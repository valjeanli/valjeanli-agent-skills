#!/usr/bin/env python3
"""
WSB Squeeze Spotter — 3-step pipeline:
1. WSB RSS feed → extract tickers from titles → find most mentioned
2. StockTwits → validate flagged ticker is trending
3. Perplexity news → confirm meme-stock catalyst
"""

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional

# ─── Constants ────────────────────────────────────────────────────────────
TICKER_STOP = {
    "A","AN","AT","BY","IN","IS","IT","MY","NO","OF","ON","OR","TO","UP",
    "WE","GO","DD","EL","LA","TV","AI","OK","ALL","ARE","ASK","BUT","CAN",
    "DAY","DID","DUE","GET","HAS","HOW","ITS","LET","LOW","MAN","NEW",
    "NOW","OLD","ONE","OUT","OWN","PER","PUT","SAY","SEE","SET","SHE",
    "TWO","USE","WAY","WHO","YET","YOU","THE","AND","FOR","NOT","ARE",
    "WAS","HIS","THAT","THIS","WITH","FROM","HAVE","BEEN","LIKE","JUST",
    "MORE","SOME","THAN","INTO","THEN","ALSO","ONLY","OVER","VERY","WHEN",
    "WHAT","WHICH","WSB","YOLO","MOON","PUMP","DUMP","FOMO","HOLD","APES",
    "LFG","ATH","IMO","CEO","CFO","FDA","SEC","YTD","EPS","PE","EV","ROI",
    "ROE","EDIT","PSA","TIL","TLDR","USA","UK","EU","NYSE","NASDAQ","AMEX",
    "OTC","IPO","SPAC","COVID","BTC","ETH","USD","CAGR","IRA","RSU","ESPP",
    "HTML","JSON","HTTP","HTTPS","URL","API","PDF","CPU","GPU","SSD","HDD",
    "RAM","AM","PM","INC","LTD","LLC","CORP","BULL","BEAR","LONG","SHORT",
    "BUY","SELL","CALL","PUT","DOW","S&P","ETF","REIT","MFG","QCOM","SPY",
    "QQQ","DIA","IWM","ARKK","SPX","VIX","RH","FDX","AMA","CMV","OC","VADER",
}

MEGA_CAPS = {"AAPL","MSFT","GOOG","GOOGL","AMZN","META","NVDA","TSLA","BRK","JPM","V","MA","UNH","HD","DIS","NFLX","ADBE","CRM","INTC","AMD","PYPL","BA"}

def extract_tickers(text: str) -> list[str]:
    """Extract likely stock tickers from text."""
    candidates = re.findall(r'\$?[A-Z]{2,5}\b', text)
    result = []
    for c in candidates:
        t = c.lstrip("$")
        if t not in TICKER_STOP and len(t) >= 2:
            result.append(t)
    return result


# ─── HTTP helpers ──────────────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
]

def http_get(url: str, headers: dict = None, timeout: int = 15) -> Optional[str]:
    hdrs = {"User-Agent": USER_AGENTS[0]}
    if headers:
        hdrs.update(headers)
    try:
        req = urllib.request.Request(url, headers=hdrs)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if resp.status == 429 or (isinstance(body, str) and "429" in body[:100]):
                return None
            return body
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print(f"  [http] Rate limited (429) on {url[:60]}", file=sys.stderr)
        return None
    except Exception:
        return None

def json_get(url: str, headers: dict = None, timeout: int = 15) -> Optional[dict]:
    body = http_get(url, headers=headers, timeout=timeout)
    if body is None:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


# ─── Step 1: WSB RSS ──────────────────────────────────────────────────────
NS = {"atom": "http://www.w3.org/2005/Atom"}

def fetch_wsb_rss(limit: int = 25) -> Optional[list[dict]]:
    url = f"https://www.reddit.com/r/wallstreetbets/new/.rss?limit={limit}"
    body = http_get(url, timeout=15)
    if not body:
        print("  [step1] Reddit RSS unavailable, trying Google News fallback...", file=sys.stderr)
        return fetch_wsb_google_news(limit)
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        print(f"  [step1] XML parse error, trying Google News fallback...", file=sys.stderr)
        return fetch_wsb_google_news(limit)
    entries = root.findall("atom:entry", NS)
    posts = []
    for e in entries:
        title_el = e.find("atom:title", NS)
        author_el = e.find("atom:author/atom:name", NS)
        link_el = e.find("atom:link", NS)
        updated_el = e.find("atom:updated", NS)
        title = title_el.text.strip() if title_el is not None and title_el.text else ""
        author = author_el.text.strip() if author_el is not None and author_el.text else ""
        url = link_el.get("href", "") if link_el is not None else ""
        updated = updated_el.text.strip() if updated_el is not None and updated_el.text else ""
        if title:
            posts.append({"title": title, "author": author, "url": url, "updated": updated})
    print(f"  [step1] Fetched {len(posts)} WSB posts from RSS", file=sys.stderr)
    return posts

def fetch_wsb_google_news(limit: int = 25) -> Optional[list[dict]]:
    url = "https://news.google.com/rss/search?q=wallstreetbets+site:reddit.com&hl=en-US&gl=US&ceid=US:en"
    body = http_get(url, timeout=10)
    if not body:
        print("  [step1] Google News fallback also failed", file=sys.stderr)
        return None
    titles = re.findall(r'<title>(.*?)</title>', body)
    posts = []
    for t in titles[2:]:
        if t and t not in ("Google News",) and "wallstreetbets" in t.lower():
            posts.append({"title": t.strip(), "author": "", "url": "", "updated": ""})
    print(f"  [step1] Fetched {len(posts)} WSB headlines from Google News (fallback)", file=sys.stderr)
    return posts[:limit]

def count_ticker_mentions(posts: list[dict]) -> list[dict]:
    tally = {}
    post_map = {}
    for post in posts:
        title = post["title"]
        tickers = extract_tickers(title)
        seen = set()
        for t in tickers:
            if t in MEGA_CAPS:
                continue
            if t in seen:
                continue
            seen.add(t)
            if t not in tally:
                tally[t] = 0
                post_map[t] = []
            tally[t] += 1
            post_map[t].append(title[:120])
    sorted_tickers = sorted(tally.items(), key=lambda x: -x[1])
    results = []
    for ticker, count in sorted_tickers:
        results.append({"ticker": ticker, "mentions": count, "posts": post_map.get(ticker, [])})
    return results


# ─── Step 2: StockTwits ───────────────────────────────────────────────────
def check_stocktwits_trending() -> set:
    data = json_get("https://api.stocktwits.com/api/2/trending/symbols.json", timeout=10)
    if not data or "symbols" not in data:
        return set()
    return {s["symbol"] for s in data["symbols"] if len(s.get("symbol", "")) <= 5}

def get_stocktwits_ticker_detail(ticker: str) -> Optional[dict]:
    data = json_get("https://api.stocktwits.com/api/2/trending/symbols.json", timeout=10)
    if not data or "symbols" not in data:
        return None
    for s in data["symbols"]:
        if s.get("symbol", "").upper() == ticker.upper():
            return {
                "ticker": s["symbol"],
                "name": s.get("title", ""),
                "watchlist_count": s.get("watchlist_count", 0),
                "trending_score": s.get("trending_score", 0),
            }
    return None


# ─── Step 3: Perplexity News ─────────────────────────────────────────────
def check_perplexity_news(ticker: str) -> Optional[dict]:
    url = f"https://www.perplexity.ai/rest/finance/timeline/{ticker}/entries"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.perplexity.ai/finance/",
    }
    data = json_get(url, headers=headers, timeout=15)
    if not data:
        return None
    entries = data if isinstance(data, list) else data.get("entries", data.get("data", []))
    if not entries:
        return None
    headlines = []
    for e in entries[:8]:
        if isinstance(e, dict):
            title = e.get("description") or e.get("title") or e.get("headline") or ""
            source = e.get("source") or e.get("site") or ""
            headlines.append({"title": title, "source": source})
    return {"headlines": headlines}


# ─── Main Pipeline ─────────────────────────────────────────────────────────
def run_pipeline() -> list[dict]:
    print("=== WSB SQUEEZE SPOTTER ===", file=sys.stderr)
    print(f"Time: {datetime.now(timezone.utc).isoformat()}", file=sys.stderr)
    print(file=sys.stderr)

    # Step 1
    print("─── Step 1: WSB Ticker Scan ───", file=sys.stderr)
    posts = fetch_wsb_rss(25)
    if not posts:
        print("No WSB posts available.", file=sys.stderr)
        return []
    ticker_counts = count_ticker_mentions(posts)
    print(f"  Tickers found: {len(ticker_counts)}", file=sys.stderr)
    for tc in ticker_counts[:10]:
        print(f"    {tc['ticker']}: {tc['mentions']}x — {tc['posts'][0][:60] if tc['posts'] else ''}", file=sys.stderr)
    print(file=sys.stderr)
    flagged = [tc for tc in ticker_counts if tc["mentions"] >= 1]
    if not flagged:
        print("No tickers with mentions.", file=sys.stderr)
        return []
    print(f"  Flagged ({len(flagged)}): {', '.join(t['ticker'] for t in flagged)}", file=sys.stderr)
    print(file=sys.stderr)

    # Step 2
    print("─── Step 2: StockTwits ───", file=sys.stderr)
    trending = check_stocktwits_trending()
    print(f"  StockTwits trending tickers: {len(trending)}", file=sys.stderr)
    step2_results = []
    for tc in flagged:
        ticker = tc["ticker"]
        is_trending = ticker in trending
        detail = get_stocktwits_ticker_detail(ticker)
        status = "TRENDING" if is_trending else "NOT trending"
        watch = f", watchlist={detail['watchlist_count']:,}" if detail else ""
        print(f"  {ticker}: {status}{watch}", file=sys.stderr)
        if is_trending or (detail and detail.get("watchlist_count", 0) > 1000):
            step2_results.append({
                "ticker": ticker,
                "mentions": tc["mentions"],
                "posts": tc["posts"],
                "stocktwits_trending": is_trending,
                "stocktwits_detail": detail or {"watchlist_count": 0},
            })
    if not step2_results:
        print("  None confirmed by StockTwits.", file=sys.stderr)
        return []
    print(file=sys.stderr)

    # Step 3
    print("─── Step 3: Perplexity News ───", file=sys.stderr)
    confirmed = []
    for item in step2_results:
        ticker = item["ticker"]
        print(f"  {ticker}: checking news...", file=sys.stderr)
        news = check_perplexity_news(ticker)
        if news and news["headlines"]:
            item["headlines"] = news["headlines"]
            print(f"    Found {len(news['headlines'])} headlines", file=sys.stderr)
            for h in news["headlines"][:3]:
                print(f"      • {h['title'][:90]}", file=sys.stderr)
        else:
            item["headlines"] = []
            print(f"    No news headlines available", file=sys.stderr)
        confirmed.append(item)
    print(file=sys.stderr)

    # Summary
    output = {
        "status": "alert",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "signals": [],
        "summary": "No signals detected"
    }
    
    for item in confirmed:
        ticker = item["ticker"]
        wl = item["stocktwits_detail"].get("watchlist_count", 0) if item["stocktwits_detail"] else 0
        headline_count = len(item.get("headlines", []))
        output["signals"].append({
            "ticker": ticker,
            "wsb_mentions": item["mentions"],
            "stocktwits_watchlist": wl,
            "headlines": [h["title"] for h in item.get("headlines", [])]
        })
        print(f"  {ticker}: {item['mentions']} WSB mentions | StockTwits watchlist {wl:,} | {headline_count} news headlines", file=sys.stderr)
    
    return confirmed

def main():
    parser = argparse.ArgumentParser(description="WSB Squeeze Spotter")
    parser.add_argument("--ticker", help="Manually check a specific ticker")
    parser.add_argument("--test", action="store_true", help="Self-test")
    args = parser.parse_args()

    if args.test:
        print(json.dumps({
            "status": "ok",
            "script": os.path.basename(__file__),
            "steps": ["step1: wsb_rss", "step2: stocktwits", "step3: perplexity_news"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, indent=2))
        return

    if args.ticker:
        ticker = args.ticker.upper().strip()
        print(f"Manual check: {ticker}", file=sys.stderr)
        st = get_stocktwits_ticker_detail(ticker)
        st_info = {"watchlist_count": st["watchlist_count"], "name": st.get("name","")} if st else {"watchlist_count": 0}
        trending = check_stocktwits_trending()
        st_info["trending"] = ticker in trending
        news = check_perplexity_news(ticker)
        st_info["headlines"] = news["headlines"] if news else []
        output = {"ticker": ticker, "stocktwits": st_info}
        print(json.dumps(output, indent=2, default=str))
        return

    results = run_pipeline()
    
    if results:
        output = {
            "status": "alert",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "signals": [
                {
                    "ticker": r["ticker"],
                    "wsb_mentions": r["mentions"],
                    "stocktwits_watchlist": r["stocktwits_detail"].get("watchlist_count", 0) if r["stocktwits_detail"] else 0,
                    "headlines": [h["title"] for h in r.get("headlines", [])]
                }
                for r in results
            ],
            "summary": f"Found {len(results)} signal(s)"
        }
    else:
        output = {
            "status": "clean",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "signals": [],
            "summary": "No signals detected"
        }
    
    print(json.dumps(output, indent=2, default=str))

if __name__ == "__main__":
    main()
