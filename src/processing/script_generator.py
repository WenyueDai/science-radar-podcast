"""
Podcast script generator.

Structure of ~1h episode:
  1. Intro (fixed text from config)
  2. Section: "Challenging What We Know" (contradicts_consensus papers)
  3. Section: "New Frontiers" (new_frontier papers)
  4. Section: "Bridging Worlds" (cross_disciplinary papers)
  5. Section: "This Week's Highlights" (remaining papers — quick roundup)
  6. SYNTHESIS SEGMENT: Cross-domain connections (LLM finds hidden links across ALL papers)
  7. Outro (fixed text from config)

Each paper gets one LLM call (not batched) for consistent quality.
"""

import logging
import time
from openai import OpenAI

logger = logging.getLogger(__name__)

# ── Per-paper prompts ──────────────────────────────────────────────────────────

SYSTEM_DEEP = """You are the host of Science Radar, a podcast for scientifically curious people.
Your style is intelligent, engaging, and direct. You explain ideas clearly without dumbing them down.
You get genuinely excited about surprising findings. No filler phrases. No "certainly!" or "great question!".
Start immediately with the science. Never invent numbers, methods, or results not in the source text."""

PROMPT_DEEP = """Write a podcast segment about this paper. Length: 250-350 words.

TITLE: {title}
JOURNAL: {journal}
LENS: {lens}

NOTES FROM ANALYSIS:
{analysis_text}

ABSTRACT / FULL TEXT EXCERPT:
{fulltext}

Write the segment now. Start with a hook sentence. Cover: what the researchers found,
how they found it, why it matters, and what it challenges or opens up.
Mention the journal naturally. End with a forward-looking sentence.
Use ONLY information from the notes and text above — do NOT invent details.
Do NOT use sub-headings. Write flowing prose only."""

PROMPT_ROUNDUP = """Write a short podcast roundup blurb about this paper. Length: 80-120 words.

TITLE: {title}
JOURNAL: {journal}

NOTES FROM ANALYSIS:
{analysis_text}

Start with the key finding. Mention the journal. End with one sentence on why it matters.
Flowing prose only. No invented details."""

# ── Synthesis prompt ───────────────────────────────────────────────────────────

SYSTEM_SYNTHESIS = """You are a science philosopher and cross-disciplinary thinker.
You find unexpected connections between discoveries from completely different fields.
Your goal is to find hidden patterns, analogies, and implications that no single scientist
would see because they are too deep in their own field. Be specific. Be bold. Be surprising."""

PROMPT_SYNTHESIS = """You are given a set of scientific papers published this week across all fields.
Your job: find the most surprising NON-OBVIOUS connections between them.

PAPERS THIS WEEK:
{paper_summaries}

Write a 400-600 word podcast closing segment called "The Big Picture".
- Identify 2-3 unexpected thematic connections across different fields
- Explain what these connections might mean for science broadly
- Suggest one bold hypothesis or research direction that emerges from combining ideas across papers
- Be specific — name the papers and fields you're connecting
- Do NOT just summarize individual papers again. Focus on CONNECTIONS and IMPLICATIONS.
Start with: "Now, stepping back from the individual papers this week..."
End with a thought-provoking question or observation."""


def generate_scripts(papers: list[dict], groups: dict, llm_client: OpenAI,
                     model: str, config: dict) -> list[dict]:
    """
    Generate podcast script segments for each paper + synthesis.
    Returns list of segment dicts: {type, title, text, paper_id}
    """
    segments = []

    # Intro
    intro_text = config.get("podcast", {}).get("intro_text", "Welcome to Science Radar.")
    segments.append({"type": "intro", "title": "Intro", "text": intro_text, "paper_id": None})

    # Section 1: Challenging What We Know
    cc_papers = groups.get("contradicts_consensus", [])
    if cc_papers:
        segments.append({"type": "section_header", "title": "Challenging What We Know",
                         "text": "Our first section this week: Challenging What We Know. "
                                 "These papers take aim at ideas we thought were settled.",
                         "paper_id": None})
        for paper in cc_papers:
            seg = _generate_paper_segment(paper, llm_client, model, is_deep=True)
            if seg:
                segments.append(seg)

    # Section 2: New Frontiers
    nf_papers = groups.get("new_frontier", [])
    if nf_papers:
        segments.append({"type": "section_header", "title": "New Frontiers",
                         "text": "Next: New Frontiers. Papers that are opening doors "
                                 "into territory science has barely touched.",
                         "paper_id": None})
        for paper in nf_papers:
            seg = _generate_paper_segment(paper, llm_client, model, is_deep=True)
            if seg:
                segments.append(seg)

    # Section 3: Bridging Worlds
    cd_papers = groups.get("cross_disciplinary", [])
    if cd_papers:
        segments.append({"type": "section_header", "title": "Bridging Worlds",
                         "text": "Now for Bridging Worlds — papers that connect ideas "
                                 "from fields that rarely talk to each other.",
                         "paper_id": None})
        for paper in cd_papers:
            seg = _generate_paper_segment(paper, llm_client, model, is_deep=True)
            if seg:
                segments.append(seg)

    # Section 4: This Week's Highlights (general / lower-scored papers)
    general_papers = groups.get("general", [])
    if general_papers:
        segments.append({"type": "section_header", "title": "This Week's Highlights",
                         "text": "And now, a quick tour through this week's other noteworthy papers.",
                         "paper_id": None})
        for paper in general_papers:
            seg = _generate_paper_segment(paper, llm_client, model, is_deep=False)
            if seg:
                segments.append(seg)

    # Synthesis segment
    synthesis = _generate_synthesis(papers, llm_client, model)
    if synthesis:
        segments.append({"type": "synthesis", "title": "The Big Picture",
                         "text": synthesis, "paper_id": None})

    # Outro
    outro_text = config.get("podcast", {}).get("outro_text", "Thanks for listening to Science Radar.")
    segments.append({"type": "outro", "title": "Outro", "text": outro_text, "paper_id": None})

    return segments


def _fallback_segment(paper: dict, is_deep: bool) -> dict:
    """Build a minimal but honest segment from abstract when LLM is unavailable."""
    title = paper["title"]
    journal = paper.get("journal", "")
    abstract = (paper.get("abstract") or "").strip()
    analysis = (paper.get("analysis_text") or "").strip()

    # Pull CORE CLAIM from analysis if it exists
    core = ""
    for line in analysis.splitlines():
        if line.strip().upper().startswith("CORE CLAIM:"):
            core = line.split(":", 1)[1].strip()
            break
    if not core:
        core = abstract[:400] if abstract else "Details not available."

    if is_deep:
        text = (
            f"{title}. "
            f"Published in {journal}. "
            f"{core} "
            f"{abstract[len(core):600].strip()}"
        ).strip()
    else:
        text = f"{title} — {journal}. {core[:300].strip()}"

    return {
        "type": "deep_dive" if is_deep else "roundup",
        "title": title,
        "text": text,
        "paper_id": paper["id"],
        "journal": journal,
        "score": paper.get("score", 0),
        "url": paper.get("url", ""),
    }


def _generate_paper_segment(paper: dict, client: OpenAI, model: str, is_deep: bool,
                              retries: int = 3) -> dict | None:
    """Generate script for a single paper using plain-text analysis as context."""
    analysis_text = paper.get("analysis_text") or paper.get("abstract", "")[:500]
    lens = paper.get("lens", "GENERAL")

    if is_deep:
        prompt = PROMPT_DEEP.format(
            title=paper["title"],
            journal=paper.get("journal", ""),
            lens=lens,
            analysis_text=analysis_text[:3000],
            fulltext=(paper.get("fulltext") or paper.get("abstract", ""))[:3000],
        )
        max_tokens = 2800
    else:
        prompt = PROMPT_ROUNDUP.format(
            title=paper["title"],
            journal=paper.get("journal", ""),
            analysis_text=analysis_text[:1500],
        )
        max_tokens = 1200

    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_DEEP},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=max_tokens,
                timeout=60,
            )
            text = (response.choices[0].message.content or "").strip()
            if text:
                return {
                    "type": "deep_dive" if is_deep else "roundup",
                    "title": paper["title"],
                    "text": text,
                    "paper_id": paper["id"],
                    "journal": paper.get("journal", ""),
                    "score": paper.get("score", 0),
                    "url": paper.get("url", ""),
                }
            logger.warning(f"Empty LLM response for '{paper['title'][:50]}' (attempt {attempt+1})")
        except Exception as e:
            logger.warning(f"Script gen failed for '{paper['title'][:50]}' (attempt {attempt+1}): {type(e).__name__}: {e}")
            if attempt < retries - 1:
                time.sleep(3 ** attempt)

    # Fallback: build segment from abstract when LLM is unavailable
    logger.warning(f"All LLM retries failed — using abstract fallback for '{paper['title'][:60]}'")
    return _fallback_segment(paper, is_deep)


def _generate_synthesis(papers: list[dict], client: OpenAI, model: str,
                         retries: int = 3) -> str | None:
    """Generate the cross-domain synthesis segment."""
    # Build paper summary list
    summaries = []
    for i, p in enumerate(papers[:25], 1):  # limit to 25 for context
        analysis_text = p.get("analysis_text", "")
        core = p.get("abstract", "")[:200]
        for line in analysis_text.splitlines():
            if line.strip().upper().startswith("CORE CLAIM:"):
                core = line.split(":", 1)[1].strip()
                break
        summaries.append(f"[{i}] {p['title']} ({p.get('journal', 'Unknown')}) [lens: {p.get('lens','GENERAL')}]\n    {core}")

    paper_summaries = "\n\n".join(summaries)

    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_SYNTHESIS},
                    {"role": "user", "content": PROMPT_SYNTHESIS.format(paper_summaries=paper_summaries)},
                ],
                temperature=0.5,  # more creative for synthesis
                max_tokens=3000,
                timeout=60,
            )
            text = response.choices[0].message.content.strip()
            if text:
                logger.info("Synthesis segment generated successfully")
                return text
        except Exception as e:
            logger.warning(f"Synthesis failed (attempt {attempt+1}): {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)

    return None
