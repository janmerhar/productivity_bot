#!/usr/bin/env python3
"""
Daily RSS → Top 10 "interesting" news (hybrid heuristic + OpenAI)
- Reads ~5 RSS feeds (≈75 items total)
- Filters for today's items and applies heuristic scoring
- Asks gpt-5-mini once to choose the top links (returns URLs only)
- Outputs a Markdown digest to stdout and saves it to ./digest.md
Requirements: see requirements.txt
ENV: OPENAI_API_KEY in your environment or .env file (python-dotenv supported)
"""

import os
from pathlib import Path
import sys
import time
import json
import datetime as dt
from email.utils import parsedate_to_datetime
from dataclasses import dataclass
from typing import List, Optional, Dict
import textwrap

import feedparser

# Optional: load .env if present
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:
    pass

try:
    from openai import OpenAI
except Exception as e:
    print(
        "The 'openai' package is missing. Install dependencies from requirements.txt",
        file=sys.stderr,
    )
    raise

# ---------------------- Configuration ----------------------
# Put your RSS feed URLs here
FEEDS = [
    "https://img.rtvslo.si/feeds/00.xml",
    "https://siol.net/feeds/latest",
    "https://www.zurnal24.si/feeds/latest",
    "https://www.24ur.com/rss",
]

# How many top articles to pick
TOP_N = 10

# Model used for the lean selection step
MODEL_SELECT = "gpt-5-mini"

# When True, include feed description + summary; set False to only use title
INCLUDE_RSS_SUMMARY = True

# Heuristic pre-filter configuration
CANDIDATE_LIMIT = 25
RECENCY_HALF_LIFE_HOURS = 24.0
RECENCY_LOOKBACK_HOURS = 96.0
KEYWORD_BOOSTS = [
    "sloven",
    "vlada",
    "government",
    "war",
    "finance",
    "econom",
    "startup",
    "technolog",
    "zdrav",
    "covid",
    "podneb",
    "weather",
]
SOURCE_BONUS = {
    "rtv slovenija": 0.2,
    "siol": 0.1,
    "zurnal24": 0.05,
    "24ur": 0.15,
}


# ---------------------- Data structures ----------------------
@dataclass
class RawItem:
    source: str
    title: str
    link: str
    published: Optional[str]
    description: Optional[str]


# ---------------------- Helpers ----------------------
def parse_rss_item(feed_title: str, entry) -> RawItem:
    title = entry.get("title") or "(no title)"
    link = entry.get("link") or ""
    published = entry.get("published") or entry.get("updated")
    # Some feeds use 'summary' or 'description' field names
    desc = entry.get("summary") or entry.get("description")
    return RawItem(
        source=feed_title or "Unknown",
        title=title.strip(),
        link=link.strip(),
        published=published,
        description=(desc.strip() if isinstance(desc, str) else None),
    )


def collect_items(feeds: List[str]) -> List[RawItem]:
    items: List[RawItem] = []
    for url in feeds:
        parsed = feedparser.parse(url)
        feed_title = parsed.feed.get("title", url)
        for entry in parsed.entries:
            items.append(parse_rss_item(feed_title, entry))
    # Dedupe by link
    seen = set()
    unique: List[RawItem] = []
    for it in items:
        key = it.link or f"{it.source}|{it.title}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(it)
    return unique


# ---------------------- OpenAI calls ----------------------
def client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY not set. Put it in your environment or in a .env file."
        )
    return OpenAI(api_key=api_key)


_SELECT_SYS = "You are an editor curating a daily top list. Return STRICT JSON only."
_SELECT_USER_TEMPLATE = """You will receive a set of news items. Pick the TOP {top_n} that are most interesting to a general audience today.
Consider breadth of topics, novelty, reliability, and geographic diversity. Avoid near-duplicates.

Return JSON with only the list of chosen links:
{{
  "links": string[]  // canonical URLs of the chosen articles, length ≤ {top_n}
}}

Items (0..{last_index}):
{items}
"""


def _clean_text(text: Optional[str]) -> str:
    if not text:
        return "(no description provided)"
    compact = " ".join(text.split())
    return textwrap.shorten(compact, width=700, placeholder="…")


def _normalize_source(source: str) -> str:
    return source.strip().lower()


def _source_bonus(source: str) -> float:
    return SOURCE_BONUS.get(_normalize_source(source), 0.0)


def _keyword_boost(text: str) -> float:
    lowered = text.lower()
    return sum(0.25 for kw in KEYWORD_BOOSTS if kw in lowered)


def _parsed_datetime(value: Optional[str]) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not parsed:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def _recency_boost(published: Optional[str]) -> float:
    parsed = _parsed_datetime(published)
    if not parsed:
        return 0.3
    now = dt.datetime.now(dt.timezone.utc)
    age_hours = max(0.0, (now - parsed).total_seconds() / 3600)
    if age_hours > RECENCY_LOOKBACK_HOURS:
        return -5.0
    if RECENCY_HALF_LIFE_HOURS <= 0:
        return 0.7
    decay = 0.7 * (0.5 ** (age_hours / RECENCY_HALF_LIFE_HOURS))
    return 0.3 + decay


def _length_bonus(text: Optional[str]) -> float:
    if not text:
        return 0.0
    length = len(text)
    if length < 120:
        return 0.05
    if length > 900:
        length = 900
    return min(0.35, length / 900.0)


def heuristic_score(raw: RawItem) -> float:
    text = f"{raw.title}\n{raw.description or ''}"
    score = 1.0
    score += _keyword_boost(text)
    score += _source_bonus(raw.source)
    score += _length_bonus(raw.description)
    score += _recency_boost(raw.published)
    return score


def pick_candidates(raw_items: List[RawItem], limit: int = CANDIDATE_LIMIT) -> List[RawItem]:
    scored = []
    for idx, raw in enumerate(raw_items):
        score = heuristic_score(raw)
        scored.append((score, -idx, raw))  # prefer earlier order on ties
    scored.sort(reverse=True, key=lambda item: item[0:2])
    pruned = [item for item in scored if item[0] > -4.0]
    selected = pruned[:limit] if limit > 0 else pruned
    return [entry[2] for entry in selected]


def filter_today_items(raw_items: List[RawItem]) -> List[RawItem]:
    if not raw_items:
        return []
    local_tz = dt.datetime.now(dt.timezone.utc).astimezone().tzinfo
    today = dt.datetime.now(local_tz).date()
    filtered: List[RawItem] = []
    for raw in raw_items:
        published_dt = _parsed_datetime(raw.published)
        if not published_dt:
            continue
        local_pub = published_dt.astimezone(local_tz)
        if local_pub.date() == today:
            filtered.append(raw)
    return filtered


def select_links(cli: OpenAI, candidates: List[RawItem], top_n: int) -> List[str]:
    if not candidates:
        return []
    lines = []
    for idx, raw in enumerate(candidates):
        desc = (
            _clean_text(raw.description)
            if INCLUDE_RSS_SUMMARY and raw.description
            else "(no description provided)"
        )
        lines.append(
            textwrap.dedent(
                f"""{idx}. Title: {raw.title}
Source: {raw.source}
Link: {raw.link}
Published: {raw.published or 'unknown'}
Details: {desc}
"""
            ).strip()
        )
    content = _SELECT_USER_TEMPLATE.format(
        top_n=top_n,
        last_index=len(candidates) - 1,
        items="\n\n".join(lines),
    )
    resp = cli.chat.completions.create(
        model=MODEL_SELECT,
        messages=[
            {"role": "system", "content": _SELECT_SYS},
            {"role": "user", "content": content},
        ],
        response_format={"type": "json_object"},
    )
    data = json.loads(resp.choices[0].message.content)
    link_list = data.get("links", []) if isinstance(data, dict) else []
    normalized_map: Dict[str, str] = {}
    for raw in candidates:
        if raw.link:
            normalized_map[raw.link.strip()] = raw.link.strip()

    chosen: List[str] = []
    for link in link_list:
        if not isinstance(link, str):
            continue
        norm = link.strip()
        if not norm:
            continue
        if norm in normalized_map and norm not in chosen:
            chosen.append(norm)
    if len(chosen) > top_n:
        chosen = chosen[:top_n]
    return chosen


# ---------------------- Output ----------------------
def to_markdown(top_links: List[str]) -> str:
    today = dt.datetime.now().strftime("%Y-%m-%d")
    lines = [f"# Top {len(top_links)} News Links — {today}", ""]
    for link in top_links:
        lines.append(f"- {link}")
    return "\n".join(lines)


# ---------------------- Main ----------------------
def main() -> int:
    start = time.time()
    print(f"Collecting feeds ({len(FEEDS)} URLs)...", file=sys.stderr)
    raw_items = collect_items(FEEDS)
    if not raw_items:
        print("No items found.", file=sys.stderr)
        return 1

    today_items = filter_today_items(raw_items)
    if not today_items:
        print("No items from today were found.", file=sys.stderr)
        return 2

    print(
        f"Collected {len(today_items)} items from today. Applying heuristic filter...",
        file=sys.stderr,
    )
    candidates = pick_candidates(today_items)
    print(
        f"Selected {len(candidates)} candidate items for LLM selection.",
        file=sys.stderr,
    )

    if not candidates:
        print("No candidates after heuristic filtering.", file=sys.stderr)
        return 3

    cli = client()
    print(f"Selecting top {TOP_N} via LLM...", file=sys.stderr)
    chosen_links = select_links(cli, candidates, TOP_N)

    if not chosen_links:
        print("LLM returned no links; falling back to heuristic top items.", file=sys.stderr)
        fallback = pick_candidates(today_items, TOP_N)
        chosen_links = [item.link for item in fallback if item.link][:TOP_N]

    md = to_markdown(chosen_links)
    out_path = Path("digest.md")
    out_path.write_text(md, encoding="utf-8")
    print(md)

    elapsed = time.time() - start
    print(
        f"\nDone in {elapsed:.1f}s. Saved digest to {out_path.resolve()}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
