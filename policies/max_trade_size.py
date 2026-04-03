#!/usr/bin/env python3
"""
OWS Executable Policy: Maximum Trade Size

Blocks any single trade exceeding a configured percentage of the portfolio's total value.
This prevents an AI agent from making disproportionately large trades.

Receives PolicyContext JSON on stdin, returns {"allow": true/false, "reason": "..."} on stdout.
Reads portfolio state from data/portfolio_state.json (written by execution bridge before signing).
"""

import json
import sys
import os
from pathlib import Path


def main():
    try:
        ctx = json.load(sys.stdin)
    except Exception as e:
        json.dump({"allow": False, "reason": f"Failed to parse policy context: {e}"}, sys.stdout)
        return

    # Get config from policy
    config = ctx.get("policy_config", {})
    max_percent = config.get("max_percent", 10)  # default 10% of portfolio

    # Read portfolio state (written by execution bridge before each sign attempt)
    state_path = Path(__file__).parent.parent / "data" / "portfolio_state.json"
    if not state_path.exists():
        json.dump({"allow": False, "reason": "Portfolio state file not found. Cannot evaluate trade size."}, sys.stdout)
        return

    try:
        with open(state_path) as f:
            portfolio = json.load(f)
    except Exception as e:
        json.dump({"allow": False, "reason": f"Failed to read portfolio state: {e}"}, sys.stdout)
        return

    total_value = portfolio.get("total_value_wei", 0)
    if total_value <= 0:
        json.dump({"allow": False, "reason": "Portfolio has zero or negative value."}, sys.stdout)
        return

    # Get transaction value
    tx = ctx.get("transaction", {})
    trade_value = int(tx.get("value", "0"))

    # Calculate percentage
    trade_percent = (trade_value / total_value) * 100

    if trade_percent > max_percent:
        json.dump({
            "allow": False,
            "reason": f"Trade size {trade_percent:.1f}% of portfolio exceeds maximum allowed {max_percent}%. "
                      f"Trade: {trade_value} wei, Portfolio: {total_value} wei."
        }, sys.stdout)
    else:
        json.dump({
            "allow": True,
            "reason": f"Trade size {trade_percent:.1f}% of portfolio is within {max_percent}% limit."
        }, sys.stdout)


if __name__ == "__main__":
    main()
