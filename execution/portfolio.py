"""Portfolio state management backed by SQLite."""

import sqlite3
import json
import os
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "openvault.db"


@dataclass
class Position:
    asset: str
    amount_wei: int  # in smallest unit (wei for ETH)
    chain_id: str
    last_updated: str = ""


@dataclass
class Portfolio:
    wallet_id: str
    total_value_wei: int = 0
    positions: list[Position] = field(default_factory=list)
    cash_wei: int = 0  # available to trade


def init_db(db_path: Path = DB_PATH):
    """Initialize the SQLite database with all required tables."""
    os.makedirs(db_path.parent, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS portfolio (
            wallet_id TEXT PRIMARY KEY,
            total_value_wei TEXT NOT NULL DEFAULT '0',
            cash_wei TEXT NOT NULL DEFAULT '0',
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_id TEXT NOT NULL,
            asset TEXT NOT NULL,
            amount_wei TEXT NOT NULL DEFAULT '0',
            chain_id TEXT NOT NULL,
            last_updated TEXT NOT NULL,
            FOREIGN KEY (wallet_id) REFERENCES portfolio(wallet_id),
            UNIQUE(wallet_id, asset, chain_id)
        );

        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            wallet_id TEXT NOT NULL,
            api_key_id TEXT NOT NULL,
            api_key_token TEXT NOT NULL,
            budget_wei TEXT NOT NULL,
            spent_wei TEXT NOT NULL DEFAULT '0',
            allowed_chains TEXT NOT NULL DEFAULT '[]',
            started_at TEXT NOT NULL,
            expires_at TEXT,
            ended_at TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            FOREIGN KEY (wallet_id) REFERENCES portfolio(wallet_id)
        );

        CREATE TABLE IF NOT EXISTS trade_log (
            trade_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            session_id TEXT,
            wallet_id TEXT NOT NULL,
            token TEXT NOT NULL,
            direction TEXT NOT NULL,
            amount_wei TEXT NOT NULL,
            chain_id TEXT NOT NULL,
            tx_hex TEXT,
            tx_hash TEXT,
            policy_result TEXT NOT NULL,
            denial_reason TEXT,
            research_rating TEXT,
            research_memo TEXT,
            analyst_reports TEXT,
            signature TEXT,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id),
            FOREIGN KEY (wallet_id) REFERENCES portfolio(wallet_id)
        );
    """)
    conn.close()


def get_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def seed_portfolio(wallet_id: str, total_value_wei: int, cash_wei: int, db_path: Path = DB_PATH):
    """Seed a portfolio with initial values for demo."""
    conn = get_db(db_path)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO portfolio (wallet_id, total_value_wei, cash_wei, updated_at) VALUES (?, ?, ?, ?)",
        (wallet_id, str(total_value_wei), str(cash_wei), now)
    )
    conn.commit()
    conn.close()


def get_portfolio(wallet_id: str, db_path: Path = DB_PATH) -> Optional[dict]:
    conn = get_db(db_path)
    row = conn.execute("SELECT * FROM portfolio WHERE wallet_id = ?", (wallet_id,)).fetchone()
    if not row:
        conn.close()
        return None
    positions = conn.execute("SELECT * FROM positions WHERE wallet_id = ?", (wallet_id,)).fetchall()
    conn.close()
    return {
        "wallet_id": row["wallet_id"],
        "total_value_wei": int(float(row["total_value_wei"])),
        "cash_wei": int(float(row["cash_wei"])),
        "positions": [dict(p) for p in positions],
    }


def update_portfolio_after_trade(wallet_id: str, amount_wei: int, direction: str, asset: str, chain_id: str, db_path: Path = DB_PATH):
    """Update portfolio state after a successful trade."""
    conn = get_db(db_path)
    now = datetime.now(timezone.utc).isoformat()

    if direction == "BUY":
        conn.execute(
            "UPDATE portfolio SET cash_wei = CAST(CAST(cash_wei AS INTEGER) - ? AS TEXT), updated_at = ? WHERE wallet_id = ?",
            (amount_wei, now, wallet_id)
        )
        conn.execute("""
            INSERT INTO positions (wallet_id, asset, amount_wei, chain_id, last_updated)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(wallet_id, asset, chain_id) DO UPDATE SET
                amount_wei = CAST(CAST(amount_wei AS INTEGER) + ? AS TEXT),
                last_updated = ?
        """, (wallet_id, asset, str(amount_wei), chain_id, now, amount_wei, now))
    elif direction == "SELL":
        conn.execute(
            "UPDATE portfolio SET cash_wei = CAST(CAST(cash_wei AS INTEGER) + ? AS TEXT), updated_at = ? WHERE wallet_id = ?",
            (amount_wei, now, wallet_id)
        )
        conn.execute("""
            UPDATE positions SET
                amount_wei = CAST(CAST(amount_wei AS INTEGER) - ? AS TEXT),
                last_updated = ?
            WHERE wallet_id = ? AND asset = ? AND chain_id = ?
        """, (amount_wei, now, wallet_id, asset, chain_id))

    conn.commit()
    conn.close()


def write_portfolio_state_json(wallet_id: str, db_path: Path = DB_PATH):
    """Write portfolio state to a JSON file that OWS executable policies can read."""
    portfolio = get_portfolio(wallet_id, db_path)
    if not portfolio:
        return
    state_path = Path(__file__).parent.parent / "data" / "portfolio_state.json"
    with open(state_path, "w") as f:
        json.dump(portfolio, f)
    return state_path
