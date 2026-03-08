"""
LLM Analyzer — evaluates each paper through 3 special lenses.

Returns plain text (not JSON) — much more robust on free-tier models
that frequently produce malformed JSON. The LENS: tag at the end is
used for grouping; the rest is passed to the script generator as context.

Adapted from openclaw-knowledge-radio's article_analysis.py pattern.
"""

import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a scientific analyst for a cross-disciplinary science podcast.

Given a paper's title, abstract, and any available full text, return a structured
plain-text analysis. Be honest: most papers are incremental, and that is fine.
Reserve high marks for papers that are genuinely surprising or field-crossing.
Do NOT invent results, numbers, or author intent not present in the source."""

ANALYSIS_PROMPT = """Analyze this scientific paper for a podcast audience.

TITLE: {title}
JOURNAL/SOURCE: {journal}
ABSTRACT: {abstract}

FULL TEXT (may be truncated or empty):
{fulltext}

Return ONLY plain text with EXACTLY these labeled sections:

CORE CLAIM:
<One sentence: the single most important finding or claim.>

KEY EVIDENCE:
<How they found it — method, data, or observation. One or two sentences.>

WHY SURPRISING:
<What makes this interesting or unexpected. If it is a solid incremental advance, say so honestly.>

NEW DIRECTION:
<What new research questions or directions does this open, if any.>

CROSS DISCIPLINARY LINK:
<Which two fields does this bridge, if any. Write "none" if it does not cross fields.>

LIMITATIONS:
<Main caveats, uncertainties, or what is not yet known.>

LENS: <choose exactly one: CONTRADICTS_CONSENSUS | NEW_FRONTIER | CROSS_DISCIPLINARY | GENERAL>

Lens guide:
- CONTRADICTS_CONSENSUS: The paper challenges an established scientific belief or overturns a consensus view.
- NEW_FRONTIER: The paper opens a genuinely new territory that was barely studied before.
- CROSS_DISCIPLINARY: The paper bridges two distant fields in a non-obvious way.
- GENERAL: Important or interesting work that does not strongly fit the above three.

Return plain text only. No markdown. No JSON."""


def analyze_papers(
    papers: list[dict],
    llm_client: OpenAI,
    model: str,
    cache_dir: str,
    max_workers: int = 1,  # kept for API compat; always sequential for free-tier safety
) -> list[dict]:
    """
    Run plain-text LLM analysis on each paper. Results cached by paper ID.
    Adds paper["analysis_text"] (str) and paper["lens"] (str) to each paper.
    """
    os.makedirs(cache_dir, exist_ok=True)

    for paper in papers:
        cache_key = hashlib.md5(paper["id"].encode()).hexdigest()
        cache_path = os.path.join(cache_dir, f"{cache_key}.txt")

        if os.path.exists(cache_path):
            text = Path(cache_path).read_text(encoding="utf-8").strip()
            paper["analysis_text"] = text
            paper["lens"] = _extract_lens(text)
            logger.debug(f"Cache hit: {paper['title'][:50]}")
            continue

        text = _call_llm(paper, llm_client, model)
        if text:
            Path(cache_path).write_text(text, encoding="utf-8")
            paper["analysis_text"] = text
            paper["lens"] = _extract_lens(text)
            logger.debug(f"Analyzed: {paper['title'][:50]} → {paper['lens']}")
        else:
            paper["analysis_text"] = ""
            paper["lens"] = "GENERAL"
            logger.warning(f"Analysis failed: {paper['title'][:50]}")

        time.sleep(0.5)  # gentle pacing for free-tier rate limits

    return papers


def _call_llm(paper: dict, client: OpenAI, model: str, retries: int = 3) -> Optional[str]:
    """Call LLM and return plain text analysis. Returns None only on total failure."""
    body = paper.get("fulltext") or paper.get("abstract", "")
    prompt = ANALYSIS_PROMPT.format(
        title=paper["title"],
        journal=paper.get("journal", "Unknown"),
        abstract=paper.get("abstract", "")[:2000],
        fulltext=body[:6000],
    )

    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=900,
                timeout=45,
            )
            text = (response.choices[0].message.content or "").strip()
            if text and "CORE CLAIM" in text:
                return text
            logger.warning(f"Unexpected response format (attempt {attempt + 1}): {text[:200]!r}")
        except Exception as e:
            logger.warning(f"LLM call failed (attempt {attempt + 1}): {type(e).__name__}: {e}")
            if attempt < retries - 1:
                time.sleep(3 ** attempt)

    return None


def _extract_lens(text: str) -> str:
    """Parse the LENS: line from plain text analysis."""
    for line in text.splitlines():
        if line.strip().upper().startswith("LENS:"):
            value = line.split(":", 1)[1].strip().upper()
            for lens in ("CONTRADICTS_CONSENSUS", "NEW_FRONTIER", "CROSS_DISCIPLINARY"):
                if lens in value:
                    return lens
    return "GENERAL"
