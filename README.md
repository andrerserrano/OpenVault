# OpenVault

**Policy-gated wallet infrastructure for AI trading agents on Solana.**

Built on the [Open Wallet Standard](https://github.com/open-wallet-standard/core) at the OWS Hackathon — April 2026.

---

## The Problem

AI agents need wallets to trade. But an autonomous agent with unrestricted wallet access is a liability — it can drain funds, make disproportionately large bets, or execute trades with no accountability.

## The Solution

OpenVault wraps OWS with **configurable trading policies** that are evaluated before every signature. Every trade attempt — approved or denied — is logged with the full AI reasoning chain that led to the decision.

Two policy layers enforce risk limits:
- **Max Trade Size** — No single trade can exceed X% of total portfolio value
- **Session Budget** — Cumulative spend is capped per trading session

## Quick Start

```bash
pip install open-wallet-standard fastapi uvicorn requests

# Start the server
cd openvault
python -m uvicorn api.main:app --port 8001

# In another terminal, run the demo
python demo/run_demo.py
```

Open **http://localhost:8001** to see the audit viewer.

## Demo: 3 Acts

**Act 1 — Happy Path:** Agent buys 5 SOL (5% of portfolio) → policies approve → OWS signs via Ed25519 → trade logged with research memo.

**Act 2 — Policy Guardrail:** Agent tries 15 SOL trade (15% of portfolio) → max trade size policy denies. Then session budget kicks in when cumulative spend exceeds the cap. Both denials logged.

**Act 3 — Audit Trail:** Open the viewer → timeline of approved (green) and denied (red) trades → click any trade → see the analyst reports, research reasoning, and policy evaluation.

## Architecture

```
[AI Agent Decision]  →  [OpenVault Policy Engine]  →  [OWS Signing]  →  [Audit Log]
                              │                            │                 │
                        Max trade size           Ed25519 signature     Trade details
                        Session budget           (Solana)              + AI reasoning
                              │                                        + policy result
                         Allow / Deny
```

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/setup` | POST | Create Solana wallet + register policies |
| `/api/sessions/create` | POST | Start a trading session with budget |
| `/api/sessions/{id}/end` | POST | End session, revoke API key |
| `/api/trade` | POST | Execute a trade through policy engine |
| `/api/audit/trades` | GET | List all trade attempts |
| `/api/audit/trades/{id}` | GET | Full trade detail with AI reasoning |
| `/api/audit/stats` | GET | Aggregate stats (approved/denied) |
| `/api/portfolio` | GET | Current portfolio state |
| `/` | GET | Audit viewer web UI |

## Policies

### Max Trade Size
Blocks any single trade exceeding a configured percentage of total portfolio value. Default: 10%.

```
Trade: 15 SOL (15% of 100 SOL portfolio)
Policy: max_trade_percent = 10
Result: DENIED — "Trade size 15.0% exceeds maximum allowed 10%"
```

### Session Budget
Enforces a cumulative spending cap per trading session. Tracks total spend across all approved trades.

```
Session budget: 20 SOL
Already spent: 13 SOL
This trade: 9 SOL (would total 22 SOL)
Result: DENIED — "Session budget exceeded. Remaining: 7 SOL"
```

## Audit Trail

Every trade attempt is logged with:
- Trade details (token, direction, amount, chain)
- Policy evaluation (approved/denied + reason)
- OWS Ed25519 signature (if approved)
- AI research memo and analyst reports
- Session context (budget spent, remaining)

The web viewer at `/` shows a timeline with expandable trade cards.

## Built With

- [Open Wallet Standard](https://github.com/open-wallet-standard/core) — Policy-gated Solana wallet signing
- [FastAPI](https://fastapi.tiangolo.com/) — API server
- [SQLite](https://sqlite.org/) — Portfolio state and audit trail
- Python 3.9+

## Hackathon Themes

| Theme | Implementation |
|-------|---------------|
| Agent Treasury Wallet | Per-trade spend limits + session budgets |
| On-Chain Audit Log | Every trade logged with AI reasoning |
| Agent Intent Verification | Research memo = declared intent before signing |
| Session-Scoped Signing | Time-limited OWS API keys per session |
