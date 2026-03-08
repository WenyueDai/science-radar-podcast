"""
Ranker — scores and selects the best papers for the podcast.

Scoring:
  - LLM lens scores (contradicts_consensus, new_frontier, cross_disciplinary)
  - Signal keywords in title/abstract
  - Journal prestige tier
  - Full text availability (enables deeper analysis)
  - Diversity: avoid same journal dominating
"""

import logging
import re

logger = logging.getLogger(__name__)

# Journal prestige tiers (higher = more prestigious)
JOURNAL_TIERS = {
    3: ["Nature", "Science", "Cell", "NEJM", "The Lancet", "Physical Review Letters"],
    2: ["PNAS", "Nature Communications", "Nature Medicine", "Nature Physics",
        "Nature Chemistry", "Nature Ecology & Evolution", "Nature Neuroscience",
        "Nature Materials", "Nature Biotechnology", "Nature Climate Change",
        "Nature Human Behaviour", "Nature Astronomy",
        "Science Translational Medicine", "Science Robotics", "Science Immunology",
        "Science Advances", "eLife", "Current Biology", "PLOS Biology",
        "Astrophysical Journal Letters", "Cell Reports"],
    1: ["arXiv", "bioRxiv", "medRxiv"],
}

# Keywords that signal surprising/paradigm-shifting findings
SIGNAL_KEYWORDS = [
    "unexpected", "surprising", "contrary to", "challenges", "overturns",
    "paradox", "anomaly", "first evidence", "previously unknown", "long-standing",
    "rethink", "surprisingly", "counterintuitive", "defies", "contrary to expectation",
    "never before", "first observation", "first direct", "unexpectedly",
    "novel mechanism", "unprecedented",
]


def score_paper(paper: dict, weights: dict) -> float:
    """Compute composite score for a paper."""
    analysis = paper.get("analysis", {})
    score = 0.0

    # LLM lens scores (0-10 each)
    score += (analysis.get("contradicts_consensus", {}).get("score", 0) / 10.0) * weights.get("contradicts_consensus", 3.0)
    score += (analysis.get("new_frontier", {}).get("score", 0) / 10.0) * weights.get("new_frontier", 2.5)
    score += (analysis.get("cross_disciplinary", {}).get("score", 0) / 10.0) * weights.get("cross_disciplinary", 2.0)

    # Podcast suitability bonus
    if analysis.get("best_for_podcast"):
        score += 0.5

    # Journal prestige
    journal = paper.get("journal", "")
    for tier, journals in JOURNAL_TIERS.items():
        if any(j.lower() in journal.lower() for j in journals):
            score += (tier / 3.0) * weights.get("high_impact_journal", 1.5)
            break

    # Signal keyword bonus
    text = f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()
    keyword_hits = sum(1 for kw in SIGNAL_KEYWORDS if kw in text)
    score += min(keyword_hits * 0.15, 0.75)  # cap at 0.75

    # Full text bonus
    if len(paper.get("fulltext", "")) > 1500:
        score += weights.get("open_access", 0.5)

    return round(score, 3)


def select_papers(papers: list[dict], config: dict) -> list[dict]:
    """
    Score all papers, apply diversity constraints, return top N.
    """
    weights = config.get("scoring", {}).get("weights", {})
    max_total = config.get("limits", {}).get("max_papers_total", 35)
    max_per_journal = config.get("limits", {}).get("max_papers_per_journal", 4)
    min_score = config.get("scoring", {}).get("min_score", 1)

    # Score all papers
    for paper in papers:
        paper["score"] = score_paper(paper, weights)

    # Sort by score descending
    papers.sort(key=lambda p: p["score"], reverse=True)

    # Apply diversity: cap per journal
    selected = []
    journal_counts: dict[str, int] = {}

    for paper in papers:
        if paper["score"] < min_score:
            continue
        journal = paper.get("journal", "Unknown")
        count = journal_counts.get(journal, 0)
        if count >= max_per_journal:
            continue
        journal_counts[journal] = count + 1
        selected.append(paper)
        if len(selected) >= max_total:
            break

    logger.info(f"Ranker: selected {len(selected)} papers from {len(papers)} candidates")
    return selected


def group_by_lens(papers: list[dict]) -> dict[str, list[dict]]:
    """
    Group selected papers by their primary lens for podcast structure.
    A paper can appear in multiple groups if it scores high on multiple lenses.
    """
    groups = {
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

        # Assign to primary lens (highest score ≥ 5)
        best_lens = max(scores, key=scores.get)
        if scores[best_lens] >= 5:
            groups[best_lens].append(paper)
        else:
            groups["general"].append(paper)

    return groups
