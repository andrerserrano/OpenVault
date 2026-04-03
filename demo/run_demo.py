#!/usr/bin/env python3
"""
OpenVault — Live Demo

Demonstrates policy-gated wallet signing for AI trading agents on Solana.
Run the server first: python -m uvicorn api.main:app --port 8001

3 Acts:
  1. Happy path — trade within limits → approved → signed
  2. Policy guardrail — oversized trade → denied → logged
  3. Audit trail — view all trades with AI reasoning
"""

import requests
import time
import sys

API = "http://localhost:8001"

G = "\033[92m"   # green
R = "\033[91m"   # red
Y = "\033[93m"   # yellow
C = "\033[96m"   # cyan
B = "\033[1m"    # bold
D = "\033[2m"    # dim
X = "\033[0m"    # reset


def h(text):
    print(f"\n{B}{C}{'='*56}{X}")
    print(f"{B}{C}  {text}{X}")
    print(f"{B}{C}{'='*56}{X}\n")


def ok(t): print(f"  {G}✓{X} {t}")
def no(t): print(f"  {R}✗{X} {t}")
def ar(t): print(f"  {Y}→{X} {t}")
def dm(t): print(f"  {D}{t}{X}")


def api(method, path, data=None):
    url = f"{API}{path}"
    r = requests.post(url, json=data or {}) if method == "POST" else requests.get(url)
    return r.json()


def main():
    h("OpenVault — Policy-Gated Wallets for AI Agents")
    print("  Built on the Open Wallet Standard (OWS)")
    print(f"  Chain: Solana  |  Signing: Ed25519\n")
    input(f"  {D}Press Enter to begin...{X}")

    # ── SETUP ──────────────────────────────────────

    h("Setup: Create Solana Wallet + Policies")

    ar("Creating OWS wallet with trading policies...")
    r = api("POST", "/api/setup", {
        "wallet_name": "demo-agent",
        "passphrase": "demo-2026",
        "initial_balance_sol": 100.0,
        "max_trade_percent": 10,
    })
    ok(f"Wallet: {r['solana_address'][:12]}... (Solana)")
    ok(f"Balance: {r['balance_sol']} SOL")
    ok(f"Policies: {', '.join(r['policies'])}")
    dm("Max trade size: 10% of portfolio per trade")
    dm("Session budget: cumulative spend cap per session")

    time.sleep(0.5)

    ar("Creating trading session (20 SOL budget, 1 hour)...")
    s = api("POST", "/api/sessions/create", {"budget_sol": 20.0, "duration_hours": 1.0})
    sid = s["session_id"]
    ok(f"Session: {sid[:8]}...  |  Budget: 20 SOL  |  Expires: {s['expires_at'][:19]}")
    dm("Session-scoped OWS API key created with policy bindings")

    input(f"\n  {D}Press Enter for Act 1...{X}")

    # ── ACT 1: HAPPY PATH ──────────────────────────

    h("Act 1: Trade Within Limits → Approved")

    ar("AI agent analyzed SOL and decided to BUY...")
    dm("Technical: RSI 42, MACD bullish crossover")
    dm("Sentiment: Social volume +23%, dev activity high")
    dm("Rating: BUY with 5 SOL allocation (5% of portfolio)")
    time.sleep(0.5)

    t1 = api("POST", "/api/trade", {
        "session_id": sid,
        "token": "solana",
        "direction": "BUY",
        "amount_sol": 5.0,
        "research_memo": (
            "INVESTMENT MEMO — SOL\n\n"
            "Rating: BUY\n\n"
            "Executive Summary:\n"
            "Solana presents strong risk/reward. Technical indicators show bullish "
            "MACD crossover with RSI at 42. On-chain metrics confirm growing network "
            "activity — TVL up 12% MoM, daily active wallets at 1.2M.\n\n"
            "Key Catalysts:\n"
            "1. Firedancer client improving TPS and reliability\n"
            "2. DePIN narrative driving real-world adoption\n"
            "3. Jupiter DEX volume exceeding $2B daily\n\n"
            "Risk Factors:\n"
            "- Network congestion during high-activity periods\n"
            "- Competition from L2 ecosystems\n\n"
            "Position: 5% of portfolio (5 SOL)"
        ),
        "analyst_reports": {
            "technical": "RSI: 42, MACD: Bullish crossover, Bollinger: Near lower band",
            "sentiment": "Social volume: +23% WoW, GitHub commits: 1,247 (7d)",
            "news": "Firedancer mainnet timeline confirmed, DePIN TVL growing",
            "fundamentals": "TVL: $8.1B (+12% MoM), DEX volume: $2.3B/day",
        }
    })

    if t1["success"]:
        ok(f"APPROVED — OWS signed via Ed25519")
        ok(f"Signature: {t1['signature']}")
        dm(f"5 SOL = 5% of portfolio — within 10% max trade size")
        dm(f"Session: 5 of 20 SOL budget used")
    else:
        no(f"Unexpected: {t1['message']}")

    input(f"\n  {D}Press Enter for Act 2...{X}")

    # ── ACT 2: POLICY DENIAL ───────────────────────

    h("Act 2: Oversized Trade → Policy Denied")

    ar("Agent tries aggressive 15 SOL trade (15% of portfolio)...")
    dm("This exceeds the 10% max trade size policy")
    time.sleep(0.5)

    t2 = api("POST", "/api/trade", {
        "session_id": sid,
        "token": "bonk",
        "direction": "BUY",
        "amount_sol": 15.0,
        "research_memo": "Aggressive BONK position — agent attempting to exceed risk limits",
        "analyst_reports": {"note": "High-conviction memecoin play"},
    })

    if not t2["success"] and t2["policy_result"] == "DENIED":
        ok(f"DENIED by policy engine!")
        no(f"Reason: {t2['denial_reason'][:80]}...")
        dm("The agent can't overspend — policy blocked before wallet signed")
        dm("Denial logged to audit trail with full context")
    else:
        dm(f"Result: {t2['message']}")

    time.sleep(0.5)

    ar("Agent makes a reasonable 8 SOL trade instead...")
    t3 = api("POST", "/api/trade", {
        "session_id": sid,
        "token": "jupiter-exchange-solana",
        "direction": "BUY",
        "amount_sol": 8.0,
        "research_memo": (
            "INVESTMENT MEMO — JUP\n\n"
            "Rating: OVERWEIGHT\n\n"
            "Jupiter ecosystem expanding rapidly. Perps volume growing, "
            "LFG launchpad creating sticky demand for JUP token. "
            "Position sizing at 8% reflects moderate-high conviction."
        ),
        "analyst_reports": {
            "technical": "RSI: 55, MACD: Neutral-bullish",
            "fundamentals": "DEX volume: $2.3B/day, Perps: $800M/day",
        }
    })

    if t3["success"]:
        ok(f"APPROVED — 8 SOL (8%) is within the 10% limit")
        ok(f"Signature: {t3['signature']}")
        dm(f"Session: 13 of 20 SOL budget used")

    time.sleep(0.5)

    ar("Agent tries one more 9 SOL trade — would exceed session budget...")
    t4 = api("POST", "/api/trade", {
        "session_id": sid,
        "token": "raydium",
        "direction": "BUY",
        "amount_sol": 9.0,
        "research_memo": "BUY RAY — DeFi momentum play",
        "analyst_reports": {},
    })

    if not t4["success"]:
        ok(f"DENIED by session budget!")
        no(f"Reason: {t4['denial_reason'][:80]}...")
        dm("Two policy layers: per-trade size AND cumulative session budget")

    input(f"\n  {D}Press Enter for Act 3...{X}")

    # ── ACT 3: AUDIT TRAIL ─────────────────────────

    h("Act 3: Audit Trail with AI Reasoning")

    stats = api("GET", "/api/audit/stats")
    ok(f"Total trades: {stats['total_trades']}")
    ok(f"Approved: {stats['approved']}  |  Denied: {stats['denied']}")

    time.sleep(0.5)

    ar("Every trade attempt is logged with:")
    dm("• The full research memo and analyst reports")
    dm("• Policy evaluation result (approved/denied + reason)")
    dm("• OWS Ed25519 signature (if approved)")
    dm("• Session context (budget spent, remaining)")
    dm("")
    dm("Click any trade in the viewer to see the full AI reasoning.")

    print(f"\n  {B}{G}→ Audit viewer: http://localhost:8001{X}")
    print(f"  {D}Auto-refreshes every 5 seconds{X}")

    # ── SUMMARY ────────────────────────────────────

    h("What This Demonstrates")

    print(f"  {G}1.{X} Agent Treasury Wallet — per-trade spend limits")
    print(f"     and cumulative session budgets on Solana")
    print(f"  {G}2.{X} On-Chain Audit Log — every trade logged with")
    print(f"     the full AI research reasoning behind it")
    print(f"  {G}3.{X} Agent Intent Verification — research memo is")
    print(f"     the declared intent before signing")
    print(f"  {G}4.{X} Session-Scoped Signing — time-limited OWS API")
    print(f"     keys with automatic expiry")
    print(f"\n  {B}Built on OWS. Running on Solana.{X}\n")


if __name__ == "__main__":
    main()
