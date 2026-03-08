"""
Semantic Scholar collector — fetches recent papers across all scientific fields.

Unlike OpenAlex (journal-restricted), this searches broadly across ALL of science
and uses Semantic Scholar's influence metrics (influentialCitationCount) as a
quality signal instead of journal prestige.

API key (optional but recommended):
  Set SEMANTIC_SCHOLAR_API_KEY env var to avoid sharing the unauthenticated
  rate-limit pool with all other users. Get a key at:
  https://www.semanticscholar.org/product/api#api-key-form
  Both authenticated and unauthenticated limits are 1 RPS, but authenticated
  requests are not throttled during heavy shared usage.

Docs: https://api.semanticscholar.org/api-docs/
"""

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)


def _headers() -> dict:
    """Return request headers, including API key if available."""
    h = {}
    key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    if key:
        h["x-api-key"] = key
    return h

S2_BASE = "https://api.semanticscholar.org/graph/v1"
S2_FIELDS = (
    "paperId,title,abstract,venue,year,publicationDate,"
    "citationCount,influentialCitationCount,"
    "externalIds,openAccessPdf,fieldsOfStudy,s2FieldsOfStudy"
)

# Broad queries per scientific domain — cast a wide net across all of science.
# Each query is intentionally general to capture diverse recent work.
DOMAIN_QUERIES: list[tuple[str, str]] = [
    ("Physics", "novel phenomenon quantum field classical"),
    ("Astronomy & Cosmology", "astronomical observation universe cosmological"),
    ("Biology & Evolution", "biological mechanism evolution organism"),
    ("Neuroscience", "brain neural cognitive behavior circuit"),
    ("Genetics & Genomics", "genome gene expression mutation sequencing"),
    ("Chemistry", "chemical synthesis molecular reaction catalysis"),
    ("Medicine & Health", "clinical treatment therapeutic disease mechanism"),
    ("Materials Science", "material structure property functional device"),
    ("Environmental & Climate", "climate ecosystem atmosphere carbon environment"),
    ("Interdisciplinary", "emergent complex system cross-disciplinary novel"),
]


def fetch_papers(
    lookback_days: int = 7,
    max_per_domain: int = 12,
    delay_sec: float = 1.2,
) -> list[dict]:
    """
    Fetch recent papers across scientific domains from Semantic Scholar.

    S2 has a 2–4 week indexing lag, so we use a wider fetch window (lookback_days * 4,
    min 30 days) but filter client-side to the actual lookback window. This ensures
    we always have a full pool of papers. Cross-week deduplication is handled
    by seen_ids in state/.

    Returns list of paper dicts with standardized fields.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    # Fetch window: 4× the lookback or at least 30 days to account for S2 indexing lag
    fetch_since = (datetime.now(timezone.utc) - timedelta(days=max(lookback_days * 4, 30))).strftime("%Y-%m-%d")

    all_papers: list[dict] = []
    seen_ids: set[str] = set()

    for domain, query in DOMAIN_QUERIES:
        try:
            papers = _fetch_domain(query, domain, fetch_since, max_per_domain, cutoff)
            new = [p for p in papers if p["id"] not in seen_ids]
            seen_ids.update(p["id"] for p in new)
            all_papers.extend(new)
            logger.info(f"S2: {len(new)} papers from {domain}")
            time.sleep(delay_sec)
        except requests.HTTPError as e:
            logger.warning(f"S2: HTTP error for {domain}: {e}")
        except Exception as e:
            logger.warning(f"S2: failed for {domain}: {e}")

    logger.info(f"Semantic Scholar total: {len(all_papers)} papers")
    return all_papers


def _fetch_domain(
    query: str,
    domain: str,
    fetch_since: str,
    max_results: int,
    cutoff: datetime,
) -> list[dict]:
    """
    Fetch papers for one domain query.
    - Server-side: broad date window (fetch_since) to account for S2 indexing lag
    - Client-side: filter to cutoff (the actual lookback window)
    """
    params = {
        "query": query,
        "fields": S2_FIELDS,
        "publicationDateOrYear": f"{fetch_since}:",
        "limit": min(max_results * 5, 100),
        "offset": 0,
    }
    resp = requests.get(f"{S2_BASE}/paper/search", params=params, headers=_headers(), timeout=20)

    if resp.status_code == 429:
        logger.warning("S2: rate limited — sleeping 60s")
        time.sleep(60)
        resp = requests.get(f"{S2_BASE}/paper/search", params=params, headers=_headers(), timeout=20)

    resp.raise_for_status()
    data = resp.json()

    papers: list[dict] = []
    for item in data.get("data", []):
        paper = _normalize(item, domain)
        if not paper:
            continue
        # Client-side date filter: keep only papers within the actual lookback window
        pub = paper.get("pub_date", "")
        if pub:
            try:
                pub_dt = datetime.fromisoformat(pub).replace(tzinfo=timezone.utc)
                if pub_dt < cutoff:
                    continue
            except ValueError:
                pass  # unparseable date — keep the paper
        papers.append(paper)
        if len(papers) >= max_results:
            break

    return papers


def _normalize(item: dict, domain: str) -> Optional[dict]:
    """Convert a Semantic Scholar paper dict → standardized paper dict."""
    title = (item.get("title") or "").strip()
    if not title or len(title) < 10:
        return None

    abstract = (item.get("abstract") or "").strip()
    if not abstract:
        return None  # no abstract = can't analyse

    paper_id = item.get("paperId", "")
    if not paper_id:
        return None

    # External identifiers
    ext = item.get("externalIds") or {}
    doi = ext.get("DOI", "")
    arxiv_id = ext.get("ArXiv", "")

    # Canonical URL
    if doi:
        url = f"https://doi.org/{doi}"
    elif arxiv_id:
        url = f"https://arxiv.org/abs/{arxiv_id}"
    else:
        url = f"https://www.semanticscholar.org/paper/{paper_id}"

    # PDF
    pdf_url: Optional[str] = None
    oa = item.get("openAccessPdf") or {}
    if oa.get("url"):
        pdf_url = oa["url"]
    elif arxiv_id:
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    # Venue / journal name
    venue = (item.get("venue") or "").strip()
    if not venue:
        # Fall back to the first field-of-study label
        s2_fields = item.get("s2FieldsOfStudy") or []
        venue = s2_fields[0].get("category", domain) if s2_fields else domain

    # Concept tags
    s2_fields = item.get("s2FieldsOfStudy") or []
    concepts = [f.get("category", "") for f in s2_fields if f.get("category")]
    if not concepts:
        concepts = item.get("fieldsOfStudy") or [domain]

    pub_date = (item.get("publicationDate") or str(item.get("year", ""))).strip()

    return {
        "id": f"s2:{paper_id}",
        "title": title,
        "abstract": abstract,
        "journal": venue,
        "source_name": venue,
        "pub_date": pub_date,
        "doi": doi,
        "url": url,
        "pdf_url": pdf_url,
        "concepts": concepts[:8],
        "cited_by_count": item.get("citationCount", 0) or 0,
        "influential_citations": item.get("influentialCitationCount", 0) or 0,
        "collection": "published" if (doi and not arxiv_id) else "preprint",
        "fulltext": "",
    }
