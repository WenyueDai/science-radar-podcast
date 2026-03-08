#!/usr/bin/env python3
"""
Build the Science Radar GitHub Pages site.
Purple-themed, includes audio player with segment seeking + episode archive.
"""

from __future__ import annotations
import json
import os
import html
from pathlib import Path
from datetime import datetime, timezone

_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = Path(os.environ.get("PODCAST_OUTPUT", str(_ROOT / "output")))
SITE_DIR = Path(os.environ.get("SITE_DIR", str(_ROOT / "docs")))
STATE_DIR = _ROOT / "state"

PODCAST_TITLE = os.environ.get("PODCAST_TITLE", "Science Radar")
PODCAST_SUBTITLE = "Weekly deep-dives into surprising, frontier, and cross-disciplinary science"
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")  # e.g. "username/science-radar-podcast"


def load_episodes() -> list[dict]:
    """Load all episode.json files from output directories, sorted newest first."""
    episodes = []
    if not OUTPUT_DIR.exists():
        return episodes
    for ep_dir in sorted(OUTPUT_DIR.iterdir(), reverse=True):
        ep_file = ep_dir / "episode.json"
        if ep_file.exists():
            try:
                ep = json.loads(ep_file.read_text())
                ep["dir"] = str(ep_dir)
                episodes.append(ep)
            except Exception:
                pass
    return episodes


def get_release_url(date: str) -> str:
    """Construct GitHub Release MP3 URL."""
    if not GITHUB_REPO:
        return ""
    return f"https://github.com/{GITHUB_REPO}/releases/download/episode-{date}/podcast_{date}.mp3"


def build_index_html(episodes: list[dict]) -> str:
    latest = episodes[0] if episodes else None
    latest_date = latest["date"] if latest else ""
    latest_url = get_release_url(latest_date) if latest else ""
    latest_segments = latest.get("segments", []) if latest else []

    # Build segment list for JS seeking
    segments_js = json.dumps([
        {"index": s["index"], "type": s["type"], "title": s["title"],
         "journal": s.get("journal", ""), "url": s.get("url", ""),
         "ts": s.get("timestamp_sec", 0)}
        for s in latest_segments
    ])

    # Episode archive rows
    archive_rows = ""
    for ep in episodes:
        date = ep.get("date", "")
        count = ep.get("paper_count", 0)
        ep_url = get_release_url(date)
        archive_rows += f"""
        <tr>
          <td>{html.escape(date)}</td>
          <td>{count} papers</td>
          <td>{"<a href='" + html.escape(ep_url) + "'>MP3</a>" if ep_url else "—"}</td>
        </tr>"""

    # Paper list for latest episode
    paper_items = ""
    for seg in latest_segments:
        if seg["type"] not in ("deep_dive", "roundup"):
            continue
        title = html.escape(seg.get("title", ""))
        journal = html.escape(seg.get("journal", ""))
        url = html.escape(seg.get("url", ""))
        ts = seg.get("ts", 0)
        idx = seg.get("index", 0)
        link = f'<a href="{url}" target="_blank">{title}</a>' if url else title
        paper_items += f"""
          <li class="paper-item" onclick="seekTo({ts})" data-idx="{idx}">
            <span class="paper-num">[{idx}]</span>
            <span class="paper-title">{link}</span>
            {"<span class='paper-journal'>" + journal + "</span>" if journal else ""}
          </li>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(PODCAST_TITLE)}</title>
  <style>
    :root {{
      --purple:      #7c3aed;
      --purple-dark: #5b21b6;
      --purple-light:#ede9fe;
      --purple-mid:  #a78bfa;
      --bg:          #0f0a1e;
      --surface:     #1a1033;
      --surface2:    #241648;
      --text:        #e2d9f3;
      --text-muted:  #9d7ecf;
      --border:      #3b2f6e;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
    }}

    /* Header */
    header {{
      background: linear-gradient(135deg, var(--purple-dark) 0%, var(--purple) 100%);
      padding: 2rem;
      text-align: center;
    }}
    header h1 {{ font-size: 2rem; font-weight: 800; letter-spacing: -0.5px; }}
    header p {{ color: var(--purple-light); margin-top: 0.4rem; font-size: 0.95rem; }}

    /* Layout */
    main {{ max-width: 860px; margin: 0 auto; padding: 2rem 1rem; }}

    /* Player card */
    .player-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.5rem;
      margin-bottom: 2rem;
    }}
    .player-card h2 {{ font-size: 1.1rem; color: var(--purple-mid); margin-bottom: 1rem; }}
    audio {{
      width: 100%;
      accent-color: var(--purple);
      margin-bottom: 0.5rem;
    }}
    audio::-webkit-media-controls-panel {{ background: var(--surface2); }}
    .episode-meta {{ font-size: 0.8rem; color: var(--text-muted); }}

    /* Segment seeking hint */
    .seek-hint {{
      font-size: 0.78rem;
      color: var(--text-muted);
      margin-top: 0.5rem;
    }}

    /* Papers list */
    .section-title {{
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: var(--purple-mid);
      margin: 1.5rem 0 0.75rem;
      font-weight: 600;
    }}
    .papers-list {{
      list-style: none;
      display: flex;
      flex-direction: column;
      gap: 0.4rem;
    }}
    .paper-item {{
      background: var(--surface2);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.6rem 0.9rem;
      cursor: pointer;
      display: flex;
      align-items: baseline;
      gap: 0.5rem;
      transition: border-color 0.15s, background 0.15s;
    }}
    .paper-item:hover {{ border-color: var(--purple); background: var(--surface); }}
    .paper-item.active {{ border-color: var(--purple-mid); background: var(--surface); }}
    .paper-num {{ color: var(--purple-mid); font-size: 0.75rem; flex-shrink: 0; font-weight: 600; }}
    .paper-title {{ font-size: 0.88rem; flex: 1; }}
    .paper-title a {{ color: var(--text); text-decoration: none; }}
    .paper-title a:hover {{ color: var(--purple-mid); }}
    .paper-journal {{ font-size: 0.72rem; color: var(--text-muted); flex-shrink: 0; }}

    /* Archive table */
    .archive-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.5rem;
      margin-top: 2rem;
    }}
    .archive-card h2 {{ font-size: 1rem; color: var(--purple-mid); margin-bottom: 1rem; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
    th {{ text-align: left; color: var(--text-muted); font-weight: 500;
          padding: 0.4rem 0.5rem; border-bottom: 1px solid var(--border); }}
    td {{ padding: 0.5rem 0.5rem; border-bottom: 1px solid var(--border); }}
    td a {{ color: var(--purple-mid); text-decoration: none; }}
    td a:hover {{ text-decoration: underline; }}
    tr:last-child td {{ border-bottom: none; }}

    /* RSS link */
    .rss-link {{
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      color: var(--purple-mid);
      font-size: 0.82rem;
      text-decoration: none;
      margin-top: 1.5rem;
    }}
    .rss-link:hover {{ color: var(--purple); }}

    /* Animated mascot */
    .mascot {{
      text-align: center;
      font-size: 2.5rem;
      margin: 1.5rem 0 0.5rem;
      animation: float 3s ease-in-out infinite;
    }}
    @keyframes float {{
      0%, 100% {{ transform: translateY(0); }}
      50% {{ transform: translateY(-6px); }}
    }}

    footer {{
      text-align: center;
      padding: 2rem;
      color: var(--text-muted);
      font-size: 0.78rem;
    }}
  </style>
</head>
<body>

<header>
  <h1>🔭 {html.escape(PODCAST_TITLE)}</h1>
  <p>{html.escape(PODCAST_SUBTITLE)}</p>
</header>

<main>
  <div class="mascot">🧪</div>

  {"<!-- No episodes yet -->" if not latest else f'''
  <div class="player-card">
    <h2>Latest Episode — {html.escape(latest_date)}</h2>
    <audio id="player" controls preload="none">
      {"<source src='" + html.escape(latest_url) + "' type='audio/mpeg'>" if latest_url else "<!-- No audio URL configured -->"}
      Your browser does not support audio.
    </audio>
    <div class="episode-meta">{latest.get("paper_count", 0)} papers · click a paper below to jump to that segment</div>
    <div class="seek-hint">⬇ Click any paper to seek directly to its segment</div>
  </div>

  <div class="section-title">This week&apos;s papers</div>
  <ul class="papers-list" id="paper-list">
    {paper_items}
  </ul>
  '''}

  {f'''
  <div class="archive-card">
    <h2>Episode Archive</h2>
    <table>
      <thead><tr><th>Date</th><th>Papers</th><th>Audio</th></tr></thead>
      <tbody>{archive_rows}</tbody>
    </table>
  </div>
  ''' if len(episodes) > 1 else ""}

  <a href="feed.xml" class="rss-link">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
      <path d="M6.18 15.64a2.18 2.18 0 0 1 2.18 2.18C8.36 19.01 7.38 20 6.18 20 4.98 20 4 19.01 4 17.82a2.18 2.18 0 0 1 2.18-2.18M4 4.44A15.56 15.56 0 0 1 19.56 20h-2.83A12.73 12.73 0 0 0 4 7.27V4.44m0 5.66a9.9 9.9 0 0 1 9.9 9.9h-2.83A7.07 7.07 0 0 0 4 12.93V10.1z"/>
    </svg>
    Subscribe via RSS / Podcast App
  </a>
</main>

<footer>
  Generated automatically by Science Radar &middot;
  Powered by OpenRouter + Edge TTS &middot; All free
</footer>

<script>
const segments = {segments_js};
const player = document.getElementById("player");
const items = document.querySelectorAll(".paper-item");

function seekTo(ts) {{
  if (!player) return;
  player.currentTime = Math.max(0, ts - 1.5);
  player.play();
}}

// Highlight active segment as audio plays
if (player) {{
  player.addEventListener("timeupdate", () => {{
    const t = player.currentTime;
    const paperSegs = segments.filter(s => s.type === "deep_dive" || s.type === "roundup");
    let activeIdx = -1;
    for (let i = paperSegs.length - 1; i >= 0; i--) {{
      if (t >= paperSegs[i].ts) {{ activeIdx = paperSegs[i].index; break; }}
    }}
    items.forEach(el => {{
      el.classList.toggle("active", parseInt(el.dataset.idx) === activeIdx);
    }});
  }});
}}
</script>
</body>
</html>"""


def build_rss_feed(episodes: list[dict]) -> str:
    items = ""
    for ep in episodes[:20]:
        date = ep.get("date", "")
        count = ep.get("paper_count", 0)
        url = get_release_url(date)
        pub_date = datetime.strptime(date, "%Y-%m-%d").strftime("%a, %d %b %Y 04:00:00 +0000") if date else ""
        items += f"""
  <item>
    <title>{html.escape(PODCAST_TITLE)} — {html.escape(date)}</title>
    <description>{count} papers analyzed</description>
    <pubDate>{html.escape(pub_date)}</pubDate>
    <guid isPermaLink="false">episode-{html.escape(date)}</guid>
    {"<enclosure url='" + html.escape(url) + "' type='audio/mpeg'/>" if url else ""}
  </item>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
<channel>
  <title>{html.escape(PODCAST_TITLE)}</title>
  <description>{html.escape(PODCAST_SUBTITLE)}</description>
  <language>en</language>
  <lastBuildDate>{datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")}</lastBuildDate>
  {items}
</channel>
</rss>"""


def main():
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    episodes = load_episodes()

    index_html = build_index_html(episodes)
    (SITE_DIR / "index.html").write_text(index_html, encoding="utf-8")

    rss_xml = build_rss_feed(episodes)
    (SITE_DIR / "feed.xml").write_text(rss_xml, encoding="utf-8")

    print(f"Site built: {SITE_DIR}/index.html ({len(episodes)} episodes)")


if __name__ == "__main__":
    main()
