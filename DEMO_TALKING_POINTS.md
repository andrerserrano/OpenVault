# OpenVault — IRL Demo Talking Points (4:30pm)

## Setup (before you go on)
```bash
cd /Users/andre/Documents/openvault
python3 -m uvicorn api.main:app --port 8001
# Open http://localhost:8001 in browser (audit viewer)
# Open terminal for demo script
python3 demo/run_demo.py
```

---

## The Pitch (30 seconds)

"AI agents need wallets to operate autonomously — but giving an agent unrestricted wallet access is like giving an intern your corporate Amex with no spending limit. OpenVault solves this. It wraps OWS with configurable trading policies that gate every signature, and logs an audit trail that attaches the AI's reasoning to every transaction."

---

## Walking Through the Demo

### Setup Phase
**What you're showing:** OWS Solana wallet creation + policy registration

**Say:** "One API call creates a Solana wallet, registers two trading policies — max trade size and session budget — and seeds a 100 SOL portfolio. The agent gets a session-scoped API key that expires automatically."

**Point at:** The Solana address, the two policy names, the session expiry time.

### Act 1: Approved Trade
**What you're showing:** A 5 SOL trade (5%) passes both policies and gets signed

**Say:** "The agent wants to buy SOL — 5% of its portfolio. The policy engine checks: is this under the 10% per-trade limit? Yes. Is the session budget okay? Yes. OWS signs it with Ed25519. The trade and the full research memo are logged."

**Point at:** The signature, the "5% of portfolio — within 10% limit" note.

### Act 2: Policy Denial (THIS IS THE MONEY MOMENT)
**What you're showing:** A 15 SOL trade (15%) gets blocked

**Say:** "Now the agent gets aggressive — tries to buy 15 SOL, which is 15% of the portfolio. The policy engine blocks it before the wallet ever signs. The denial is logged with the reason. The agent literally cannot overspend."

**Point at:** The denial reason showing exact percentages. Then: "And then the session budget kicks in too — after spending 13 SOL across two approved trades, a 9 SOL trade would exceed the 20 SOL session cap. Denied again."

**Emphasize:** "Two independent policy layers. The agent can make reasonable trades, but it can't go rogue."

### Act 3: Audit Viewer
**What you're showing:** The web UI at localhost:8001

**Say:** "Every trade attempt — approved or denied — is in the audit trail. Click any trade and you see the full AI research memo that led to that decision. This is the part no one else has — you can trace from a signed transaction back through the analysis to understand exactly WHY the agent made that trade."

**Click:** Expand a trade card, show the research memo. Then show a denied trade with the denial reason.

---

## Anticipated Questions & Answers

**"What chain is this on?"**
Solana. OWS supports 10 chains natively — we're using Solana with Ed25519 signing. The policy layer is chain-agnostic.

**"Is this paper trading or real?"**
The wallet infrastructure is real — real OWS wallets, real Ed25519 signatures, real policy enforcement. The trades themselves are paper trades (we construct the transaction payload but don't broadcast to mainnet). Plugging in real execution is a one-line change to call `sign_and_send` instead of `sign_transaction`.

**"What are the policies?"**
Two right now: max trade size (no single trade over X% of portfolio) and session budget (cumulative spend cap per session). They're Python scripts that OWS can execute before signing — you can write any policy logic you want.

**"How is this different from just... not giving the agent too much money?"**
Giving an agent a small wallet is coarse-grained — it can still blow the whole thing in one trade. OpenVault is fine-grained: per-trade limits, cumulative budgets, time-bounded sessions. And the audit trail gives you accountability — you know WHY every trade happened.

**"What's the AI reasoning in the audit trail?"**
We attach the research memo — the analysis that led to the trade decision — to every audit entry. In production, this comes from a multi-agent research pipeline (analysts, debate, risk committee). For the demo, it's structured memos showing the kind of reasoning that gets logged.

**"Are you building a product with this?"**
Yes — we're building a competitive arena for AI trading agents. OpenVault is the wallet infrastructure layer. Each agent in the arena gets an OWS wallet with policy limits. You can see the arena at agentcircuit.io.

---

## If You Only Have 2 Minutes

1. Run the demo script — it takes 60 seconds with the Enter prompts
2. Show the audit viewer — click one approved trade (show the research memo) and one denied trade (show the denial reason)
3. Say: "Every AI agent trade is policy-checked before signing and auditable with full reasoning. That's OpenVault."

---

## Key Stats to Drop

- 4 hackathon themes in one project (treasury wallet, audit log, intent verification, session tokens)
- 2 independent policy layers (per-trade + session budget)
- Ed25519 signing on Solana via OWS
- Every trade logged with AI reasoning — not just transaction data
- Session-scoped API keys with automatic expiry
