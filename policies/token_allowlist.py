#!/usr/bin/env python3
"""
OWS Executable Policy: Token Allowlist

Restricts agents to trading only approved tokens.
Prevents agents from trading unknown or high-risk assets.

Receives PolicyContext JSON on stdin, returns {"allow": true/false, "reason": "..."} on stdout.
Reads allowlist from data/token_allowlist.json.
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

    allowlist_path = Path(__file__).parent.parent / "data" / "token_allowlist.json"
    if not allowlist_path.exists():
        json.dump({"allow": True, "reason": "No allowlist configured — all tokens permitted."}, sys.stdout)
        return

    try:
        with open(allowlist_path) as f:
            allowlist = json.load(f)
    except Exception as e:
        json.dump({"allow": False, "reason": f"Failed to read allowlist: {e}"}, sys.stdout)
        return

    allowed_tokens = [t.lower() for t in allowlist.get("tokens", [])]
    tx = ctx.get("transaction", {})
    token = tx.get("data", "").lower()  # token name passed in tx data field

    if not allowed_tokens:
        json.dump({"allow": True, "reason": "Allowlist is empty — all tokens permitted."}, sys.stdout)
        return

    if token in allowed_tokens:
        json.dump({"allow": True, "reason": f"Token '{token}' is on the allowlist."}, sys.stdout)
    else:
        json.dump({
            "allow": False,
            "reason": f"Token '{token}' is not on the approved trading list. Allowed: {', '.join(allowed_tokens[:10])}"
        }, sys.stdout)


if __name__ == "__main__":
    main()
