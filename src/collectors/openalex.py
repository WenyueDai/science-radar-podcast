"""
OpenAlex collector — fetches papers from high-impact journals published in the past N days.
OpenAlex API is completely free, no key required.
Docs: https://docs.openalex.org/
"""

import requests
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

OPENALEX_BASE = "https://api.openalex.org"

# Map journal names → OpenAlex source IDs for precise filtering
# Fetched dynamically if not cached; these are the most common ones
JOURNAL_NAME_MAP = {
    "Nature": "S137773608",
    "Science": "S3880285",
    "Cell": "S3880376",
    "PNAS": "S3880382",
    "Nature Communications": "S33987098",
    "eLife": "S4306400",
}


def fetch_papers(journal_names: list[str], lookback_days: int = 7, max_per_journal: int = 4) -> list[dict]:
    """
    Fetch recent open-access papers from specified journals via OpenAlex.
    Returns list of paper dicts with standardized fields.
    """
    since_date = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    all_papers = []

    for journal_name in journal_names:
        try:
            papers = _fetch_journal(journal_name, since_date, max_per_journal)
            all_papers.extend(papers)
            logger.info(f"OpenAlex: {len(papers)} papers from {journal_name}")
        except Exception as e:
            logger.warning(f"OpenAlex: failed for {journal_name}: {e}")

    logger.info(f"OpenAlex total: {len(all_papers)} papers")
    return all_papers


def _fetch_journal(journal_name: str, since_date: str, max_results: int) -> list[dict]:
    """Fetch papers from a single journal."""
    params = {
        "filter": f"primary_location.source.display_name.search:{journal_name},from_publication_date:{since_date},is_oa:true",
        "sort": "publication_date:desc",
        "per-page": max_results * 3,  # fetch more, filter down
        "select": "id,doi,title,abstract_inverted_index,primary_location,publication_date,authorships,concepts,open_access,cited_by_count",
        "mailto": "science-radar@example.com",  # polite pool
    }

    resp = requests.get(f"{OPENALEX_BASE}/works", params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    papers = []
    for work in data.get("results", []):
        paper = _normalize(work, journal_name)
        if paper:
            papers.append(paper)
        if len(papers) >= max_results:
            break

    return papers


def _normalize(work: dict, source_journal: str) -> Optional[dict]:
    """Convert OpenAlex work → standardized paper dict."""
    title = work.get("title", "").strip()
    if not title or len(title) < 10:
        return None

    # Reconstruct abstract from inverted index
    abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))

    # Get DOI and PDF URL
    doi = work.get("doi", "")
    pdf_url = None
    location = work.get("primary_location", {}) or {}
    if location.get("pdf_url"):
        pdf_url = location["pdf_url"]
    elif work.get("open_access", {}).get("oa_url"):
        pdf_url = work["open_access"]["oa_url"]

    landing_page = location.get("landing_page_url") or (f"https://doi.org/{doi.replace('https://doi.org/', '')}" if doi else "")

    # Concepts (topics) from OpenAlex
    concepts = [c["display_name"] for c in work.get("concepts", [])[:8] if c.get("score", 0) > 0.3]

    # Journal name from the actual data (may differ slightly from query)
    actual_journal = (location.get("source") or {}).get("display_name", source_journal)

    return {
        "id": work.get("id", ""),
        "title": title,
        "abstract": abstract or "",
        "journal": actual_journal,
        "source_name": actual_journal,
        "pub_date": work.get("publication_date", ""),
        "doi": doi,
        "url": landing_page,
        "pdf_url": pdf_url,
        "concepts": concepts,
        "cited_by_count": work.get("cited_by_count", 0),
        "collection": "journal",
        "fulltext": "",  # filled later by extractor
    }


def _reconstruct_abstract(inverted_index: Optional[dict]) -> str:
    """OpenAlex stores abstracts as inverted index {word: [positions]}. Reconstruct."""
    if not inverted_index:
        return ""
    try:
        max_pos = max(pos for positions in inverted_index.values() for pos in positions)
        words = [""] * (max_pos + 1)
        for word, positions in inverted_index.items():
            for pos in positions:
                words[pos] = word
        return " ".join(w for w in words if w)
    except Exception:
        return ""


def search_by_keyword(keyword: str, lookback_days: int = 7, max_results: int = 10) -> list[dict]:
    """
    Fallback: search OpenAlex by keyword across all journals.
    Useful for catching cross-disciplinary papers missed by journal filter.
    """
    since_date = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    params = {
        "filter": f"title_and_abstract.search:{keyword},from_publication_date:{since_date},is_oa:true",
        "sort": "cited_by_count:desc",
        "per-page": max_results,
        "select": "id,doi,title,abstract_inverted_index,primary_location,publication_date,authorships,concepts,open_access,cited_by_count",
        "mailto": "science-radar@example.com",
    }
    resp = requests.get(f"{OPENALEX_BASE}/works", params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return [p for work in data.get("results", []) if (p := _normalize(work, "OpenAlex Search"))]
