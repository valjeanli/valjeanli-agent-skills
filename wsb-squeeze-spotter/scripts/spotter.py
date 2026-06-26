#!/usr/bin/env python3
"""
WSB Squeeze Spotter — 4-step pipeline:
1. WSB RSS feed → extract tickers from titles → find most mentioned
2. StockTwits → validate flagged ticker is trending
3. Perplexity news → confirm meme-stock catalyst
4. GitHub → upload <SYMBOL>_<yyyymmdd>.txt to valjeanli/trading-hub/alert (skip if exists)
"""

import argparse
import base64
import json
import os
import re
import sys
import urllib.request
import urllib.error
from typing import Optional
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

# ─── Constants ────────────────────────────────────────────────────────────

def _load_env_file():
    """Auto-load env vars from /data/.env if not already set."""
    env_path = "/data/.env"
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                if k and v and k not in os.environ:
                    os.environ[k] = v

_load_env_file()

GITHUB_REPO = "valjeanli/trading-hub"
GITHUB_ALERT_PATH = "alert"
GITHUB_API_BASE = "https://api.github.com"

# EDT offset (UTC-4 during daylight saving time)
EDT_OFFSET = timedelta(hours=-4)

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
    "QQQ","DIA","IWM","ARKK","SPX","VIX","RH","FDX",
}

MEGA_CAPS = {"AAPL","MSFT","GOOG","GOOGL","AMZN","META","NVDA","TSLA","BRK","JPM","V","MA","UNH","HD","DIS","NFLX","ADBE","CRM","INTC","AMD","PYPL","BA"}

MEME_KEYWORDS = {
    "meme stock", "meme-stock", "meme stocks",
    "short squeeze", "short-squeeze", "squeeze",
    "wallstreetbets", "wall street bets", "wsb",
    "retail traders", "retail investors", "retail trader",
    "reddit", "r/wallstreetbets",
    "pump and dump", "pump", "dump",
    "yolo", "diamond hands", "diamond-hand",
    "to the moon", "moon", "rocket",
    "apes", "ape", "ape strong",
    "bag holder", "bagholder",
    "gamma squeeze", "gamma ramp",
    "short interest", "short float",
}

LLM_CONFIDENCE_THRESHOLD = 0.6

TICKER_COMPANY = {
    "MU": "Micron Technology", "WEN": "Wendy's", "GME": "GameStop",
    "AMC": "AMC Entertainment", "BB": "BlackBerry", "NOK": "Nokia",
    "PLTR": "Palantir", "RIVN": "Rivian", "LCID": "Lucid",
    "COIN": "Coinbase", "HOOD": "Robinhood", "AFRM": "Affirm", "SOFI": "SoFi",
}


def extract_tickers(text: str) -> list[str]:
    candidates = re.findall(r'\$?[A-Z]{2,5}\b', text)
    return [c.lstrip("$") for c in candidates if c.lstrip("$") not in TICKER_STOP]


# ─── HTTP helpers ──────────────────────────────────────────────────────────

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

def http_get(url: str, headers: dict = None, timeout: int = 15) -> Optional[str]:
    hdrs = {"User-Agent": USER_AGENTS[0]}
    if headers:
        hdrs.update(headers)
    try:
        req = urllib.request.Request(url, headers=hdrs)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if resp.status == 429:
                return None
            return body
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
        return None
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return None
    entries = root.findall("atom:entry", NS)
    posts = []
    for e in entries:
        title = e.find("atom:title", NS)
        if title is not None and title.text:
            posts.append({"title": title.text.strip(), "author": "", "url": "", "updated": ""})
    return posts

def count_ticker_mentions(posts: list[dict]) -> list[dict]:
    tally, post_map = {}, {}
    for post in posts:
        seen = set()
        for t in extract_tickers(post["title"]):
            if t in MEGA_CAPS or t in seen:
                continue
            seen.add(t)
            tally[t] = tally.get(t, 0) + 1
            post_map.setdefault(t, []).append(post["title"][:120])
    return [{"ticker": t, "mentions": c, "posts": post_map.get(t, [])}
            for t, c in sorted(tally.items(), key=lambda x: -x[1])]


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
            return {"ticker": s["symbol"], "name": s.get("title", ""),
                    "watchlist_count": s.get("watchlist_count", 0)}
    return None


# ─── Step 3: Perplexity + Validation ──────────────────────────────────────

def check_perplexity_news(ticker: str) -> Optional[dict]:
    url = f"https://www.perplexity.ai/rest/finance/timeline/{ticker}/entries"
    data = json_get(url, headers={"Referer": "https://www.perplexity.ai/finance/"}, timeout=15)
    if not data:
        return None
    entries = data if isinstance(data, list) else data.get("entries", [])
    return {"headlines": [{"title": e.get("description") or e.get("title") or "", "source": e.get("source", "")}
                           for e in entries[:8] if isinstance(e, dict)]}

def contains_meme_keyword(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in MEME_KEYWORDS)

def check_meme_narrative(ticker: str, headlines: list[dict]) -> tuple[bool, list[dict], str]:
    """Check meme narrative via Perplexity headlines + keyword match only. No fallback."""
    if headlines:
        confirmed = [h for h in headlines if contains_meme_keyword(h["title"])]
        if confirmed:
            return True, confirmed, "perplexity+keywords"
    return False, [], "none"


# ─── Step 4: GitHub Upload ────────────────────────────────────────────────

def get_edt_date() -> str:
    return (datetime.now(timezone.utc) + EDT_OFFSET).strftime("%Y%m%d")

def github_api_request(path: str, method: str = "GET", data: dict = None, token: str = None) -> Optional[dict]:
    url = f"{GITHUB_API_BASE}/{path}"
    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "wsb-squeeze-spotter"}
    if token:
        headers["Authorization"] = f"token {token}"
    body = json.dumps(data).encode("utf-8") if data else None
    if body:
        headers["Content-Type"] = "application/json"
    try:
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return None if e.code == 404 else None
    except Exception:
        return None

def check_file_exists(ticker: str, date_str: str, token: str) -> bool:
    """Check if ANY file with base name {ticker}_{date} exists (any extension)."""
    base_name = f"{ticker}_{date_str}"
    result = github_api_request(f"repos/{GITHUB_REPO}/contents/{GITHUB_ALERT_PATH}", token=token)
    if result is None:
        return False
    return any(isinstance(item, dict) and item.get("name", "").startswith(base_name + ".")
               for item in result)

def format_alert_content(ticker: str, signal: dict, date_str: str) -> str:
    company = TICKER_COMPANY.get(ticker, ticker)
    mentions = signal.get("wsb_mentions", signal.get("mentions", 0))
    watchlist = signal.get("stocktwits_watchlist", 0)
    posts = signal.get("posts", [])[:2]
    headlines = signal.get("headlines", [])
    source = signal.get("meme_source", "unknown")
    highlights = []
    if posts:
        highlights.append(f"Reddit: {'; '.join(posts)}")
    if headlines:
        h = headlines[0] if isinstance(headlines[0], str) else headlines[0].get("title", "")
        highlights.append(f"News: {h}")
    hl_text = "\n".join(f"- {h}" for h in highlights) if highlights else "- No highlights"
    ts = (datetime.now(timezone.utc) + EDT_OFFSET).strftime("%Y-%m-%d %H:%M:%S EDT")
    return f"🚨 Meme Alert: {company} ({ticker})\nWSB mentions: {mentions} | StockTwits watchlist: {watchlist:,}\n{hl_text}\nSource: {source}\nGenerated: {ts}\n"

def upload_to_github(ticker: str, signal: dict, token: str) -> bool:
    date_str = get_edt_date()
    filename = f"{ticker}_{date_str}.txt"
    if check_file_exists(ticker, date_str, token):
        print(f"  [github] {filename} already exists — skipping", file=sys.stderr)
        return False
    content_b64 = base64.b64encode(format_alert_content(ticker, signal, date_str).encode()).decode()
    result = github_api_request(f"repos/{GITHUB_REPO}/contents/{GITHUB_ALERT_PATH}/{filename}",
                                method="PUT", data={"message": f"Add WSB alert: {ticker}", "content": content_b64}, token=token)
    if result and "content" in result:
        print(f"  [github] Uploaded {filename}", file=sys.stderr)
        return True
    print(f"  [github] Failed to upload {filename}", file=sys.stderr)
    return False


# ─── Main Pipeline ─────────────────────────────────────────────────────────

def run_pipeline() -> list[dict]:
    print("=== WSB SQUEEZE SPOTTER ===", file=sys.stderr)
    posts = fetch_wsb_rss(25)
    if not posts:
        return []
    ticker_counts = count_ticker_mentions(posts)
    flagged = [tc for tc in ticker_counts if tc["mentions"] >= 1]
    if not flagged:
        return []

    trending = check_stocktwits_trending()
    step2 = []
    for tc in flagged:
        t = tc["ticker"]
        detail = get_stocktwits_ticker_detail(t)
        if t in trending or (detail and detail.get("watchlist_count", 0) > 1000):
            step2.append({**tc, "stocktwits_detail": detail or {"watchlist_count": 0}})
    if not step2:
        return []

    confirmed = []
    for item in step2:
        news = check_perplexity_news(item["ticker"])
        headlines = news["headlines"] if news else []
        is_valid, meme_hl, source = check_meme_narrative(item["ticker"], headlines)
        if is_valid:
            item["headlines"] = meme_hl
            item["meme_source"] = source
            confirmed.append(item)
    return confirmed


def main():
    parser = argparse.ArgumentParser(description="WSB Squeeze Spotter")
    parser.add_argument("--ticker", help="Manually check a specific ticker")
    parser.add_argument("--test", action="store_true", help="Self-test")
    args = parser.parse_args()

    if args.test:
        print(json.dumps({"status": "ok", "script": os.path.basename(__file__),
                          "steps": ["wsb_rss", "stocktwits", "perplexity+llm", "github_upload"],
                          "timestamp": datetime.now(timezone.utc).isoformat()}, indent=2))
        return

    if args.ticker:
        ticker = args.ticker.upper().strip()
        st = get_stocktwits_ticker_detail(ticker)
        news = check_perplexity_news(ticker)
        headlines = news["headlines"] if news else []
        is_valid, meme_hl, source = check_meme_narrative(ticker, headlines)
        print(json.dumps({"ticker": ticker, "stocktwits": st, "meme_confirmed": is_valid,
                          "meme_source": source, "headlines": meme_hl}, indent=2, default=str))
        return

    results = run_pipeline()
    output = {
        "status": "alert" if results else "clean",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "signals": [{"ticker": r["ticker"], "company": TICKER_COMPANY.get(r["ticker"], r["ticker"]),
                      "wsb_mentions": r["mentions"], "posts": r.get("posts", []),
                      "stocktwits_watchlist": r["stocktwits_detail"].get("watchlist_count", 0),
                      "headlines": [h["title"] for h in r.get("headlines", [])],
                      "meme_source": r.get("meme_source", "unknown")} for r in results],
        "summary": f"Found {len(results)} confirmed signal(s)" if results else "No signals detected",
    }

    if output["status"] == "alert":
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            for sig in output["signals"]:
                upload_to_github(sig["ticker"], sig, token)

    print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    main()
