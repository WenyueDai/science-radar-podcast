#!/usr/bin/env python3
"""
Process missed paper submissions.

When a user submits a paper they expected to see but didn't,
this script:
  1. Diagnoses WHY it was missed (already_covered / low_ranking / source_not_tracked)
  2. Extracts 3-5 topic keywords via LLM
  3. Merges keywords into state/boosted_topics.json (raises their priority in future runs)
  4. Marks entry as processed in missed_papers.json

Triggered by: .github/workflows/process_missed.yml (on push to missed_papers.json)
"""

import json
import logging
import os
import re
import sys
import time
from pathlib import Path

import requests
import yaml
from openai import OpenAI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("process-missed")

_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = _ROOT / "config.yaml"
STATE_DIR = _ROOT / "state"
MISSED_FILE = STATE_DIR / "missed_papers.json"
BOOSTED_FILE = STATE_DIR / "boosted_topics.json"
SEEN_FILE = STATE_DIR / "seen_ids.json"

STOP_WORDS = {
    "the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or", "but",
    "with", "via", "by", "from", "new", "using", "based", "this", "that", "its",
    "are", "is", "was", "were", "has", "have", "been", "study", "shows", "show",
    "reveal", "reveals", "role", "effect", "effects", "through", "between",
}


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def load_json(path: Path, default):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ── Diagnosis ──────────────────────────────────────────────────────────────────

def diagnose(entry: dict, seen_ids: set, config: dict) -> str:
    """Determine why the paper was missed."""
    title = (entry.get("title") or "").lower()
    url = (entry.get("url") or "").lower()

    # Already covered in a previous episode
    uid = entry.get("url") or entry.get("title", "")
    if uid in seen_ids:
        return "already_covered"

    # Check if it would have been excluded by config terms
    # (Science Radar has no excluded terms by default, but future config might)
    excluded = [t.lower() for t in config.get("excluded_terms", [])]
    if any(term in title for term in excluded):
        return "excluded_term"

    # Check if the source journal is tracked
    target_journals = [j.lower() for j in config.get("target_journals", [])]
    arxiv_cats = [c.lower() for c in config.get("arxiv_categories", [])]
    if url:
        is_arxiv = "arxiv.org" in url
        is_tracked_journal = any(j in title or j in url for j in target_journals)
        if not is_arxiv and not is_tracked_journal:
            return "source_not_tracked"

    # Default: was in scope but ranked too low
    return "low_ranking"


# ── Keyword extraction ─────────────────────────────────────────────────────────

def extract_keywords_llm(title: str, client: OpenAI, model: str) -> list[str]:
    """Use LLM to extract 3-5 topic keywords from paper title."""
    prompt = (
        f"Extract 3 to 5 short, specific topic keywords (2-4 words each) from this paper title.\n"
        f"Title: {title}\n\n"
        f"Return ONLY a JSON array of strings. Example: [\"protein folding\", \"deep learning\", \"structure prediction\"]\n"
        f"Focus on the scientific topic, not methodology words like 'study', 'analysis', 'approach'."
    )
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=150,
                timeout=20,
            )
            raw = resp.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            keywords = json.loads(raw)
            if isinstance(keywords, list):
                return [k.lower().strip() for k in keywords if isinstance(k, str) and len(k) > 3]
        except Exception as e:
            logger.warning(f"LLM keyword extraction failed (attempt {attempt+1}): {e}")
            if attempt < 2:
                time.sleep(2)
    return _extract_keywords_heuristic(title)


def _extract_keywords_heuristic(title: str) -> list[str]:
    """Fallback: extract meaningful words from title."""
    words = re.findall(r"[a-zA-Z]{4,}", title.lower())
    filtered = [w for w in words if w not in STOP_WORDS]
    # Build bigrams
    bigrams = [f"{filtered[i]} {filtered[i+1]}" for i in range(len(filtered)-1)]
    return (bigrams + filtered)[:5]


# ── Merge boosted topics ───────────────────────────────────────────────────────

def merge_boosted_topics(new_keywords: list[str]) -> int:
    """Merge new keywords into boosted_topics.json. Returns count of newly added."""
    existing = load_json(BOOSTED_FILE, [])
    existing_lower = {k.lower() for k in existing}
    added = 0
    for kw in new_keywords:
        kw = kw.lower().strip()
        if kw and kw not in existing_lower:
            existing.append(kw)
            existing_lower.add(kw)
            added += 1
    save_json(BOOSTED_FILE, existing)
    return added


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    config = load_config()
    api_key = os.environ.get(config["llm"]["api_key_env"])
    if not api_key:
        logger.error(f"Missing {config['llm']['api_key_env']}")
        sys.exit(1)

    client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
    model = config["llm"].get("analysis_model", "google/gemini-2.0-flash-exp:free")

    missed = load_json(MISSED_FILE, [])
    seen_ids = set(load_json(SEEN_FILE, []))

    unprocessed = [e for e in missed if not e.get("processed")]
    if not unprocessed:
        logger.info("No unprocessed missed paper submissions.")
        return

    logger.info(f"Processing {len(unprocessed)} missed paper submission(s)...")

    for entry in unprocessed:
        title = entry.get("title", "Untitled")
        logger.info(f"  Processing: {title[:70]}")

        # Diagnose
        diagnosis = diagnose(entry, seen_ids, config)
        entry["diagnosis"] = diagnosis
        logger.info(f"    Diagnosis: {diagnosis}")

        # Extract keywords for low_ranking and source_not_tracked
        keywords = []
        if diagnosis in ("low_ranking", "source_not_tracked"):
            keywords = extract_keywords_llm(title, client, model)
            entry["keywords_added"] = keywords
            added = merge_boosted_topics(keywords)
            logger.info(f"    Keywords: {keywords} ({added} new added to boosted_topics)")
        else:
            entry["keywords_added"] = []

        entry["processed"] = True

    save_json(MISSED_FILE, missed)
    logger.info("Done. Updated missed_papers.json and boosted_topics.json.")


if __name__ == "__main__":
    main()
