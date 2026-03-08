#!/usr/bin/env python3
"""
Science Radar Podcast — Weekly Runner
Fetches papers from across ALL of science (Semantic Scholar + arXiv + science journalism),
analyses them through 3 lenses (contradicts consensus / new frontier / cross-disciplinary),
and generates a ~1h podcast episode + Notion digest page.

Usage:
    python run_weekly.py                    # run for this week
    RUN_DATE=2026-03-01 python run_weekly.py  # run for a specific week
    REGEN_SCRIPT=true python run_weekly.py    # re-generate script from cached analyses
    FORCE_REGEN=true python run_weekly.py     # redo even if mp3 already exists
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from openai import OpenAI

# ── Setup ─────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("science-radar")


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def make_llm_client(config: dict) -> OpenAI:
    api_key = os.environ.get(config["llm"]["api_key_env"])
    if not api_key:
        raise ValueError(
            f"Missing env var: {config['llm']['api_key_env']}\n"
            "Get a free key at https://openrouter.ai"
        )
    return OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )


# ── Main pipeline ──────────────────────────────────────────────────────────────

def main():
    config = load_config()

    run_date = os.environ.get("RUN_DATE", "").strip() or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    logger.info(f"=== Science Radar — episode {run_date} ===")

    data_dir = config["paths"]["data_dir"]
    output_dir = os.path.join(config["paths"]["output_dir"], run_date)
    state_dir = config["paths"]["state_dir"]
    cache_dir = os.path.join(data_dir, "analysis_cache")
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(state_dir, exist_ok=True)

    # Idempotency: skip if already published
    final_mp3 = Path(output_dir) / f"podcast_{run_date}.mp3"
    episode_json = Path(output_dir) / "episode.json"
    if final_mp3.exists() and not os.environ.get("FORCE_REGEN"):
        logger.info(f"Already published: {final_mp3}. Set FORCE_REGEN=true to redo.")
        return

    llm = make_llm_client(config)
    lookback_days = config.get("lookback_days", 7)

    # ── Phase 1: Collect ──────────────────────────────────────────────────────
    logger.info("Phase 1: Collecting papers...")
    from src.collectors import arxiv, rss
    from src.collectors import semantic_scholar
    from src.utils.dedup import load_seen, deduplicate, save_seen

    seen = load_seen(state_dir)
    papers = []

    # Semantic Scholar — requires API key to avoid shared rate-limit throttling.
    # Skipped automatically until SEMANTIC_SCHOLAR_API_KEY is set.
    s2_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    if s2_key:
        s2_cfg = config.get("semantic_scholar", {})
        s2_papers = semantic_scholar.fetch_papers(
            lookback_days=lookback_days,
            max_per_domain=s2_cfg.get("max_per_domain", 12),
            delay_sec=s2_cfg.get("delay_sec", 1.2),
        )
        papers.extend(s2_papers)
        logger.info(f"Semantic Scholar: {len(s2_papers)} papers")
    else:
        logger.info("Semantic Scholar: skipped (set SEMANTIC_SCHOLAR_API_KEY to enable)")

    # arXiv preprints (keep: good preprint coverage, especially physics/ML)
    arxiv_cats = config.get("arxiv_categories", [])
    if arxiv_cats:
        ax_papers = arxiv.fetch_papers(arxiv_cats, lookback_days=lookback_days, max_per_category=6)
        papers.extend(ax_papers)

    # RSS feeds — science journalism (Quanta, Nature News)
    rss_sources = config.get("rss_sources", [])
    if rss_sources:
        rss_papers = rss.fetch_papers(rss_sources, lookback_days=lookback_days)
        papers.extend(rss_papers)

    logger.info(f"Collected {len(papers)} papers total (before dedup)")

    papers = deduplicate(papers, seen)
    logger.info(f"After dedup: {len(papers)} papers")

    if not papers:
        logger.error("No papers found. Check API connectivity and config.")
        sys.exit(1)

    with open(Path(output_dir) / "candidates.json", "w") as f:
        json.dump([{k: v for k, v in p.items() if k != "fulltext"} for p in papers], f, indent=2)

    # ── Phase 2: Extract full text ────────────────────────────────────────────
    logger.info("Phase 2: Extracting full text...")
    from src.processing.extractor import extract

    regen_script = os.environ.get("REGEN_SCRIPT", "").lower() == "true"
    for i, paper in enumerate(papers):
        if not regen_script or not paper.get("fulltext"):
            paper["fulltext"] = extract(paper)

    # ── Phase 3: LLM analysis (3 lenses) ─────────────────────────────────────
    logger.info("Phase 3: LLM analysis (contradicts / frontier / cross-disciplinary)...")
    from src.processing.analyzer import analyze_papers

    papers = analyze_papers(
        papers,
        llm_client=llm,
        model=config["llm"]["analysis_model"],
        cache_dir=cache_dir,
        max_workers=4,
    )

    # ── Phase 4: Rank and select ──────────────────────────────────────────────
    logger.info("Phase 4: Ranking by intellectual value (not journal prestige)...")
    from src.processing.ranker import select_papers, group_by_lens

    selected = select_papers(papers, config, state_dir=state_dir)
    groups = group_by_lens(selected)

    logger.info(f"Selected {len(selected)} papers:")
    logger.info(f"  Contradicts consensus: {len(groups['contradicts_consensus'])}")
    logger.info(f"  New frontier:          {len(groups['new_frontier'])}")
    logger.info(f"  Cross-disciplinary:    {len(groups['cross_disciplinary'])}")
    logger.info(f"  General highlights:    {len(groups['general'])}")

    with open(Path(output_dir) / "selected.json", "w") as f:
        json.dump(
            [{k: v for k, v in p.items() if k != "fulltext"} for p in selected],
            f, indent=2,
        )

    # ── Phase 5: Generate podcast script ─────────────────────────────────────
    logger.info("Phase 5: Generating podcast script...")
    from src.processing.script_generator import generate_scripts

    segments = generate_scripts(
        selected, groups,
        llm_client=llm,
        model=config["llm"]["script_model"],
        config=config,
    )

    logger.info(f"Generated {len(segments)} script segments")

    script_path = Path(output_dir) / "script.json"
    with open(script_path, "w") as f:
        json.dump(segments, f, indent=2)

    script_txt = Path(output_dir) / "script.txt"
    with open(script_txt, "w") as f:
        for seg in segments:
            f.write(f"\n{'='*60}\n")
            f.write(f"[{seg['type'].upper()}] {seg['title']}\n")
            f.write(f"{'='*60}\n")
            f.write(seg["text"] + "\n")

    # ── Phase 6: Text-to-speech ───────────────────────────────────────────────
    logger.info("Phase 6: Generating audio...")
    from src.outputs.tts import synthesize
    from src.outputs.audio import concat_with_transitions

    voice = config["podcast"]["voice"]
    rate = config["podcast"]["voice_rate"]
    segments_dir = Path(output_dir) / "segments"
    segments_dir.mkdir(exist_ok=True)
    segment_files = []

    for i, seg in enumerate(segments):
        seg_path = segments_dir / f"{i:03d}_{seg['type']}.mp3"
        if seg_path.exists() and seg_path.stat().st_size > 5000 and not regen_script:
            segment_files.append(seg_path)
            continue
        if synthesize(seg["text"], seg_path, voice=voice, rate=rate):
            segment_files.append(seg_path)
        else:
            logger.warning(f"TTS failed: {seg['title'][:50]}")

    if not segment_files:
        logger.error("No audio segments generated. Check TTS setup.")
        sys.exit(1)

    timestamps = concat_with_transitions(segment_files, final_mp3)

    # ── Phase 7: Save episode index ───────────────────────────────────────────
    episode = {
        "date": run_date,
        "mp3": str(final_mp3),
        "paper_count": len(selected),
        "segments": [
            {
                "index": i,
                "type": seg["type"],
                "title": seg["title"],
                "journal": seg.get("journal", ""),
                "url": seg.get("url", ""),
                "score": seg.get("score", 0),
                "timestamp_sec": timestamps[i] if i < len(timestamps) else 0,
            }
            for i, seg in enumerate(segments)
            if i < len(segment_files)
        ],
    }
    with open(episode_json, "w") as f:
        json.dump(episode, f, indent=2)

    # ── Phase 8: Publish to Notion ────────────────────────────────────────────
    logger.info("Phase 8: Publishing digest to Notion...")
    try:
        from src.outputs.notion_publish import publish_episode
        notion_url = publish_episode(
            date=run_date,
            groups=groups,
            paper_count=len(selected),
            script_path=script_txt,
        )
        if notion_url:
            logger.info(f"Notion digest: {notion_url}")
    except Exception as e:
        logger.warning(f"Notion publish failed (non-fatal): {e}")

    # ── Phase 9: Update seen IDs ──────────────────────────────────────────────
    new_seen = seen | {p["id"] for p in selected}
    save_seen(new_seen, state_dir)

    # ── Done ──────────────────────────────────────────────────────────────────
    size_mb = final_mp3.stat().st_size / 1024 / 1024
    logger.info("")
    logger.info("=== Episode complete ===")
    logger.info(f"  Output:   {final_mp3}")
    logger.info(f"  Size:     {size_mb:.1f} MB")
    logger.info(f"  Papers:   {len(selected)}")
    logger.info(f"  Segments: {len(segment_files)}")
    logger.info(f"  Script:   {script_txt}")


if __name__ == "__main__":
    main()
