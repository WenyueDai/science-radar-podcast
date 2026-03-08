"""
Notion integration — saves the weekly Science Radar digest as a Notion database page.

Page layout:
  Title: "Science Radar — YYYY-MM-DD"
  Sections (Heading 2):
    🔄 Challenging What We Know   — contradicts-consensus papers
    🚀 New Frontiers              — frontier-opening papers
    🌉 Bridging Worlds            — cross-disciplinary papers
    ✨ This Week's Highlights     — remaining papers
  Each item: title (linked) — snippet — [source] — score

Setup:
  1. notion.so/my-integrations → New integration (Internal) → copy token
  2. Create a Notion database → Share → Connect your integration
  3. Copy the 32-char database ID from the URL
  Required env vars:
    NOTION_TOKEN          — ntn_xxxx or secret_xxxx
    NOTION_DATABASE_ID    — 32-char hex ID (hyphens optional)
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

_API = "https://api.notion.com/v1"
_VERSION = "2022-06-28"

# Lens → section heading
LENS_HEADINGS = {
    "contradicts_consensus": "🔄 Challenging What We Know",
    "new_frontier": "🚀 New Frontiers",
    "cross_disciplinary": "🌉 Bridging Worlds",
    "general": "✨ This Week's Highlights",
}


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ.get('NOTION_TOKEN', '').strip()}",
        "Content-Type": "application/json",
        "Notion-Version": _VERSION,
    }


def _strip_html(s: str) -> str:
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup(s, "html.parser").get_text(" ", strip=True)
    except ImportError:
        return re.sub(r"<[^>]+>", " ", s).strip()


def _rich(text: str, url: str = "") -> Dict[str, Any]:
    obj: Dict[str, Any] = {"type": "text", "text": {"content": text[:2000]}}
    if url:
        obj["text"]["link"] = {"url": url}
    return obj


def _h2(text: str) -> Dict[str, Any]:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [_rich(text)]},
    }


def _bullet(paper: dict) -> Dict[str, Any]:
    """One bulleted item per paper: title (linked) — snippet — [source] — score."""
    title = (paper.get("title") or "").strip()[:200]
    url = (paper.get("url") or "").strip()
    source = (paper.get("journal") or paper.get("source_name") or "").strip()
    score = paper.get("score", 0)

    # Best one-liner: why_surprising > core_claim > abstract[:200]
    analysis = paper.get("analysis") or {}
    snippet = (
        _strip_html(analysis.get("why_surprising") or "")
        or _strip_html(analysis.get("core_claim") or "")
        or (paper.get("abstract") or "")[:200]
    ).strip()

    rich: List[Dict[str, Any]] = [_rich(title, url)]
    meta_parts = []
    if snippet:
        meta_parts.append(snippet[:300])
    if source:
        meta_parts.append(f"[{source}]")
    if score:
        meta_parts.append(f"score: {score:.1f}")
    if meta_parts:
        rich.append(_rich("  —  " + "  ·  ".join(meta_parts)))

    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": rich},
    }


def _spacer() -> Dict[str, Any]:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": []}}


def _build_blocks(date: str, groups: dict) -> List[Dict[str, Any]]:
    """Build all Notion blocks for the weekly digest."""
    blocks: List[Dict[str, Any]] = []

    for lens_key in ("contradicts_consensus", "new_frontier", "cross_disciplinary", "general"):
        papers = groups.get(lens_key, [])
        if not papers:
            continue
        blocks.append(_h2(LENS_HEADINGS[lens_key]))
        for paper in papers:
            blocks.append(_bullet(paper))
        blocks.append(_spacer())

    return blocks


def _api_call(method: str, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{_API}/{endpoint}", data=data, headers=_headers(), method=method
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def publish_episode(
    date: str,
    groups: dict,
    paper_count: int,
    script_path: Optional[Path] = None,
) -> Optional[str]:
    """
    Publish the weekly digest to a Notion database page.

    Args:
        date: Episode date string "YYYY-MM-DD"
        groups: Paper groups from ranker.group_by_lens()
        paper_count: Total number of selected papers
        script_path: Optional path to script.txt (unused in layout, kept for compat)

    Returns:
        Notion page URL, or None if env vars are missing / call fails.
    """
    token = os.environ.get("NOTION_TOKEN", "").strip()
    db_id = os.environ.get("NOTION_DATABASE_ID", "").strip().replace("-", "")
    if not token or not db_id:
        print("[notion] NOTION_TOKEN or NOTION_DATABASE_ID not set — skipping", flush=True)
        return None

    blocks = _build_blocks(date, groups)
    first_batch, rest = blocks[:100], blocks[100:]

    try:
        page = _api_call("POST", "pages", {
            "parent": {"database_id": db_id},
            "properties": {
                "Name": {"title": [{"type": "text", "text": {"content": f"Science Radar — {date}"}}]},
                "Date": {"date": {"start": date}},
            },
            "children": first_batch,
        })
        page_id = page.get("id", "")
        page_url = page.get("url", "")

        while rest:
            batch, rest = rest[:100], rest[100:]
            _api_call("PATCH", f"blocks/{page_id}/children", {"children": batch})

        print(f"[notion] Published: {page_url}", flush=True)
        return page_url

    except Exception as e:
        print(f"[notion] Warning: failed to publish — {e}", flush=True)
        return None
