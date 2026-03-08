"""Deduplication — tracks seen paper IDs across weekly runs."""

import json
import os
import re


def load_seen(state_dir: str) -> set:
    path = os.path.join(state_dir, "seen_ids.json")
    if os.path.exists(path):
        with open(path) as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set, state_dir: str) -> None:
    os.makedirs(state_dir, exist_ok=True)
    path = os.path.join(state_dir, "seen_ids.json")
    with open(path, "w") as f:
        json.dump(list(seen), f)


def deduplicate(papers: list[dict], seen: set) -> list[dict]:
    """Remove papers already seen in previous runs. Also dedup within batch by title."""
    fresh = []
    seen_titles = set()

    for paper in papers:
        pid = paper.get("id", "")
        title_key = _normalize_title(paper.get("title", ""))

        if pid in seen:
            continue
        if title_key in seen_titles:
            continue

        fresh.append(paper)
        seen_titles.add(title_key)

    return fresh


def _normalize_title(title: str) -> str:
    """Lowercase, remove punctuation, collapse spaces — for fuzzy dedup."""
    t = title.lower()
    t = re.sub(r"[^a-z0-9 ]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t
