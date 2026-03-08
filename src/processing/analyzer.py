"""
LLM Analyzer — evaluates each paper through 3 special lenses:
  1. Contradicts consensus: challenges established scientific belief
  2. New frontier: opens a genuinely new research direction
  3. Cross-disciplinary: bridges two distant fields unexpectedly

Uses OpenRouter free tier (Gemini 2.0 Flash).
Results cached by paper ID to avoid re-running on reruns.
"""

import json
import logging
import os
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a scientific editor at Nature with deep expertise across all fields of science.
Your job is to identify papers that are genuinely surprising, groundbreaking, or cross-disciplinary.
Be rigorous and honest. Most papers are incremental — that is fine. Reserve high scores for papers
that truly stand out. Do NOT inflate scores. Base your analysis strictly on the provided text."""

ANALYSIS_PROMPT = """Analyze this scientific paper through three specific lenses.

PAPER:
Title: {title}
Journal: {journal}
Abstract: {abstract}

FULL TEXT (may be truncated):
{fulltext}

Answer in JSON with EXACTLY this structure:
{{
  "contradicts_consensus": {{
    "score": <0-10>,
    "explanation": "<1-2 sentences. What established belief does this challenge? If score < 3, say why not.>"
  }},
  "new_frontier": {{
    "score": <0-10>,
    "explanation": "<1-2 sentences. What new research direction does this open? If score < 3, say why not.>"
  }},
  "cross_disciplinary": {{
    "score": <0-10>,
    "explanation": "<1-2 sentences. Which two fields does this bridge? If score < 3, say why not.>"
  }},
  "core_claim": "<One sentence: the single most important claim of this paper>",
  "why_surprising": "<One sentence: what is genuinely surprising or interesting about this, if anything. Be honest — say 'This is a solid incremental advance' if that is the case.>",
  "best_for_podcast": <true/false: would a scientifically curious non-expert find this genuinely interesting?>
}}

Scoring guide:
- 0-2: Not relevant to this lens
- 3-5: Mildly relevant, somewhat interesting
- 6-8: Clearly relevant, genuinely interesting
- 9-10: Exceptional, paradigm-shifting

Return ONLY valid JSON, no markdown fences."""


def analyze_papers(papers: list[dict], llm_client: OpenAI, model: str,
                   cache_dir: str, max_workers: int = 4) -> list[dict]:
    """
    Run LLM analysis on each paper. Results cached by paper ID.
    Returns papers with 'analysis' field added.
    """
    os.makedirs(cache_dir, exist_ok=True)

    def analyze_one(paper):
        cache_key = hashlib.md5(paper["id"].encode()).hexdigest()
        cache_path = os.path.join(cache_dir, f"{cache_key}.json")

        # Check cache
        if os.path.exists(cache_path):
            with open(cache_path) as f:
                paper["analysis"] = json.load(f)
            return paper

        analysis = _call_llm(paper, llm_client, model)
        if analysis:
            paper["analysis"] = analysis
            with open(cache_path, "w") as f:
                json.dump(analysis, f, indent=2)
        else:
            paper["analysis"] = _empty_analysis()

        return paper

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(analyze_one, p): p for p in papers}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                logger.warning(f"Analysis failed: {e}")
                paper = futures[future]
                paper["analysis"] = _empty_analysis()
                results.append(paper)

    return results


def _call_llm(paper: dict, client: OpenAI, model: str, retries: int = 3) -> Optional[dict]:
    """Call LLM to analyze paper. Returns parsed JSON or None."""
    text = paper.get("fulltext") or paper.get("abstract", "")
    prompt = ANALYSIS_PROMPT.format(
        title=paper["title"],
        journal=paper.get("journal", "Unknown"),
        abstract=paper.get("abstract", "")[:2000],
        fulltext=text[:8000],
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
                max_tokens=800,
                timeout=30,
            )
            raw = response.choices[0].message.content.strip()

            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

            return json.loads(raw)

        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed (attempt {attempt+1}): {e}")
        except Exception as e:
            logger.warning(f"LLM call failed (attempt {attempt+1}): {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)

    return None


def _empty_analysis() -> dict:
    return {
        "contradicts_consensus": {"score": 0, "explanation": "Analysis unavailable."},
        "new_frontier": {"score": 0, "explanation": "Analysis unavailable."},
        "cross_disciplinary": {"score": 0, "explanation": "Analysis unavailable."},
        "core_claim": "",
        "why_surprising": "",
        "best_for_podcast": False,
    }
