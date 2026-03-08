#!/usr/bin/env python3
"""
Sync paper notes to Notion.

When the user writes a note on a paper in the site, it's saved to
state/paper_notes.json. This script creates a Notion page for each
new note, with the note text + paper metadata.

Required env vars:
  NOTION_TOKEN       — Notion integration token (ntn_...)
  NOTION_DATABASE_ID — ID of the Notion database to add pages to

Triggered by: .github/workflows/sync_notes.yml (on push to paper_notes.json)
"""

import json
import logging
import os
import sys
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sync-notion")

_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = _ROOT / "state"
NOTES_FILE = STATE_DIR / "paper_notes.json"
CREATED_FILE = STATE_DIR / "notion_created.json"  # tracks already-created pages

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def notion_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def create_notion_page(token: str, database_id: str, title: str, url: str,
                        note: str, date: str) -> str | None:
    """Create a Notion page. Returns page ID or None on failure."""
    # Format date as ISO 8601 for Notion date property (YYYY-MM-DD)
    notion_date = date if len(date) == 10 else None

    payload = {
        "parent": {"database_id": database_id},
        "properties": {
            "Name": {
                "title": [{"text": {"content": title[:200]}}]
            },
            "Date": {
                "date": {"start": notion_date} if notion_date else None
            },
            "Description": {
                "rich_text": [{"text": {"content": note[:2000]}}]
            },
        },
        "children": [
            # Green callout with the user's note
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [{"type": "text", "text": {"content": note}}],
                    "icon": {"emoji": "📝"},
                    "color": "green_background",
                },
            },
        ],
    }

    # Remove Date if not available (avoids Notion API error)
    if not notion_date:
        del payload["properties"]["Date"]

    # Add bookmark if URL provided
    if url:
        payload["children"].append({
            "object": "block",
            "type": "bookmark",
            "bookmark": {"url": url},
        })

    resp = requests.post(
        f"{NOTION_API}/pages",
        headers=notion_headers(token),
        json=payload,
        timeout=15,
    )
    if resp.ok:
        return resp.json().get("id")
    else:
        logger.error(f"Notion API error {resp.status_code}: {resp.text[:200]}")
        return None


def main():
    token = os.environ.get("NOTION_TOKEN")
    database_id = os.environ.get("NOTION_DATABASE_ID")

    if not token or not database_id:
        logger.error("Missing NOTION_TOKEN or NOTION_DATABASE_ID env vars.")
        logger.error("Set them in GitHub secrets to enable Notion sync.")
        sys.exit(0)  # Exit 0 — not a fatal error, just skip

    if not NOTES_FILE.exists():
        logger.info("No paper_notes.json found, nothing to sync.")
        return

    with open(NOTES_FILE) as f:
        notes = json.load(f)  # {date: {url: {note, title, source}}}

    created = {}
    if CREATED_FILE.exists():
        with open(CREATED_FILE) as f:
            created = json.load(f)  # {url: notion_page_id}

    synced = 0
    for date, date_notes in notes.items():
        for url, val in date_notes.items():
            if url in created:
                continue  # already synced

            if isinstance(val, str):
                note_text = val
                title = url
            else:
                note_text = val.get("note", "")
                title = val.get("title", url)

            if not note_text.strip():
                continue

            logger.info(f"Creating Notion page: {title[:60]}")
            page_id = create_notion_page(token, database_id, title, url, note_text, date)
            if page_id:
                created[url] = page_id
                synced += 1

    if synced > 0:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(CREATED_FILE, "w") as f:
            json.dump(created, f, indent=2)
        logger.info(f"Synced {synced} new note(s) to Notion.")
    else:
        logger.info("No new notes to sync.")


if __name__ == "__main__":
    main()
