"""Execution bridge: connects research signals to OWS-gated trade execution."""

import json
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

import ows

from execution.portfolio import (
    get_portfolio, write_portfolio_state_json, update_portfolio_after_trade, DB_PATH
)
from execution.session import Session, SessionManager
from audit.logger import AuditLogger


@dataclass
class TradeSignal:
    token: str
    direction: str  # BUY, SELL
    rating: str  # BUY, OVERWEIGHT, HOLD, UNDERWEIGHT, SELL
    confidence: float  # 0-1
    amount_wei: int
    chain_id: str
    research_memo: str
    analyst_reports: dict  # {market, sentiment, news, fundamentals}


@dataclass
class TradeResult:
    trade_id: str
    success: bool
    policy_result: str  # APPROVED, DENIED
    denial_reason: Optional[str]
    signature: Optional[str]
    tx_hash: Optional[str]
    message: str


class ExecutionBridge:
    def __init__(self, wallet_name: str, session_manager: SessionManager, audit_logger: AuditLogger, db_path: Path = DB_PATH):
        self.wallet_name = wallet_name
        self.session_manager = session_manager
        self.audit_logger = audit_logger
        self.db_path = db_path

    def parse_research_signal(
        self,
        rating: str,
        token: str,
        research_memo: str,
        analyst_reports: dict,
        portfolio_percent: float = 5.0,
        chain_id: str = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp",
    ) -> Optional[TradeSignal]:
        """Parse a research rating into a trade signal with calculated amount."""
        direction_map = {
            "BUY": ("BUY", 1.0),
            "OVERWEIGHT": ("BUY", 0.7),
            "HOLD": (None, 0.0),
            "UNDERWEIGHT": ("SELL", 0.5),
            "SELL": ("SELL", 1.0),
        }

        direction, confidence = direction_map.get(rating.upper(), (None, 0.0))
        if direction is None:
            return None  # HOLD = no trade

        # Get portfolio to calculate trade size
        portfolio = get_portfolio(self.session_manager.wallet_id, self.db_path)
        if not portfolio:
            return None

        # Calculate amount as percentage of portfolio
        base_amount = int(portfolio["total_value_wei"] * (portfolio_percent / 100))
        amount_wei = int(base_amount * confidence)

        if amount_wei <= 0:
            return None

        return TradeSignal(
            token=token,
            direction=direction,
            rating=rating,
            confidence=confidence,
            amount_wei=amount_wei,
            chain_id=chain_id,
            research_memo=research_memo,
            analyst_reports=analyst_reports,
        )

    def _evaluate_policies(self, signal: TradeSignal, session: Session) -> tuple[bool, str]:
        """Evaluate trading policies before signing.

        Runs the same logic as OWS executable policies, but in-process
        for reliable enforcement and richer error messages.
        """
        # Policy 1: Max trade size (% of portfolio)
        portfolio = get_portfolio(session.wallet_id, self.db_path)
        if not portfolio:
            return False, "Portfolio not found"

        total_value = portfolio["total_value_wei"]
        if total_value <= 0:
            return False, "Portfolio has zero value"

        max_percent = 10  # configurable
        trade_percent = (signal.amount_wei / total_value) * 100
        if trade_percent > max_percent:
            return False, (
                f"Trade size {trade_percent:.1f}% of portfolio exceeds maximum allowed {max_percent}%. "
                f"Trade: {signal.amount_wei} wei ({signal.amount_wei / 1e9:.2f} SOL), "
                f"Portfolio: {total_value} wei ({total_value / 1e9:.2f} SOL)."
            )

        # Policy 2: Session budget
        session_data = self.session_manager.get_session(session.session_id)
        if session_data:
            new_total = session_data.spent_wei + signal.amount_wei
            if new_total > session_data.budget_wei:
                remaining = session_data.budget_wei - session_data.spent_wei
                return False, (
                    f"Session budget exceeded. Budget: {session_data.budget_wei / 1e9:.2f} SOL, "
                    f"Already spent: {session_data.spent_wei / 1e9:.2f} SOL, "
                    f"This trade: {signal.amount_wei / 1e9:.2f} SOL, "
                    f"Remaining: {remaining / 1e9:.2f} SOL."
                )

        return True, "All policies passed"

    def execute_trade(self, signal: TradeSignal, session: Session) -> TradeResult:
        """Execute a trade through OWS with policy enforcement."""
        trade_id = str(uuid.uuid4())

        # 1. Write state files for OWS executable policies
        write_portfolio_state_json(session.wallet_id, self.db_path)
        self.session_manager.write_session_state_json(session.session_id)

        # 2. Evaluate policies in-process (reliable enforcement)
        policy_ok, policy_reason = self._evaluate_policies(signal, session)

        if not policy_ok:
            trade_result = TradeResult(
                trade_id=trade_id,
                success=False,
                policy_result="DENIED",
                denial_reason=policy_reason,
                signature=None,
                tx_hash=None,
                message=f"{signal.direction} {signal.token}: Policy denied — {policy_reason}"
            )
            # Log denial to audit trail
            self.audit_logger.log_trade(
                trade_id=trade_id,
                session_id=session.session_id,
                wallet_id=session.wallet_id,
                token=signal.token,
                direction=signal.direction,
                amount_wei=signal.amount_wei,
                chain_id=signal.chain_id,
                policy_result="DENIED",
                denial_reason=policy_reason,
                research_rating=signal.rating,
                research_memo=signal.research_memo,
                analyst_reports=signal.analyst_reports,
            )
            return trade_result

        # 3. Construct Solana transaction (simplified for paper trading)
        tx_hex = self._construct_solana_tx(signal.amount_wei, signal.token)

        # 4. Sign via OWS on Solana (agent API key — declarative policies still enforced)
        try:
            result = ows.sign_transaction(
                wallet=self.wallet_name,
                chain="solana",
                tx_hex=tx_hex,
                passphrase=session.api_key_token,
            )

            signature = result.get("signature", "")

            # Update session spent
            self.session_manager.update_spent(session.session_id, signal.amount_wei)

            # Update portfolio
            update_portfolio_after_trade(
                session.wallet_id, signal.amount_wei,
                signal.direction, signal.token, signal.chain_id, self.db_path
            )

            trade_result = TradeResult(
                trade_id=trade_id,
                success=True,
                policy_result="APPROVED",
                denial_reason=None,
                signature=signature,
                tx_hash=None,
                message=f"{signal.direction} {signal.token}: {signal.amount_wei} wei signed successfully."
            )

        except Exception as e:
            error_msg = str(e)
            is_policy_denial = "policy denied" in error_msg.lower()

            trade_result = TradeResult(
                trade_id=trade_id,
                success=False,
                policy_result="DENIED" if is_policy_denial else "ERROR",
                denial_reason=error_msg,
                signature=None,
                tx_hash=None,
                message=f"{signal.direction} {signal.token}: {'Policy denied' if is_policy_denial else 'Error'} - {error_msg}"
            )

        # 5. Log to audit trail
        self.audit_logger.log_trade(
            trade_id=trade_id,
            session_id=session.session_id,
            wallet_id=session.wallet_id,
            token=signal.token,
            direction=signal.direction,
            amount_wei=signal.amount_wei,
            chain_id=signal.chain_id,
            tx_hex=tx_hex,
            policy_result=trade_result.policy_result,
            denial_reason=trade_result.denial_reason,
            research_rating=signal.rating,
            research_memo=signal.research_memo,
            analyst_reports=signal.analyst_reports,
            signature=trade_result.signature,
            tx_hash=trade_result.tx_hash,
        )

        return trade_result

    def execute_from_research(
        self,
        rating: str,
        token: str,
        research_memo: str,
        analyst_reports: dict,
        session: Session,
        portfolio_percent: float = 5.0,
        chain_id: str = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp",
    ) -> TradeResult:
        """Convenience: parse research output and execute in one call."""
        signal = self.parse_research_signal(
            rating=rating,
            token=token,
            research_memo=research_memo,
            analyst_reports=analyst_reports,
            portfolio_percent=portfolio_percent,
            chain_id=chain_id,
        )
        if signal is None:
            return TradeResult(
                trade_id=str(uuid.uuid4()),
                success=False,
                policy_result="SKIPPED",
                denial_reason=f"Rating '{rating}' does not produce a trade signal.",
                signature=None,
                tx_hash=None,
                message=f"No trade executed for {rating} rating on {token}."
            )
        return self.execute_trade(signal, session)

    def _construct_solana_tx(self, amount_lamports: int, token: str) -> str:
        """Construct a minimal Solana transaction-like payload for signing.

        For paper trading, we construct a deterministic byte payload that
        represents the trade intent. In production, this would be a
        serialized Solana transaction (e.g., Jupiter swap instruction).
        OWS signs whatever bytes we provide via Ed25519.
        """
        import struct
        import hashlib

        # Solana-style: recent_blockhash(32) + program_id(32) + amount(8) + token_hash(32)
        fake_blockhash = hashlib.sha256(f"blockhash-{amount_lamports}".encode()).digest()
        program_id = hashlib.sha256(b"openvault-paper-trade").digest()
        token_hash = hashlib.sha256(token.encode()).digest()

        tx_data = b""
        tx_data += b"\x01"  # num signatures placeholder
        tx_data += fake_blockhash
        tx_data += program_id
        tx_data += struct.pack("<Q", amount_lamports)  # little-endian (Solana convention)
        tx_data += token_hash

        return tx_data.hex()

    def _construct_tx(self, to: str, value: int, chain_id: str) -> str:
        """Legacy EVM tx constructor — kept for compatibility."""
        return self._construct_solana_tx(value, "unknown")
