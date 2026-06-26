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

Four-step pipeline to detect the next meme stock squeeze:

1. **WSB RSS** — pull `/new/.rss`, count ticker mentions in post titles
2. **StockTwits** — validate flagged tickers are trending with retail momentum
3. **Perplexity News** — confirm a catalyst exists (meme-stock narrative)
4. **GitHub Upload** — create `<SYMBOL>_<yyyymmdd>.txt` in `valjeanli/trading-hub/alert` (skip if exists)

## When to Use

- Detecting meme stock / short squeeze candidates early
- Running as a recurring cron job every 15 minutes
- Manual check on a specific ticker

## Data Sources

| Source | Endpoint | Use |
|---|---|---|
| Reddit RSS | `www.reddit.com/r/wallstreetbets/new/.rss` | Post titles, timestamps, ticker mentions |
| StockTwits | `api.stocktwits.com/api/2/trending/symbols.json` | Trending tickers + watchlist counts |
| StockTwits | `api.stocktwits.com/api/2/streams/symbol/{TICKER}.json` | Per-ticker message activity |
| Perplexity | `perplexity.ai/rest/finance/timeline/{TICKER}/entries` | News headlines for catalyst confirmation |

See `references/api-endpoints.md` for detailed response structures and known quirks for each API.

## Pipeline

### Step 1 — WSB Ticker Scan

Pull the 25 newest posts from the WSB RSS feed. Extract stock tickers from post titles (any 2-5 uppercase letter word that isn't a common English word or WSB slang). Tally mentions. Flag any ticker found (no minimum mention threshold).

Output: `{ticker: "WEN", mentions: 2, posts: ["title1", "title2", ...]}`

### Step 2 — StockTwits Cross-Check

For each flagged ticker, check StockTwits:
- Is it in the **trending tickers** list?
- What's the **watchlist count**? (higher = more retail interest)

A ticker passing WSB mentions (any count) AND StockTwits trending is the signal.

### Step 3 — Perplexity News Confirmation + LLM Validation

Search Perplexity finance timeline for recent headlines about the ticker. Validate with two layers:

**Layer 1 — Keyword pre-filter:** Fast check for meme-stock language in headlines:
- "meme stock", "short squeeze", "WallStreetBets", "retail traders", "Reddit"
- If keywords found, proceed to LLM validation.

**Layer 2 — LLM validation (final arbiter):** Sends headlines to an LLM (OpenAI-compatible API) with a classification prompt asking:
> "Does this describe a meme stock / short squeeze driven by WSB retail traders?"

The LLM returns `is_meme_squeeze: true/false` with a confidence score (0.0-1.0). Signal passes only if:
- `is_meme_squeeze = true` AND
- `confidence >= 0.6`

This catches false positives that keyword matching misses (e.g. "squeeze" in a non-meme context) and confirms edge cases where keywords are absent but the narrative is clearly meme-driven.

If Perplexity returns no data, the ticker fails validation — no fallback.

LLM config via env vars:
- `LLM_API_KEY` — API key (defaults to `OPENCODE_GO_API_KEY`)
- `LLM_BASE_URL` — API endpoint (default: `https://opencode.ai/zen/go/v1`)
- `LLM_VALIDATION_MODEL` — model name (default: `gpt-4o-mini`)
- `LLM_CONFIDENCE_THRESHOLD` — minimum confidence (default: `0.6`)

### Step 4 — GitHub Upload

If any signals pass Steps 1-3, create a text file in the GitHub repo `valjeanli/trading-hub/alert/` and commit it.

**File naming:** `<SYMBOL>_<yyyymmdd>.txt` where yyyymmdd is today's date in EDT (Eastern Daylight Time).

**Skip rule:** If a file with the same base name already exists (any extension), skip the upload — do not overwrite. For example, if `WEN_20260626.done` exists, do not upload `WEN_20260626.txt`.

**Process:**
1. Use GitHub API to check if `alert/<SYMBOL>_<date>.txt` exists
2. If exists → skip (print message, move to next ticker)
3. If not → create the file with alert content and commit via GitHub API

The script uses `GITHUB_TOKEN` env var for authentication. The file content includes:
```
🚨 Meme Alert: <Company Name> (<SYMBOL>)
WSB mentions: <N> | StockTwits watchlist: <N>
- Reddit: <post highlights>
- News: <headline>
Source: <validation source>
Generated: <timestamp EDT>
```

Example filenames:
- `WEN_20260625.txt`
- `GME_20260625.txt`

## Reference Script

The automated implementation lives at `scripts/spotter.py`. Usage:

```bash
python3 scripts/spotter.py              # full pipeline + GitHub upload
python3 scripts/spotter.py --ticker WEN  # manual ticker check
python3 scripts/spotter.py --test        # self-test
```

Requires `GITHUB_TOKEN` env var with `repo` scope for GitHub uploads.

## Common Pitfalls

0. **Cron env vars not loaded** — `scripts/spotter.py` reads `GITHUB_TOKEN` and `OPENCODE_GO_API_KEY` from `os.environ`. In cron execution, these are NOT auto-exported. The script auto-loads them from `/data/.env` as a fallback (lines at top of `main()`). If the script is run outside cron, ensure the env is sourced: `source /data/.env && python3 scripts/spotter.py`. Without `GITHUB_TOKEN`, Steps 1-3 still run but Step 4 (GitHub upload) silently skips — no error, just no file created.

1. **RSS feed rate limits** — Reddit returns HTTP 429 after ~5 rapid requests (~1 minute window). At 15-min cron intervals this is safe. Full cooldown from a 429 takes 30-60 seconds.

2. **False positives** — Common WSB/Reddit acronyms like "AMA" (Ask Me Anything), "CMV" (Change My View), and "OC" (Original Content) match 2-3 letter uppercase patterns and are excluded via the stop-word list. Real tickers that happen to be common words (e.g., WEN, NOW, BIG) are also handled with the stop list — if a real ticker is genuinely mentioned, it still passes through.

3. **StockTwits API quirks** — The `bullish` field in message objects is always `None` in API v2 (not True/False). Do not use it for sentiment calculation. Use `watchlist_count` as the primary signal — higher = more retail interest. Large caps (MSFT, AAPL) trend constantly and are excluded.

4. **Perplexity API** — This is an unofficial endpoint that may change. The `title` and `headline` fields are often empty strings — always fall back to the `description` field which contains the full news text. The response is a JSON array of entry objects, each with `ticker`, `description`, and `last_modified` fields.

5. **GitHub Actions: commit detection** — `git diff --name-only` only shows tracked file changes. When `mv` renames a file (`.txt` → `.done`), the new file is untracked and git won't see it. Use `ls alert/*.done` to detect renamed files instead.

6. **GitHub Actions: token scope** — Pushing workflow files (`.github/workflows/*.yml`) requires the `workflow` scope on the GITHUB_TOKEN. If the push is rejected with "refusing to allow a Personal Access Token to create or update workflow", the token needs this scope added.

5. **Extension-agnostic file matching** — When checking if an alert file exists, match by base name (`TICKER_YYYYMMDD`) not exact filename. A `.done` file (sent to ntfy) should block a `.txt` upload for the same ticker+date. See `check_file_exists()` in `scripts/spotter.py` for the pattern.

6. **GitHub Actions token scope** — Pushing workflow files (`.github/workflows/*.yml`) requires `workflow` scope on the GitHub token. If push is rejected with "refusing to allow a Personal Access Token to create or update workflow", run `gh auth refresh -s workflow` or create the file manually via GitHub web UI.

7. **Cron job skill installation** — Cron jobs load skills from the local skills directory (`~/.hermes/skills/` or `/data/skills/`), NOT from GitHub. After pushing a skill update to a repo, you must also install it locally for cron jobs to use the latest version. Copy files manually or use `hermes skills install`.

8. **Cron skill-not-found race condition** — The cron runner checks skill existence at job creation time AND at run time. If the skill file was recently moved, deleted, or recreated (e.g. during a `skill_manage` operation), the cron runner may fail with `skill not found, skipping` even if the file exists moments later. Symptom: the agent runs the prompt WITHOUT the skill's instructions loaded, producing generic/incomplete output. Fix: after any skill file manipulation, wait 30s before triggering cron, or manually re-trigger the job after confirming `skill_view(name='wsb-squeeze-spotter')` returns content.

9. **Cron `deliver: "local"` hides output** — When the cron job's delivery mode is `local`, results are saved to `/data/cron/output/<job_id>/` but NOT pushed to any chat channel. The user sees nothing. To get results delivered: set `deliver` to `'origin'` (current chat), `'all'` (all connected channels), or a specific platform target like `'telegram:<chat_id>'`. Check with `cronjob(action='list')` and update if needed.

10. **Subagent timing in cron sessions** — When the agent dispatches subagents via `delegate_task` in a cron job, the cron session may end before subagents return results. The agent's final response gets captured incomplete. Mitigation: either (a) avoid subagents in cron prompts — run the pipeline steps sequentially inline, or (b) ensure the prompt instructs the agent to wait for subagent results before responding.

## Cron Job Setup

To run as a recurring Hermes cron job:

```bash
# Create daily at 9am UTC — results delivered to current chat
hermes cron create --name wsb-squeeze-spotter-daily \
  --schedule "0 9 * * *" \
  --prompt "Run the WSB Squeeze Spotter pipeline. Report findings." \
  --skills wsb-squeeze-spotter \
  --deliver origin
```

**⚠️ Delivery mode matters:** By default, cron jobs use `deliver: "local"` which saves output to files only — you won't see it in chat. Always set `--deliver origin` (or `'all'` for all channels) when you want results pushed to you. Without this, the only way to see output is: `cat /data/cron/output/<job_id>/*.md`

**Pitfall: Cron jobs require the gateway to be running.** The cron ticker only executes when `hermes gateway` is active. If you trigger a cron job manually and it doesn't run, check `ps aux | grep hermes gateway` — the gateway process must be alive. Start it with `hermes gateway start`.

Monitor cron runs in `/data/logs/agent.log`:
```bash
tail -f /data/logs/agent.log | grep -i cron
```

## Verification

- [ ] `python3 scripts/spotter.py --test`
- [ ] `python3 scripts/spotter.py` — runs full pipeline
- [ ] `python3 scripts/spotter.py --ticker WEN` — manual check
