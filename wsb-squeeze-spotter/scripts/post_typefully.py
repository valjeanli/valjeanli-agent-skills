#!/usr/bin/env python3
"""
Post WSB Squeeze Spotter signals to Typefully.
Reads JSON from stdin (piped from spotter.py output).
"""

import json
import os
import sys
import urllib.request
import urllib.error

TYPEFULLY_API = "https://api.typefully.com/v1/drafts/"

def post_to_typefully(content: str) -> bool:
    api_key = os.environ.get("TYPEFULLY_API_KEY", "")
    if not api_key:
        print("TYPEFULLY_API_KEY not set", file=sys.stderr)
        return False

    data = json.dumps({
        "content": content,
        "share": False,
        "threadify": True,
    }).encode("utf-8")

    req = urllib.request.Request(
        TYPEFULLY_API,
        data=data,
        headers={
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode()
            print(f"Typefully: {resp.status} — {body[:200]}", file=sys.stderr)
            return resp.status == 200
    except urllib.error.HTTPError as e:
        print(f"Typefully error: {e.code} {e.read()[:200]}", file=sys.stderr)
        return False

def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print("No valid JSON on stdin", file=sys.stderr)
        sys.exit(1)

    if data.get("status") != "alert":
        print("No signals — nothing to post", file=sys.stderr)
        return

    lines = ["🚨 WSB Squeeze Spotter Alert\n"]
    for s in data.get("signals", []):
        lines.append(f"${s['ticker']}")
        lines.append(f"  WSB mentions: {s['wsb_mentions']}")
        lines.append(f"  StockTwits watchlist: {s['stocktwits_watchlist']:,}")
        lines.append(f"  Headlines: {len(s.get('headlines', []))}")
        lines.append("")

    content = "\n".join(lines)
    success = post_to_typefully(content)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
