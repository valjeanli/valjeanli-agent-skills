---
name: wsb-squeeze-spotter
description: "Use when detecting meme stock / short squeeze candidates from WSB post titles, cross-checked with StockTwits and confirmed via Perplexity news."
version: 1.3.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [meme-stock, short-squeeze, wsb, stocktwits, reddit]
    related_skills: []
---

# WSB Squeeze Spotter

Four-step pipeline to detect the next meme stock squeeze (steps 1-3 detect, step 4 alerts):

1. **WSB RSS** — pull `/new/.rss`, count ticker mentions in post titles
2. **StockTwits** — validate flagged tickers are trending with retail momentum
3. **Perplexity News** — confirm a catalyst exists (meme-stock narrative)

## When to Use

- Detecting meme stock / short squeeze candidates early
- Running as a recurring cron job every 15 minutes
- Manual check on a specific ticker

## Data Sources

| Source | Endpoint | Use |
|---|---|---|
| Reddit RSS | `www.reddit.com/r/wallstreetbets/new/.rss` | Post titles, timestamps, ticker mentions |
| Google News RSS (fallback) | `news.google.com/rss/search?q=wallstreetbets+site:reddit.com` | WSB headlines when Reddit RSS is rate-limited |
| StockTwits | `api.stocktwits.com/api/2/trending/symbols.json` | Trending tickers + watchlist counts |
| StockTwits | `api.stocktwits.com/api/2/streams/symbol/{TICKER}.json` | Per-ticker message activity |
| Perplexity | `perplexity.ai/rest/finance/timeline/{TICKER}/entries` | News headlines for catalyst confirmation |

See `references/api-endpoints.md` for detailed response structures and known quirks for each API.

## Pipeline — Mandatory Steps

The agent running these steps MUST execute ALL 4 steps when signals are found.

### Step 0 — Before Running

Ensure Himalaya is in PATH. The binary may be installed at `~/.local/bin/himalaya` while `~/.local/bin` is not on the default PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
which himalaya  # verify
```

Check that `~/.config/himalaya/config.toml` exists with Gmail folder aliases (especially `[Gmail]/Sent Mail` for the sent folder) and that the password auth command is set correctly. Credentials live in `/opt/data/.env` under `EMAIL_*` keys.

### Step 1 — WSB Ticker Scan

Pull the 25 newest posts from the WSB RSS feed. Extract stock tickers from post titles (any 2-5 uppercase letter word that isn't a common English word or WSB slang). Tally mentions. Flag any ticker found (no minimum mention threshold).

Output: `{ticker: "WEN", mentions: 2, posts: ["title1", "title2", ...]}`

### Step 2 — StockTwits Cross-Check

For each flagged ticker, check StockTwits:
- Is it in the **trending tickers** list?
- What's the **watchlist count**? (higher = more retail interest)

A ticker passing WSB mentions (any count) AND StockTwits trending is the signal.

### Step 3 — Perplexity News Confirmation

Search Perplexity finance timeline for recent headlines about the ticker. Look for meme-stock related language:
- "meme stock", "short squeeze", "WallStreetBets", "retail traders", "Reddit"
- Management change, activist investor, or turnaround narrative

If at least one headline confirms the meme-stock narrative, it's a confirmed signal.

### Step 4 — Email Alert (if signals found)

When Step 3 produces confirmed signals (status: `"alert"`), send an email alert via Himalaya:

```bash
# Compose the email body to a temp file
cat << 'EMAIL' > /tmp/wsb-alert.txt
From: sender@example.com
To: recipient@example.com
Subject: 🚨 WSB Squeeze Spotter Alert — N signals detected (TICKER1, TICKER2, ...)

[Full signal details here — ticker, WSB mentions, watchlist count, headlines]
EMAIL

# Send via Himalaya
export PATH="$HOME/.local/bin:$PATH"
cat /tmp/wsb-alert.txt | himalaya template send

# Verify in sent folder
himalaya envelope list --folder "[Gmail]/Sent Mail" --page 1 --page-size 3
```

Key details:
- **Recipient** — from `EMAIL_ALLOWED_USERS` in `/opt/data/.env`, or self (check the env var)
- **From** — `EMAIL_ADDRESS` from `/opt/data/.env`
- **Cleanup** — remove the temp file after sending: `rm /tmp/wsb-alert.txt`
- **Verification** — Always verify the email landed in Sent Mail; don't assume success from exit code alone

**⚠️ SMTP vs IMAP split pitfall** — `himalaya template send` does SMTP delivery first, then IMAP save-to-sent. If IMAP auth fails (stale app password), the email was **still delivered via SMTP** but the command exits non-zero. Do NOT retry on non-zero exit without checking stderr: an IMAP-only error (contains `cannot authenticate to IMAP server` or `Invalid credentials`) means the send actually worked. Only retry on SMTP errors (`cannot send message`). When IMAP auth fails, you also cannot verify via Sent Mail lookup — instead, confirm by other means (recipient inbox, web interface, or trust the SMTP success). See the `himalaya` skill's Known Pitfalls for full details.

### Alert Output

```
SIGNAL: WEN
  WSB mentions: 7 (from 25 newest posts)
  StockTwits: #1 trending, 14,042 watchlist
  Catalyst: Wendy's surges after Reddit's WallStreetBets rally (Seeking Alpha)
  Verdict: CONFIRMED meme-stock squeeze candidate
```

## Scripts

The automated pipeline runner is at `scripts/spotter.py`. A copy also lives in the orphan directory at `skills/financial-analysis/wsb-squeeze-spotter/scripts/spotter.py` (supporting files split during a previous reorganization — see Pitfalls below).

### Run full pipeline

```bash
cd /opt/data
python3 scripts/spotter.py
```

### Manual ticker check

```bash
python3 scripts/spotter.py --ticker WEN
```

### Self-test

```bash
python3 scripts/spotter.py --test
```

The script outputs JSON to stdout (parsable) and logs to stderr. The JSON shape:

| Key | Type | Description |
|-----|------|-------------|
| `status` | string | `"alert"` (signals found) or `"clean"` (none) |
| `signals` | array | One entry per confirmed ticker |
| `signals[].ticker` | string | Stock ticker |
| `signals[].wsb_mentions` | int | Mention count in 25 newest WSB posts |
| `signals[].stocktwits_watchlist` | int | Watchlist count on StockTwits |
| `signals[].headlines` | array | Confirming news headlines |
| `summary` | string | Human-readable summary |

### Post to Typefully (alternative to email)

The script at `scripts/post_typefully.py` (in the orphan directory) posts signals to Typefully — used for social-media-format deliveries.

## Common Pitfalls

1. **RSS feed rate limits** — Reddit returns HTTP 429 after ~5 rapid requests (~1 minute window). At 15-min cron intervals this is safe. The script falls back to Google News RSS when Reddit is unavailable — this returns WSB-related headlines (no post URLs or timestamps, but tickers are still extractable). Full cooldown from a 429 takes 30-60 seconds.

2. **Himalaya not in PATH** — `himalaya` binary is commonly installed at `~/.local/bin/himalaya` but `~/.local/bin` is NOT on the default PATH in many Hermes environments. Always run `export PATH="$HOME/.local/bin:$PATH"` before calling himalaya. Verify with `which himalaya`.

3. **Himalaya config password auth** — The password auth command in `~/.config/himalaya/config.toml` must output the password to stdout. For Hermes setups where credentials are in `/opt/data/.env`, the helper script at `skills/email/himalaya/scripts/hermes-gateway-email-pass.sh` reads `EMAIL_PASSWORD` from the `.env` file. A simpler alternative for cron jobs: use `echo <password>` directly in the auth.cmd (less secure but works non-interactively). Gmail folder aliases must be set for `[Gmail]/Sent Mail`, `[Gmail]/Drafts`, `[Gmail]/Trash` — without these, save-to-sent fails silently after SMTP succeeds.

4. **False positives** — Common WSB/Reddit acronyms like "AMA" (Ask Me Anything), "CMV" (Change My View), and "OC" (Original Content) match 2-3 letter uppercase patterns and are excluded via the stop-word list. Real tickers that happen to be common words (e.g., WEN, NOW, BIG) are also handled with the stop list — if a real ticker is genuinely mentioned, it still passes through.

5. **StockTwits API quirks** — The `bullish` field in message objects is always `None` in API v2 (not True/False). Use `watchlist_count` as the primary signal — higher = more retail interest. Large caps (MSFT, AAPL) are excluded.

6. **Perplexity API** — This is an unofficial endpoint that may change. Always fall back to the `description` field if `title`/`headline` is empty. The response is a JSON array of entry objects, each with `ticker`, `description`, and `last_modified` fields.

7. **Split/orphan skill directories** — The SKILL.md lives at `skills/wsb-squeeze-spotter/SKILL.md` but supporting files (scripts, references) were previously placed under `skills/financial-analysis/wsb-squeeze-spotter/` which has no SKILL.md. After any agent-visible reorganization, update the SKILL.md's paths and call `skill_manage(action='write_file')` to move supporting files into the correct skill directory. See the `references/` and `scripts/` subdirectories under this skill's directory.

8. **Verification**
   - Run `python3 scripts/spotter.py --test` to validate the script.
   - Test the full pipeline with `python3 scripts/spotter.py`.
   - Manually check a ticker with `python3 scripts/spotter.py --ticker WEN`.

