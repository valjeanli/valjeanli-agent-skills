# API Endpoints Reference

## Reddit RSS (`/r/wallstreetbets/new/.rss`)

**URL:** `https://www.reddit.com/r/wallstreetbets/new/.rss?limit=N`

**Format:** Atom XML (`xml.etree.ElementTree` with namespace `{"atom": "http://www.w3.org/2005/Atom"}`)

**Fields per entry:**

| Field | Path | Notes |
|---|---|---|
| title | `atom:title` | The post title — primary source for ticker extraction |
| author | `atom:author/atom:name` | Reddit username |
| url | `atom:link/@href` | Link to the Reddit post |
| updated | `atom:updated` | ISO 8601 timestamp |

**Rate limits:** HTTP 429 after ~5 rapid requests (~1 min window). At 15-min cron intervals this is safe. Cooldown takes 30-60s.

**Fallback:** Google News RSS → `news.google.com/rss/search?q=wallstreetbets+site:reddit.com`. Returns WSB-related headlines (no post URLs or timestamps), parsed via regex `<title>(.*?)</title>`. Skip first 2 entries (feed metadata).

---

## StockTwits API v2

### Trending Symbols

**URL:** `https://api.stocktwits.com/api/2/trending/symbols.json`

**Response structure:**
```json
{
  "symbols": [
    {
      "symbol": "WEN",
      "title": "Wendy's Company",
      "watchlist_count": 14102,
      "trending_score": 87.5
    }
  ]
}
```

**Known quirks:**
- `bullish` field in message objects is always `None` in API v2 (not True/False). Do not use for sentiment.
- `watchlist_count` is the primary signal — higher = more retail interest.
- Large caps (MSFT, AAPL, GOOG, AMZN, META, NVDA, TSLA) trend constantly — filter them out with MEGA_CAPS set.
- Symbols returned may include non-stock items; only keep those with `len(symbol) <= 5`.

### Symbol Stream

**URL:** `https://api.stocktwits.com/api/2/streams/symbol/{TICKER}.json`

Returns recent messages for a ticker. `message_count` in the response indicates activity level but is not a reliable signal — use `watchlist_count` from the trending endpoint instead.

---

## Perplexity Finance Timeline (Unofficial)

**URL:** `https://www.perplexity.ai/rest/finance/timeline/{TICKER}/entries`

**Headers required:**
```
Accept: application/json, text/plain, */*
Referer: https://www.perplexity.ai/finance/
```

**Response structure (JSON array):**
```json
[
  {
    "ticker": "WEN",
    "description": "Full news article text here...",
    "title": "",
    "headline": "",
    "source": "Seeking Alpha",
    "site": "seekingalpha.com",
    "last_modified": "2026-06-24T15:30:00Z"
  }
]
```

**Known quirks:**
- `title` and `headline` fields are often empty strings — always fall back to `description`.
- `description` contains the full news article text (not just a snippet).
- Response is a raw JSON array of entry objects. Some endpoints wrap in `{"entries": [...]}` or `{"data": [...]}` — always handle both shapes.
- Unofficial endpoint — may change without notice. Handle failures gracefully.
- Headlines referencing "meme stock", "short squeeze", "WallStreetBets", "retail traders", "Reddit", management change, activist investor, or turnaround narrative are signals.

---

## Ticker Extraction Patterns

**Regex:** `\$?[A-Z]{2,5}\b`

**Stop words:** ~120 entries covering English articles (THE, AND, FOR), WSB slang (YOLO, FOMO, LFG), finance terms (EPS, PE, EV, ROI), tech terms (CPU, GPU, API, JSON), common 2-letter words (AM, PM, IN, AT, BY), and mega caps.

**Known false-positive patterns seen in the wild:**
| Pattern | Source | Why it's excluded |
|---|---|---|
| AMA | Reddit posts | "Ask Me Anything" - common WSB post format |
| CMV | Reddit posts | "Change My View" - common discussion format |
| OC | Reddit posts | "Original Content" - common post tag |
| VADER | Sentiment posts | "VADER sentiment analysis" - NLP library name |
| WEN | Real ticker | Wendy's — genuinely mentioned but also a common word. Allowed through (it's a real ticker) |
