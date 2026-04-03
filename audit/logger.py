"""Audit logger for trade attempts with AI reasoning context."""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path

from execution.portfolio import get_db, DB_PATH


class AuditLogger:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    def log_trade(
        self,
        trade_id: str,
        session_id: str,
        wallet_id: str,
        token: str,
        direction: str,
        amount_wei: int,
        chain_id: str,
        tx_hex: str = None,
        policy_result: str = "PENDING",
        denial_reason: str = None,
        research_rating: str = None,
        research_memo: str = None,
        analyst_reports: dict = None,
        signature: str = None,
        tx_hash: str = None,
    ):
        """Log a trade attempt with full research context."""
        conn = get_db(self.db_path)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO trade_log (trade_id, timestamp, session_id, wallet_id,
               token, direction, amount_wei, chain_id, tx_hex, tx_hash,
               policy_result, denial_reason, research_rating, research_memo,
               analyst_reports, signature)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (trade_id, now, session_id, wallet_id, token, direction,
             str(amount_wei), chain_id, tx_hex, tx_hash, policy_result,
             denial_reason, research_rating, research_memo,
             json.dumps(analyst_reports) if analyst_reports else None, signature)
        )
        conn.commit()
        conn.close()

    def get_trades(self, session_id: str = None, limit: int = 50) -> list[dict]:
        conn = get_db(self.db_path)
        if session_id:
            rows = conn.execute(
                "SELECT * FROM trade_log WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
                (session_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM trade_log ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_trade(self, trade_id: str) -> Optional[dict]:
        conn = get_db(self.db_path)
        row = conn.execute("SELECT * FROM trade_log WHERE trade_id = ?", (trade_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_session_summary(self, session_id: str) -> dict:
        conn = get_db(self.db_path)
        trades = conn.execute(
            "SELECT * FROM trade_log WHERE session_id = ? ORDER BY timestamp ASC",
            (session_id,)
        ).fetchall()
        conn.close()

        total_trades = len(trades)
        approved = sum(1 for t in trades if t["policy_result"] == "APPROVED")
        denied = sum(1 for t in trades if t["policy_result"] == "DENIED")
        total_volume = sum(int(t["amount_wei"]) for t in trades if t["policy_result"] == "APPROVED")

        return {
            "session_id": session_id,
            "total_trades": total_trades,
            "approved": approved,
            "denied": denied,
            "total_volume_wei": total_volume,
            "trades": [dict(t) for t in trades],
        }

    def get_stats(self) -> dict:
        conn = get_db(self.db_path)
        total = conn.execute("SELECT COUNT(*) FROM trade_log").fetchone()[0]
        approved = conn.execute("SELECT COUNT(*) FROM trade_log WHERE policy_result = 'APPROVED'").fetchone()[0]
        denied = conn.execute("SELECT COUNT(*) FROM trade_log WHERE policy_result = 'DENIED'").fetchone()[0]
        conn.close()
        return {"total_trades": total, "approved": approved, "denied": denied}
