"""
Ranker — scores and selects the best papers for the podcast.

Scoring tiers (applied in order, higher tier = more important):
  Tier 0: Boosted topics from missed papers (user's explicit ground truth)
  Tier 1: Time-decayed feedback score (liked papers → extract source/keyword signals)
  Tier 2: LLM lens scores (contradicts/frontier/cross-disciplinary) ← primary signal
  Tier 3: Signal keywords in title/abstract (surprise/novelty language)
  Tier 4: Semantic Scholar influential citations (log-scaled, quality proxy)
  Tier 5: Full text available

Journal prestige is intentionally NOT a ranking factor — we want papers ranked
by their intellectual value (surprising, frontier-opening, cross-disciplinary),
not by which journal they happen to be in.
"""

import json
import logging
import math
import os
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

FEEDBACK_HALFLIFE_DAYS = 14

# Keywords that signal surprising/paradigm-shifting findings
SIGNAL_KEYWORDS = [
    "unexpected", "surprising", "contrary to", "challenges", "overturns",
    "paradox", "anomaly", "first evidence", "previously unknown", "long-standing",
    "rethink", "surprisingly", "counterintuitive", "defies", "contrary to expectation",
    "never before", "first observation", "first direct", "unexpectedly",
    "novel mechanism", "unprecedented", "overturns", "challenges the",
    "contradicts", "defies expectation", "paradigm shift",
]


# ── Feedback loading ─────────────────────────────────────────────────────────

def load_feedback(state_dir: str) -> dict:
    """
    Load feedback.json and compute time-decayed signals.
    Returns: {"source_weights": {source: float}, "keyword_weights": {kw: float}}
    """
    path = os.path.join(state_dir, "feedback.json")
    if not os.path.exists(path):
        return {"source_weights": {}, "keyword_weights": {}}

    with open(path) as f:
        raw = json.load(f)

    today = datetime.now(timezone.utc).date()
    source_weights: dict[str, float] = {}
    keyword_weights: dict[str, float] = {}

    for date_str, entries in raw.items():
        try:
            entry_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        days_ago = (today - entry_date).days
        decay = 0.5 ** (days_ago / FEEDBACK_HALFLIFE_DAYS)

        for entry in entries:
            if isinstance(entry, str):
                continue  # old format without metadata
            source = entry.get("source", "")
            title = entry.get("title", "").lower()

            if source:
                source_weights[source] = source_weights.get(source, 0) + decay

            words = _extract_keywords(title)
            for w in words:
                keyword_weights[w] = keyword_weights.get(w, 0) + decay

    return {"source_weights": source_weights, "keyword_weights": keyword_weights}


def load_boosted_topics(state_dir: str) -> list[str]:
    """Load user-defined boosted topics from missed paper submissions."""
    path = os.path.join(state_dir, "boosted_topics.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [t.lower() for t in json.load(f)]


def _extract_keywords(title: str) -> list[str]:
    STOP = {"the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or",
            "but", "with", "via", "by", "from", "new", "using", "based", "this",
            "that", "its", "are", "is", "was", "were", "has", "have", "been"}
    words = re.findall(r"[a-z]{4,}", title.lower())
    return [w for w in words if w not in STOP]


# ── Scoring ──────────────────────────────────────────────────────────────────

def score_paper(paper: dict, weights: dict, feedback: dict, boosted_topics: list[str]) -> float:
    """Compute composite score for a paper. Higher = more podcast-worthy."""
    analysis = paper.get("analysis", {})
    title = paper.get("title", "").lower()
    abstract = paper.get("abstract", "").lower()
    source = paper.get("source_name", paper.get("journal", ""))
    text = f"{title} {abstract}"

    score = 0.0

    # ── Tier 0: Boosted topics (user's explicit ground truth) ──
    if any(topic in text for topic in boosted_topics):
        score += 5.0

    # ── Tier 1: Time-decayed feedback signals ──
    source_weights = feedback.get("source_weights", {})
    keyword_weights = feedback.get("keyword_weights", {})

    if source in source_weights:
        score += min(source_weights[source], 3.0)

    keyword_boost = sum(min(w, 1.5) for kw, w in keyword_weights.items() if kw in text)
    score += min(keyword_boost, 3.0)

    # ── Tier 2: LLM lens scores (0–10 each) — PRIMARY quality signal ──
    # These directly measure what we care about: surprising, frontier, cross-disciplinary.
    score += (analysis.get("contradicts_consensus", {}).get("score", 0) / 10.0) * weights.get("contradicts_consensus", 3.0)
    score += (analysis.get("new_frontier", {}).get("score", 0) / 10.0) * weights.get("new_frontier", 2.5)
    score += (analysis.get("cross_disciplinary", {}).get("score", 0) / 10.0) * weights.get("cross_disciplinary", 2.0)

    if analysis.get("best_for_podcast"):
        score += 0.5

    # ── Tier 3: Signal keywords (surprise/novelty language in title/abstract) ──
    keyword_hits = sum(1 for kw in SIGNAL_KEYWORDS if kw in text)
    score += min(keyword_hits * 0.15, 0.75)

    # ── Tier 4: Influential citations (log-scaled, quality proxy without prestige bias) ──
    # Uses Semantic Scholar's influentialCitationCount — papers that have already
    # influenced other researchers. Log-scaled so a handful of citations still helps.
    infl = paper.get("influential_citations", 0) or 0
    if infl > 0:
        score += min(math.log1p(infl) * weights.get("influential_citations", 0.5), 2.0)

    # ── Tier 5: Full text available (enables better analysis) ──
    if len(paper.get("fulltext", "")) > 1500:
        score += weights.get("open_access", 0.5)

    return round(score, 3)


def select_papers(papers: list[dict], config: dict, state_dir: str = "state") -> list[dict]:
    """Score all papers, apply diversity constraints, return top N."""
    weights = config.get("scoring", {}).get("weights", {})
    max_total = config.get("limits", {}).get("max_papers_total", 35)
    max_per_source = config.get("limits", {}).get("max_papers_per_source", 4)
    min_score = config.get("scoring", {}).get("min_score", 1)

    feedback = load_feedback(state_dir)
    boosted_topics = load_boosted_topics(state_dir)

    if feedback["source_weights"] or feedback["keyword_weights"]:
        logger.info(f"Feedback: {len(feedback['source_weights'])} sources, "
                    f"{len(feedback['keyword_weights'])} keywords (time-decayed)")
    if boosted_topics:
        logger.info(f"Boosted topics: {boosted_topics[:5]}{'...' if len(boosted_topics) > 5 else ''}")

    for paper in papers:
        paper["score"] = score_paper(paper, weights, feedback, boosted_topics)

    papers.sort(key=lambda p: p["score"], reverse=True)

    selected: list[dict] = []
    source_counts: dict[str, int] = {}

    for paper in papers:
        if paper["score"] < min_score:
            continue
        source = paper.get("journal", "Unknown")
        count = source_counts.get(source, 0)
        if count >= max_per_source:
            continue
        source_counts[source] = count + 1
        selected.append(paper)
        if len(selected) >= max_total:
            break

    logger.info(f"Ranker: selected {len(selected)} from {len(papers)} candidates")
    return selected


def group_by_lens(papers: list[dict]) -> dict[str, list[dict]]:
    """Group selected papers by their primary lens for podcast structure."""
    groups: dict[str, list[dict]] = {
        "contradicts_consensus": [],
        "new_frontier": [],
        "cross_disciplinary": [],
        "general": [],
    }
    for paper in papers:
        analysis = paper.get("analysis", {})
        scores = {
            "contradicts_consensus": analysis.get("contradicts_consensus", {}).get("score", 0),
            "new_frontier": analysis.get("new_frontier", {}).get("score", 0),
            "cross_disciplinary": analysis.get("cross_disciplinary", {}).get("score", 0),
        }
        best_lens = max(scores, key=scores.get)
        if scores[best_lens] >= 5:
            groups[best_lens].append(paper)
        else:
            groups["general"].append(paper)
    return groups
