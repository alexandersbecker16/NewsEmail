"""Fetch top headlines from trustworthy RSS sources."""

from __future__ import annotations

import html
import re
from typing import Any

import feedparser
import requests

# Wire services and established business desks. Order is a tie-break only.
SOURCES = [
    {
        "name": "Reuters",
        "url": "https://news.google.com/rss/search?q=when:2d+site:reuters.com+(inflation+OR+%22interest+rate%22+OR+%22Federal+Reserve%22+OR+ECB+OR+recession+OR+tariff+OR+%22oil%22+OR+GDP+OR+%22central+bank%22)&hl=en-US&gl=US&ceid=US:en",
        "rank": 0,
    },
    {
        "name": "AP News",
        "url": "https://news.google.com/rss/search?q=when:2d+site:apnews.com+(inflation+OR+%22interest+rate%22+OR+%22Federal+Reserve%22+OR+economy+OR+tariff+OR+jobs+OR+GDP)&hl=en-US&gl=US&ceid=US:en",
        "rank": 1,
    },
    {
        "name": "Financial Times",
        "url": "https://www.ft.com/world/economy?format=rss",
        "rank": 2,
    },
    {
        "name": "Wall Street Journal",
        "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "rank": 3,
    },
    {
        "name": "The Economist",
        "url": "https://www.economist.com/finance-and-economics/rss.xml",
        "rank": 4,
    },
    {
        "name": "BBC Business",
        "url": "https://feeds.bbci.co.uk/news/business/rss.xml",
        "rank": 5,
    },
    {
        "name": "CNBC",
        "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "rank": 6,
    },
    {
        "name": "NPR Economy",
        "url": "https://feeds.npr.org/1006/rss.xml",
        "rank": 7,
    },
]

# Higher weight = more likely to move global markets. Matched on title and summary.
IMPACT_TERMS: list[tuple[str, int]] = [
    (r"\bfederal reserve\b|\bfomc\b|\brate cut\b|\brate hike\b|\binterest rates?\b|\becb\b|\beuropean central bank\b|\bbank of england\b|\bbank of japan\b|\bboj\b|\bpboc\b|\bcentral bank\b", 100),
    (r"\binflation\b|\bcpi\b|\bpce\b|\bconsumer prices?\b|\bjobs report\b|\bnonfarm\b|\bpayrolls?\b|\bunemployment\b|\brecession\b|\bgdp\b", 90),
    (r"\bopec\b|\bcrude\b|\bbrent\b|\boil price\b|\bsanctions?\b|\binvasion\b|\bwar\b|\btariffs?\b|\btrade war\b|\bdefault\b|\bbank failure\b|\bcredit crisis\b|\bstimulus\b", 80),
    (r"\byields?\b|\btreasury\b|\bdollar\b|\byen\b|\beuro\b|\byuan\b|\bs&p\b|\bnasdaq\b|\bstock market\b|\bwall street\b|\bsell-?off\b|\brally\b", 55),
    (r"\bpmi\b|\bretail sales\b|\bmanufacturing\b|\bhousing\b|\bconsumer confidence\b|\bearnings\b|\bguidance\b", 30),
    (r"\beconomy\b|\beconomic\b|\bmarkets?\b|\binvestors?\b|\bstocks?\b|\bshares\b|\btrade\b", 15),
]

NOISE_TERMS = re.compile(
    r"\b(celebrity|wedding|recipe|football|soccer|nba|nfl|oscar|box office|obituary|royals?)\b",
    re.IGNORECASE,
)
SOFT_STORY = re.compile(
    r"\b(meet the|identity crisis|commentary|opinion|explainer|newsletter|scandal|comeback|what to know)\b",
    re.IGNORECASE,
)
STOP_WORDS = {
    "the", "a", "an", "of", "to", "and", "in", "on", "for", "as", "at", "by",
    "from", "with", "after", "over", "its", "into", "that", "this", "are", "was",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
TAG_RE = re.compile(r"<[^>]+>")


def _clean_text(value: str | None, limit: int = 320) -> str:
    if not value:
        return ""
    text = html.unescape(TAG_RE.sub(" ", value))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def _entry_summary(entry: Any) -> str:
    for attr in ("summary", "description"):
        value = getattr(entry, attr, None)
        cleaned = _clean_text(value)
        if cleaned:
            return cleaned
    content = getattr(entry, "content", None)
    if isinstance(content, list) and content:
        cleaned = _clean_text(content[0].get("value", ""))
        if cleaned:
            return cleaned
    return "Open the article for the full story."


def _fetch_feed(url: str) -> feedparser.FeedParserDict:
    last_error: Exception | None = None
    for _ in range(2):
        try:
            response = requests.get(
                url,
                timeout=20,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/rss+xml, application/xml, text/xml, */*",
                },
            )
            response.raise_for_status()
            parsed = feedparser.parse(response.content)
            if getattr(parsed, "entries", None):
                return parsed
            last_error = RuntimeError(f"No stories in feed: {url}")
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise RuntimeError(f"Could not read feed: {url}")


def _impact_score(text: str) -> int:
    macro = 0
    extra = 0
    for pattern, weight in IMPACT_TERMS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            if weight >= 55:
                macro += weight
            else:
                extra += weight
    score = macro + min(extra, 20)
    if SOFT_STORY.search(text):
        score -= 60
    return score


def _tokens(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", title.casefold())
    return {word for word in words if word not in STOP_WORDS and len(word) > 2}


def _too_similar(title: str, chosen: list[dict[str, Any]]) -> bool:
    current = _tokens(title)
    if not current:
        return False
    for item in chosen:
        other = _tokens(item["title"])
        if not other:
            continue
        overlap = len(current & other) / min(len(current), len(other))
        if overlap >= 0.6:
            return True
    return False


def fetch_headlines(count: int = 5) -> list[dict[str, Any]]:
    """Return macro headlines ranked by how much they are likely to move markets."""
    collected: list[dict[str, Any]] = []
    seen_titles: set[str] = set()

    for source in SOURCES:
        try:
            feed = _fetch_feed(source["url"])
        except Exception:
            continue

        for entry in feed.entries[:12]:
            title = _clean_text(getattr(entry, "title", ""), limit=160)
            title = re.sub(r"\s+-\s+(Reuters|AP News|AP|BBC|CNBC|FT|WSJ)$", "", title).strip()
            if not title:
                continue

            key = title.casefold()
            if key in seen_titles:
                continue
            seen_titles.add(key)

            summary = _entry_summary(entry)
            blob = f"{title} {summary}"
            if NOISE_TERMS.search(blob):
                continue

            collected.append(
                {
                    "title": title,
                    "summary": summary,
                    "link": getattr(entry, "link", "") or "",
                    "source": source["name"],
                    "score": _impact_score(blob),
                    "rank": source["rank"],
                }
            )

    collected.sort(key=lambda item: (-item["score"], item["rank"]))

    ranked: list[dict[str, Any]] = []
    for item in collected:
        if item["score"] <= 0 and len(ranked) >= count:
            break
        if _too_similar(item["title"], ranked):
            continue
        ranked.append(
            {
                "title": item["title"],
                "summary": item["summary"],
                "link": item["link"],
                "source": item["source"],
            }
        )
        if len(ranked) >= count:
            break

    return ranked
