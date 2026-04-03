"""OpenVault — API Server

Policy-gated wallet infrastructure for AI trading agents.
Built on the Open Wallet Standard (OWS).
"""

import json
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))

from execution.portfolio import init_db, get_portfolio, seed_portfolio, DB_PATH
from execution.session import SessionManager
from execution.bridge import ExecutionBridge, TradeSignal
from audit.logger import AuditLogger

import ows

app = FastAPI(
    title="OpenVault",
    description="Policy-gated wallet infrastructure for AI trading agents. Built on OWS.",
    version="0.1.0",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_state = {}


class SetupRequest(BaseModel):
    wallet_name: str = "openvault-agent"
    passphrase: str = "openvault-hackathon-2026"
    initial_balance_sol: float = 100.0  # in SOL
    max_trade_percent: int = 10
    session_budget_sol: float = 20.0


class CreateSessionRequest(BaseModel):
    budget_sol: float = 20.0
    duration_hours: float = 24.0


class TradeRequest(BaseModel):
    session_id: str
    token: str
    direction: str  # BUY or SELL
    amount_sol: float
    research_memo: str = ""
    analyst_reports: dict = {}


SOL_LAMPORTS = 1_000_000_000  # 1 SOL = 1B lamports


@app.on_event("startup")
async def startup():
    init_db()


# ── Setup ───────────────────────────────────────────

@app.post("/api/setup")
async def setup(req: SetupRequest):
    """Create an OWS Solana wallet with trading policies."""
    try:
        wallet = ows.create_wallet(name=req.wallet_name, passphrase=req.passphrase)
    except Exception as e:
        if "already exists" in str(e).lower():
            wallet = ows.get_wallet(req.wallet_name)
        else:
            raise HTTPException(status_code=500, detail=str(e))

    wallet_id = wallet["id"]
    sol_account = next((a for a in wallet["accounts"] if "solana" in a["chain_id"]), None)

    # Register policies
    now = datetime.now(timezone.utc).isoformat()
    policies_dir = Path(__file__).parent.parent / "policies"
    for pid, pname, script in [
        ("openvault-max-trade-size", "Max Trade Size", "max_trade_size.py"),
        ("openvault-session-budget", "Session Budget", "session_budget.py"),
    ]:
        try:
            ows.create_policy(json.dumps({
                "id": pid, "name": pname, "version": 1, "created_at": now,
                "rules": [], "executable": str(policies_dir / script),
                "config": {"max_percent": req.max_trade_percent}, "action": "deny",
            }))
        except Exception:
            pass

    # Seed portfolio
    balance_lamports = int(req.initial_balance_sol * SOL_LAMPORTS)
    seed_portfolio(wallet_id, balance_lamports, balance_lamports)

    _state["wallet_name"] = req.wallet_name
    _state["wallet_id"] = wallet_id
    _state["passphrase"] = req.passphrase
    _state["session_manager"] = SessionManager(req.wallet_name, wallet_id, req.passphrase)
    _state["audit_logger"] = AuditLogger()
    _state["bridge"] = ExecutionBridge(req.wallet_name, _state["session_manager"], _state["audit_logger"])

    return {
        "status": "ready",
        "wallet_id": wallet_id,
        "solana_address": sol_account["address"] if sol_account else None,
        "balance_sol": req.initial_balance_sol,
        "policies": ["openvault-max-trade-size", "openvault-session-budget"],
    }


# ── Sessions ────────────────────────────────────────

@app.post("/api/sessions/create")
async def create_session(req: CreateSessionRequest):
    sm = _state.get("session_manager")
    if not sm:
        raise HTTPException(status_code=400, detail="Run /api/setup first")
    session = sm.create_session(
        budget_wei=int(req.budget_sol * SOL_LAMPORTS),
        duration_hours=req.duration_hours,
    )
    return {
        "session_id": session.session_id,
        "budget_sol": req.budget_sol,
        "expires_at": session.expires_at,
    }


@app.post("/api/sessions/{session_id}/end")
async def end_session(session_id: str):
    sm = _state.get("session_manager")
    if not sm:
        raise HTTPException(status_code=400, detail="Run /api/setup first")
    sm.end_session(session_id)
    return {"status": "ended", "session_id": session_id}


@app.get("/api/sessions")
async def list_sessions():
    sm = _state.get("session_manager")
    if not sm:
        return {"sessions": []}
    return {"sessions": sm.list_sessions()}


# ── Trading ─────────────────────────────────────────

@app.post("/api/trade")
async def execute_trade(req: TradeRequest):
    """Execute a trade through OWS policy engine."""
    bridge = _state.get("bridge")
    sm = _state.get("session_manager")
    if not bridge or not sm:
        raise HTTPException(status_code=400, detail="Run /api/setup first")

    session = sm.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    signal = TradeSignal(
        token=req.token,
        direction=req.direction,
        rating=req.direction,
        confidence=1.0,
        amount_wei=int(req.amount_sol * SOL_LAMPORTS),
        chain_id="solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp",
        research_memo=req.research_memo,
        analyst_reports=req.analyst_reports,
    )
    result = bridge.execute_trade(signal, session)

    return {
        "trade_id": result.trade_id,
        "success": result.success,
        "policy_result": result.policy_result,
        "denial_reason": result.denial_reason,
        "signature": result.signature[:20] + "..." if result.signature else None,
        "message": result.message,
    }


# ── Audit ───────────────────────────────────────────

@app.get("/api/audit/trades")
async def get_trades(session_id: Optional[str] = None, limit: int = 50):
    logger = _state.get("audit_logger", AuditLogger())
    trades = logger.get_trades(session_id=session_id, limit=limit)
    for t in trades:
        if t.get("research_memo") and len(t["research_memo"]) > 200:
            t["research_memo_preview"] = t["research_memo"][:200] + "..."
    return {"trades": trades}


@app.get("/api/audit/trades/{trade_id}")
async def get_trade_detail(trade_id: str):
    logger = _state.get("audit_logger", AuditLogger())
    trade = logger.get_trade(trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    return trade


@app.get("/api/audit/stats")
async def get_stats():
    logger = _state.get("audit_logger", AuditLogger())
    return logger.get_stats()


@app.get("/api/portfolio")
async def get_portfolio_api():
    wallet_id = _state.get("wallet_id")
    if not wallet_id:
        raise HTTPException(status_code=400, detail="Run /api/setup first")
    return get_portfolio(wallet_id)


# ── Viewer ──────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def viewer():
    path = Path(__file__).parent.parent / "audit" / "viewer.html"
    return HTMLResponse(path.read_text())


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "openvault"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
