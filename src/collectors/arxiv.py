"""
arXiv collector — fetches recent preprints across science categories.
arXiv API is completely free, no key required.
"""

import requests
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

ARXIV_API = "https://export.arxiv.org/api/query"
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


def fetch_papers(categories: list[str], lookback_days: int = 7, max_per_category: int = 8) -> list[dict]:
    """
    Fetch recent arXiv preprints for given categories.
    Returns standardized paper dicts.
    """
    all_papers = []
    since = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    for cat in categories:
        try:
            papers = _fetch_category(cat, since, max_per_category)
            all_papers.extend(papers)
            logger.info(f"arXiv: {len(papers)} papers from {cat}")
        except Exception as e:
            logger.warning(f"arXiv: failed for {cat}: {e}")

    logger.info(f"arXiv total: {len(all_papers)} papers")
    return all_papers


def _fetch_category(category: str, since: datetime, max_results: int) -> list[dict]:
    params = {
        "search_query": f"cat:{category}",
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": max_results * 3,
        "start": 0,
    }
    resp = requests.get(ARXIV_API, params=params, timeout=20)
    resp.raise_for_status()

    root = ET.fromstring(resp.text)
    papers = []

    for entry in root.findall("atom:entry", NS):
        paper = _normalize(entry, category)
        if paper is None:
            continue
        # Filter by date
        pub_date = datetime.fromisoformat(paper["pub_date"].replace("Z", "+00:00"))
        if pub_date < since:
            continue
        papers.append(paper)
        if len(papers) >= max_results:
            break

    return papers


def _normalize(entry, category: str) -> dict | None:
    """Convert arXiv entry → standardized paper dict."""
    title_el = entry.find("atom:title", NS)
    summary_el = entry.find("atom:summary", NS)
    published_el = entry.find("atom:published", NS)
    id_el = entry.find("atom:id", NS)

    if title_el is None or id_el is None:
        return None

    title = (title_el.text or "").strip().replace("\n", " ")
    abstract = (summary_el.text or "").strip().replace("\n", " ") if summary_el is not None else ""
    pub_date = (published_el.text or "").strip() if published_el is not None else ""
    arxiv_id = (id_el.text or "").strip()

    # Get PDF link
    pdf_url = None
    for link in entry.findall("atom:link", NS):
        if link.get("title") == "pdf":
            pdf_url = link.get("href", "").replace("http://", "https://")
            break

    # Fallback pdf url
    if not pdf_url and "abs" in arxiv_id:
        pdf_url = arxiv_id.replace("/abs/", "/pdf/") + ".pdf"

    return {
        "id": arxiv_id,
        "title": title,
        "abstract": abstract,
        "journal": "arXiv",
        "source_name": f"arXiv {category}",
        "pub_date": pub_date[:10] if len(pub_date) >= 10 else pub_date,
        "doi": "",
        "url": arxiv_id,
        "pdf_url": pdf_url,
        "concepts": [category],
        "cited_by_count": 0,
        "collection": "preprint",
        "fulltext": "",
    }
