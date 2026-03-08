"""
RSS collector — fetches from journal RSS feeds.
Reuses pattern from openclaw-knowledge-radio.
"""

import feedparser
import requests
import logging
from datetime import datetime, timedelta, timezone
from dateutil import parser as dateparser

logger = logging.getLogger(__name__)


def fetch_papers(sources: list[dict], lookback_days: int = 7) -> list[dict]:
    """Fetch papers from RSS sources, return standardized paper dicts."""
    since = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    all_papers = []

    for source in sources:
        try:
            papers = _fetch_feed(source, since)
            all_papers.extend(papers)
            logger.info(f"RSS: {len(papers)} items from {source['name']}")
        except Exception as e:
            logger.warning(f"RSS: failed for {source['name']}: {e}")

    return all_papers


def _fetch_feed(source: dict, since: datetime) -> list[dict]:
    headers = {"User-Agent": "Science-Radar-Podcast/1.0 (research tool)"}
    resp = requests.get(source["url"], headers=headers, timeout=15)
    resp.raise_for_status()

    feed = feedparser.parse(resp.text)
    papers = []

    for entry in feed.entries:
        pub_date = _parse_date(entry)
        if pub_date and pub_date < since:
            continue

        title = (getattr(entry, "title", "") or "").strip()
        url = getattr(entry, "link", "") or ""
        summary = (getattr(entry, "summary", "") or "").strip()

        if not title or not url:
            continue

        papers.append({
            "id": url,
            "title": title,
            "abstract": summary[:1000],
            "journal": source["name"],
            "source_name": source["name"],
            "pub_date": pub_date.strftime("%Y-%m-%d") if pub_date else "",
            "doi": "",
            "url": url,
            "pdf_url": None,
            "concepts": [],
            "cited_by_count": 0,
            "collection": "rss",
            "priority": source.get("priority", 3),
            "fulltext": "",
        })

    return papers


def _parse_date(entry) -> datetime | None:
    for field in ("published", "updated", "created"):
        val = getattr(entry, field, None)
        if val:
            try:
                dt = dateparser.parse(val)
                if dt and dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                continue
    return None
