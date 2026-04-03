#!/usr/bin/env python3
"""
OWS Executable Policy: Session Budget

Enforces a cumulative spending cap per trading session.
Tracks total spent across all trades in the session and denies if budget would be exceeded.

Receives PolicyContext JSON on stdin, returns {"allow": true/false, "reason": "..."} on stdout.
Reads session state from data/session_state.json (written by execution bridge before signing).
"""

import json
import sys
from pathlib import Path


def main():
    try:
        ctx = json.load(sys.stdin)
    except Exception as e:
        json.dump({"allow": False, "reason": f"Failed to parse policy context: {e}"}, sys.stdout)
        return

    # Read session state
    state_path = Path(__file__).parent.parent / "data" / "session_state.json"
    if not state_path.exists():
        json.dump({"allow": False, "reason": "Session state file not found. Cannot evaluate budget."}, sys.stdout)
        return

    try:
        with open(state_path) as f:
            session = json.load(f)
    except Exception as e:
        json.dump({"allow": False, "reason": f"Failed to read session state: {e}"}, sys.stdout)
        return

    budget_wei = int(session.get("budget_wei", 0))
    spent_wei = int(session.get("spent_wei", 0))

    # Get transaction value
    tx = ctx.get("transaction", {})
    trade_value = int(tx.get("value", "0"))

    new_total = spent_wei + trade_value
    remaining = budget_wei - spent_wei

    if new_total > budget_wei:
        json.dump({
            "allow": False,
            "reason": f"Session budget exceeded. Budget: {budget_wei} wei, Already spent: {spent_wei} wei, "
                      f"This trade: {trade_value} wei, Would total: {new_total} wei. "
                      f"Remaining budget: {remaining} wei."
        }, sys.stdout)
    else:
        json.dump({
            "allow": True,
            "reason": f"Within session budget. Spent: {spent_wei}/{budget_wei} wei. "
                      f"After this trade: {new_total}/{budget_wei} wei."
        }, sys.stdout)


if __name__ == "__main__":
    main()
