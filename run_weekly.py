#!/usr/bin/env python3
"""
Science Radar Podcast — Weekly Runner
Fetches high-impact papers from the past week, analyzes them through
3 special lenses, and generates a ~1h podcast episode.

Usage:
    python run_weekly.py                    # run for this week
    RUN_DATE=2026-03-01 python run_weekly.py  # run for a specific week
    REGEN_SCRIPT=true python run_weekly.py    # re-generate script from cached analyses
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
        raise ValueError(f"Missing env var: {config['llm']['api_key_env']}\n"
                         "Get a free key at https://openrouter.ai")
    return OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )


# ── Main pipeline ──────────────────────────────────────────────────────────────

def main():
    config = load_config()

    # Determine episode date — treat empty string same as missing
    run_date = os.environ.get("RUN_DATE", "").strip() or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    logger.info(f"=== Science Radar — episode {run_date} ===")

    # Paths
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
    from src.collectors import openalex, arxiv, rss
    from src.utils.dedup import load_seen, deduplicate, save_seen

    seen = load_seen(state_dir)
    papers = []

    # OpenAlex (high-impact journals)
    journals = config.get("target_journals", [])
    if journals:
        oa_papers = openalex.fetch_papers(
            journals, lookback_days=lookback_days,
            max_per_journal=config["limits"]["max_papers_per_journal"]
        )
        papers.extend(oa_papers)

    # arXiv preprints
    arxiv_cats = config.get("arxiv_categories", [])
    if arxiv_cats:
        ax_papers = arxiv.fetch_papers(arxiv_cats, lookback_days=lookback_days, max_per_category=6)
        papers.extend(ax_papers)

    # RSS feeds
    rss_sources = config.get("rss_sources", [])
    if rss_sources:
        rss_papers = rss.fetch_papers(rss_sources, lookback_days=lookback_days)
        papers.extend(rss_papers)

    logger.info(f"Collected {len(papers)} papers total (before dedup)")

    # Deduplicate
    papers = deduplicate(papers, seen)
    logger.info(f"After dedup: {len(papers)} papers")

    if not papers:
        logger.error("No papers found. Check your API connectivity and config.")
        sys.exit(1)

    # Save candidate list
    with open(Path(output_dir) / "candidates.json", "w") as f:
        json.dump([{k: v for k, v in p.items() if k != "fulltext"} for p in papers], f, indent=2)

    # ── Phase 2: Extract full text ────────────────────────────────────────────
    logger.info("Phase 2: Extracting full text...")
    from src.processing.extractor import extract

    regen_script = os.environ.get("REGEN_SCRIPT", "").lower() == "true"
    for i, paper in enumerate(papers):
        if not regen_script or not paper.get("fulltext"):
            paper["fulltext"] = extract(paper)
            if len(paper.get("fulltext", "")) > 1500:
                logger.debug(f"  [{i+1}] Full text OK: {paper['title'][:60]}")

    # ── Phase 3: LLM analysis (3 lenses) ─────────────────────────────────────
    logger.info("Phase 3: LLM analysis...")
    from src.processing.analyzer import analyze_papers

    papers = analyze_papers(
        papers,
        llm_client=llm,
        model=config["llm"]["analysis_model"],
        cache_dir=cache_dir,
        max_workers=4,
    )

    # ── Phase 4: Rank and select ──────────────────────────────────────────────
    logger.info("Phase 4: Ranking and selecting...")
    from src.processing.ranker import select_papers, group_by_lens

    selected = select_papers(papers, config, state_dir=state_dir)
    groups = group_by_lens(selected)

    logger.info(f"Selected {len(selected)} papers:")
    logger.info(f"  Contradicts consensus: {len(groups['contradicts_consensus'])}")
    logger.info(f"  New frontier:          {len(groups['new_frontier'])}")
    logger.info(f"  Cross-disciplinary:    {len(groups['cross_disciplinary'])}")
    logger.info(f"  General highlights:    {len(groups['general'])}")

    # Save selected papers
    with open(Path(output_dir) / "selected.json", "w") as f:
        selected_export = []
        for p in selected:
            exp = {k: v for k, v in p.items() if k != "fulltext"}
            selected_export.append(exp)
        json.dump(selected_export, f, indent=2)

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

    # Save script
    script_path = Path(output_dir) / "script.json"
    with open(script_path, "w") as f:
        json.dump(segments, f, indent=2)

    # Also save human-readable script
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
    segment_files = []

    segments_dir = Path(output_dir) / "segments"
    segments_dir.mkdir(exist_ok=True)

    for i, seg in enumerate(segments):
        seg_path = segments_dir / f"{i:03d}_{seg['type']}.mp3"

        # Skip if already exists and valid
        if seg_path.exists() and seg_path.stat().st_size > 5000 and not regen_script:
            logger.debug(f"  [{i+1}] Reusing cached: {seg_path.name}")
            segment_files.append(seg_path)
            continue

        ok = synthesize(seg["text"], seg_path, voice=voice, rate=rate)
        if ok:
            segment_files.append(seg_path)
            logger.debug(f"  [{i+1}] TTS OK: {seg['type']} — {seg['title'][:50]}")
        else:
            logger.warning(f"  [{i+1}] TTS FAILED: {seg['title'][:50]}")

    if not segment_files:
        logger.error("No audio segments generated. Check TTS setup.")
        sys.exit(1)

    # Concatenate with transitions
    timestamps = concat_with_transitions(segment_files, final_mp3)

    # ── Phase 7: Save episode index ───────────────────────────────────────────
    episode = {
        "date": run_date,
        "mp3": str(final_mp3),
        "duration_sec": sum(timestamps[1:][i] - timestamps[i] for i in range(len(timestamps)-1)) if len(timestamps) > 1 else 0,
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

    # ── Phase 8: Update seen IDs ──────────────────────────────────────────────
    new_seen = seen | {p["id"] for p in selected}
    save_seen(new_seen, state_dir)

    # ── Done ──────────────────────────────────────────────────────────────────
    size_mb = final_mp3.stat().st_size / 1024 / 1024
    logger.info(f"")
    logger.info(f"=== Episode complete ===")
    logger.info(f"  Output:   {final_mp3}")
    logger.info(f"  Size:     {size_mb:.1f} MB")
    logger.info(f"  Papers:   {len(selected)}")
    logger.info(f"  Segments: {len(segment_files)}")
    logger.info(f"  Script:   {script_txt}")


if __name__ == "__main__":
    main()
