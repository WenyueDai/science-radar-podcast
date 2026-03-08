"""
Article text extractor — pulls full text from PDFs and web pages.
Reuses proven pattern from openclaw-knowledge-radio.
"""

import logging
import re
import requests
from typing import Optional

logger = logging.getLogger(__name__)

MAX_CHARS = 15000  # Feed up to 15k chars to LLM (Gemini Flash handles this easily)
MIN_FULLTEXT_CHARS = 1500  # Below this, treat as abstract-only


def extract(paper: dict) -> str:
    """
    Try multiple strategies to get full text.
    Returns extracted text (may be just abstract if full text unavailable).
    """
    # Strategy 1: PDF (best quality)
    if paper.get("pdf_url"):
        text = _from_pdf(paper["pdf_url"])
        if text and len(text) > MIN_FULLTEXT_CHARS:
            return text[:MAX_CHARS]

    # Strategy 2: Web page extraction
    if paper.get("url"):
        text = _from_webpage(paper["url"])
        if text and len(text) > MIN_FULLTEXT_CHARS:
            return text[:MAX_CHARS]

    # Strategy 3: Try arXiv PDF if it's an arXiv paper
    arxiv_pdf = _guess_arxiv_pdf(paper)
    if arxiv_pdf:
        text = _from_pdf(arxiv_pdf)
        if text and len(text) > MIN_FULLTEXT_CHARS:
            return text[:MAX_CHARS]

    # Fallback: abstract only
    return paper.get("abstract", "")


def _from_pdf(url: str) -> Optional[str]:
    """Download and extract text from PDF using PyMuPDF."""
    try:
        import fitz  # PyMuPDF
        import io

        headers = {"User-Agent": "Science-Radar-Podcast/1.0"}
        resp = requests.get(url, headers=headers, timeout=20, stream=True)
        resp.raise_for_status()

        # Sanity check: must be a PDF
        content_type = resp.headers.get("content-type", "")
        if "pdf" not in content_type.lower() and not url.endswith(".pdf"):
            # Check first bytes
            chunk = next(resp.iter_content(1024), b"")
            if not chunk.startswith(b"%PDF"):
                return None
            content = chunk + resp.content
        else:
            content = resp.content

        doc = fitz.open(stream=io.BytesIO(content), filetype="pdf")
        texts = []
        for page_num, page in enumerate(doc):
            if page_num > 15:  # Don't extract beyond page 15 (references section)
                break
            texts.append(page.get_text())
        doc.close()

        raw = "\n".join(texts)
        return _clean_text(raw)

    except Exception as e:
        logger.debug(f"PDF extraction failed for {url}: {e}")
        return None


def _from_webpage(url: str) -> Optional[str]:
    """Extract article text from web page using newspaper4k then BeautifulSoup."""
    # Try newspaper4k first
    try:
        from newspaper import Article
        article = Article(url)
        article.download()
        article.parse()
        if article.text and len(article.text) > MIN_FULLTEXT_CHARS:
            return _clean_text(article.text)
    except Exception:
        pass

    # Fallback: BeautifulSoup
    try:
        from bs4 import BeautifulSoup
        headers = {"User-Agent": "Mozilla/5.0 (compatible; Science-Radar/1.0)"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")
        # Remove nav, header, footer, scripts
        for tag in soup(["nav", "header", "footer", "script", "style", "aside"]):
            tag.decompose()

        # Try article/main tags first
        for selector in ["article", "main", "[role='main']", ".article-body", "#article-body"]:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(separator=" ", strip=True)
                if len(text) > MIN_FULLTEXT_CHARS:
                    return _clean_text(text)

        # Last resort: body
        body = soup.find("body")
        if body:
            return _clean_text(body.get_text(separator=" ", strip=True))

    except Exception as e:
        logger.debug(f"Web extraction failed for {url}: {e}")

    return None


def _guess_arxiv_pdf(paper: dict) -> Optional[str]:
    """Try to construct an arXiv PDF URL from the paper's URL or ID."""
    url = paper.get("url", "") or paper.get("id", "")
    if "arxiv.org" not in url:
        return None
    # Convert abs URL to PDF
    pdf = re.sub(r"arxiv\.org/abs/", "arxiv.org/pdf/", url)
    if not pdf.endswith(".pdf"):
        pdf += ".pdf"
    return pdf


def _clean_text(text: str) -> str:
    """Clean extracted text for LLM consumption."""
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    # Remove common PDF artifacts
    text = re.sub(r"(\w)-\s+(\w)", r"\1\2", text)  # hyphenation
    # Remove reference sections (common patterns)
    for pattern in [r"References\s*\n.*$", r"Bibliography\s*\n.*$", r"\[\d+\].*$"]:
        text = re.sub(pattern, "", text, flags=re.DOTALL | re.MULTILINE)
    return text.strip()
