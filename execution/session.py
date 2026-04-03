"""Session manager for trading sessions with time-scoped OWS API keys."""

import json
import uuid
import sqlite3
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

import ows

from execution.portfolio import get_db, DB_PATH


@dataclass
class Session:
    session_id: str
    wallet_id: str
    api_key_id: str
    api_key_token: str
    budget_wei: int
    spent_wei: int
    allowed_chains: list[str]
    started_at: str
    expires_at: Optional[str]
    status: str  # 'active', 'ended', 'expired'


class SessionManager:
    def __init__(self, wallet_name: str, wallet_id: str, passphrase: str, db_path: Path = DB_PATH):
        self.wallet_name = wallet_name
        self.wallet_id = wallet_id
        self.passphrase = passphrase
        self.db_path = db_path

    def create_session(
        self,
        budget_wei: int,
        duration_hours: float = 24.0,
        allowed_chains: list[str] = None,
    ) -> Session:
        """Create a new trading session with an OWS API key scoped to policies."""
        if allowed_chains is None:
            allowed_chains = ["solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"]

        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(hours=duration_hours)).isoformat()

        # Collect policy IDs to bind
        policy_ids = []
        try:
            policies = ows.list_policies()
            for p in policies:
                pid = p.get("id", "")
                if pid in ("openvault-max-trade-size", "openvault-session-budget"):
                    policy_ids.append(pid)
        except Exception:
            pass

        # Create OWS API key for this session
        key_result = ows.create_api_key(
            name=f"session-{session_id[:8]}",
            wallet_ids=[self.wallet_id],
            passphrase=self.passphrase,
            policy_ids=policy_ids if policy_ids else None,
            expires_at=expires_at,
        )

        session = Session(
            session_id=session_id,
            wallet_id=self.wallet_id,
            api_key_id=key_result["id"],
            api_key_token=key_result["token"],
            budget_wei=budget_wei,
            spent_wei=0,
            allowed_chains=allowed_chains,
            started_at=now.isoformat(),
            expires_at=expires_at,
            status="active",
        )

        # Persist to DB
        conn = get_db(self.db_path)
        conn.execute(
            """INSERT INTO sessions (session_id, wallet_id, api_key_id, api_key_token,
               budget_wei, spent_wei, allowed_chains, started_at, expires_at, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session.session_id, session.wallet_id, session.api_key_id,
             session.api_key_token, str(session.budget_wei), str(session.spent_wei),
             json.dumps(session.allowed_chains), session.started_at,
             session.expires_at, session.status)
        )
        conn.commit()
        conn.close()

        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        conn = get_db(self.db_path)
        row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        conn.close()
        if not row:
            return None
        return Session(
            session_id=row["session_id"],
            wallet_id=row["wallet_id"],
            api_key_id=row["api_key_id"],
            api_key_token=row["api_key_token"],
            budget_wei=int(row["budget_wei"]),
            spent_wei=int(row["spent_wei"]),
            allowed_chains=json.loads(row["allowed_chains"]),
            started_at=row["started_at"],
            expires_at=row["expires_at"],
            status=row["status"],
        )

    def update_spent(self, session_id: str, additional_wei: int):
        conn = get_db(self.db_path)
        conn.execute(
            "UPDATE sessions SET spent_wei = CAST(CAST(spent_wei AS INTEGER) + ? AS TEXT) WHERE session_id = ?",
            (additional_wei, session_id)
        )
        conn.commit()
        conn.close()

    def end_session(self, session_id: str):
        session = self.get_session(session_id)
        if not session:
            return
        # Revoke the OWS API key
        try:
            ows.revoke_api_key(session.api_key_id)
        except Exception:
            pass

        conn = get_db(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE sessions SET status = 'ended', ended_at = ? WHERE session_id = ?",
            (now, session_id)
        )
        conn.commit()
        conn.close()

    def write_session_state_json(self, session_id: str) -> Path:
        """Write session state to JSON for OWS executable policies to read."""
        session = self.get_session(session_id)
        state_path = Path(__file__).parent.parent / "data" / "session_state.json"
        state = {
            "session_id": session.session_id,
            "budget_wei": session.budget_wei,
            "spent_wei": session.spent_wei,
            "allowed_chains": session.allowed_chains,
            "started_at": session.started_at,
            "expires_at": session.expires_at,
        }
        with open(state_path, "w") as f:
            json.dump(state, f)
        return state_path

    def list_sessions(self, status: str = None) -> list[dict]:
        conn = get_db(self.db_path)
        if status:
            rows = conn.execute("SELECT * FROM sessions WHERE status = ? ORDER BY started_at DESC", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM sessions ORDER BY started_at DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]
