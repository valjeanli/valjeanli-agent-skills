#!/usr/bin/env python3
"""
LLM-based meme-stock narrative validator.

Sends Perplexity news headlines to an LLM and asks whether they describe
a meme stock / short-squeeze situation driven by WSB retail traders.
"""

import json
import os
import urllib.request
import urllib.error


LLM_API_KEY = os.environ.get("OPENCODE_GO_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://opencode.ai/zen/go/v1")
LLM_MODEL = os.environ.get("LLM_VALIDATION_MODEL", "deepseek-v4-flash")


SYSTEM_PROMPT = """You are a stock market news classifier. Your job is to determine whether a set of news headlines describes a MEME STOCK or SHORT SQUEEZE situation driven by RETAIL TRADERS from Reddit's r/wallstreetbets (WSB) community.

Return JSON with this exact structure:
{
  "is_meme_squeeze": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "one sentence explaining why"
}

RULES:
- is_meme_squeeze = TRUE if headlines describe:
  * A stock being actively traded/pumped by retail traders
  * Short squeeze mechanics (high short interest, gamma squeeze)
  * WallStreetBets / Reddit-driven buying pressure
  * Meme stock mania (viral trading, diamond hands, etc.)
  
- is_meme_squeeze = FALSE if headlines describe:
  * Generic "best stocks to buy" listicles that mention Reddit
  * Normal earnings/business news about the company
  * Analyst upgrades/downgrades unrelated to retail activity
  * The ticker is mentioned but the story isn't about retail/meme trading
  * Crypto, forex, or non-equity assets

- confidence should reflect how certain you are:
  * 0.9-1.0: Clear meme/WSB language in headlines
  * 0.7-0.8: Strong retail trading signals but no explicit WSB mention
  * 0.5-0.6: Ambiguous — mentions Reddit but could be generic
  * Below 0.5: Not a meme stock situation

ONLY return the JSON object. No other text."""


def validate_with_llm(headlines: list[dict], ticker: str) -> dict:
    """
    Send headlines to LLM for meme-stock validation.
    
    Returns:
        {"is_valid": bool, "confidence": float, "reasoning": str}
    """
    if not LLM_API_KEY:
        return {"is_valid": False, "confidence": 0.0, "reasoning": "No LLM API key configured"}
    
    if not headlines:
        return {"is_valid": False, "confidence": 0.0, "reasoning": "No headlines to validate"}
    
    # Build the user message with headlines
    headline_text = "\n".join(
        f"- [{h.get('source', 'unknown')}] {h['title']}"
        for h in headlines[:8]
    )
    
    user_msg = f"""Ticker: {ticker}

Headlines:
{headline_text}

Does this describe a meme stock / short squeeze driven by WSB retail traders?"""
    
    payload = json.dumps({
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.1,
        "max_tokens": 200,
    }).encode("utf-8")
    
    url = f"{LLM_BASE_URL}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLM_API_KEY}",
    }
    
    try:
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        
        content = body["choices"][0]["message"]["content"].strip()
        
        # Parse JSON from response (handle markdown code blocks)
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        
        result = json.loads(content)
        
        return {
            "is_valid": bool(result.get("is_meme_squeeze", False)),
            "confidence": float(result.get("confidence", 0.0)),
            "reasoning": result.get("reasoning", ""),
        }
    
    except (urllib.error.URLError, json.JSONDecodeError, KeyError, Exception) as e:
        return {"is_valid": False, "confidence": 0.0, "reasoning": f"LLM call failed: {e}"}


if __name__ == "__main__":
    # Quick test
    test_headlines = [
        {"title": "GameStop surges as WallStreetBets traders pile in again", "source": "Reuters"},
        {"title": "GME short interest remains elevated at 25%", "source": "MarketWatch"},
    ]
    result = validate_with_llm(test_headlines, "GME")
    print(json.dumps(result, indent=2))
