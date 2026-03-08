#!/usr/bin/env python3
"""
Build the Science Radar GitHub Pages site.
Purple-themed. Features:
  - Audio player with per-paper segment seeking
  - Feedback checkboxes (liked papers → improve future ranking)
  - Note-taking per paper (syncs to Notion)
  - Missed paper submission form
  - Episode archive
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
GITHUB_REPO = os.environ.get("GITHUB_REPO", "WenyueDai/science-radar-podcast")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "31d5f58ea8c280409e43fba26a6aabc3")


def load_episodes() -> list[dict]:
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
    if not GITHUB_REPO:
        return ""
    return f"https://github.com/{GITHUB_REPO}/releases/download/episode-{date}/podcast_{date}.mp3"


def build_index_html(episodes: list[dict]) -> str:
    latest = episodes[0] if episodes else None
    latest_date = latest["date"] if latest else ""
    latest_url = get_release_url(latest_date) if latest else ""
    latest_segments = latest.get("segments", []) if latest else []

    segments_js = json.dumps([
        {"index": s["index"], "type": s["type"], "title": s["title"],
         "journal": s.get("journal", ""), "url": s.get("url", ""),
         "ts": s.get("timestamp_sec", 0)}
        for s in latest_segments
    ])

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

    paper_items = ""
    for seg in latest_segments:
        if seg["type"] not in ("deep_dive", "roundup"):
            continue
        title = html.escape(seg.get("title", ""))
        journal = html.escape(seg.get("journal", ""))
        url = html.escape(seg.get("url", ""))
        ts = seg.get("ts", 0)
        idx = seg.get("index", 0)
        link = f'<a href="{url}" target="_blank" onclick="event.stopPropagation()">{title}</a>' if url else title
        paper_items += f"""
          <li class="paper-item" data-idx="{idx}" data-ts="{ts}"
              data-url="{url}" data-title="{title}" data-journal="{journal}"
              data-date="{html.escape(latest_date)}">
            <div class="paper-row" onclick="seekTo({ts})">
              <input type="checkbox" class="like-cb" title="Mark as interesting"
                onclick="event.stopPropagation()" onchange="saveLikeLocally(this)">
              <span class="paper-num">[{idx}]</span>
              <span class="paper-title">{link}</span>
              {"<span class='paper-journal'>" + journal + "</span>" if journal else ""}
              <button class="note-btn" title="Add note" onclick="event.stopPropagation(); toggleNote(this)">✏️</button>
            </div>
            <div class="note-area" style="display:none">
              <textarea class="note-input" placeholder="Your note about this paper..."></textarea>
              <button class="note-save-btn" onclick="saveNote(this)">Save note</button>
              <span class="note-status"></span>
            </div>
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
      --green:       #10b981;
      --red:         #ef4444;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
             background: var(--bg); color: var(--text); min-height: 100vh; }}

    header {{ background: linear-gradient(135deg, var(--purple-dark) 0%, var(--purple) 100%);
               padding: 2rem; text-align: center; }}
    header h1 {{ font-size: 2rem; font-weight: 800; }}
    header p {{ color: var(--purple-light); margin-top: 0.4rem; font-size: 0.95rem; }}

    main {{ max-width: 860px; margin: 0 auto; padding: 2rem 1rem; }}

    .card {{ background: var(--surface); border: 1px solid var(--border);
              border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; }}
    .card h2 {{ font-size: 1rem; color: var(--purple-mid); margin-bottom: 1rem; }}

    audio {{ width: 100%; accent-color: var(--purple); margin-bottom: 0.5rem; }}
    .episode-meta {{ font-size: 0.8rem; color: var(--text-muted); }}

    .section-title {{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px;
                       color: var(--purple-mid); margin: 1.5rem 0 0.75rem; font-weight: 600; }}

    /* Paper list */
    .papers-list {{ list-style: none; display: flex; flex-direction: column; gap: 0.4rem; }}
    .paper-item {{ background: var(--surface2); border: 1px solid var(--border);
                   border-radius: 8px; overflow: hidden;
                   transition: border-color 0.15s; }}
    .paper-item:hover {{ border-color: var(--purple); }}
    .paper-item.active {{ border-color: var(--purple-mid); }}
    .paper-row {{ display: flex; align-items: center; gap: 0.5rem;
                  padding: 0.6rem 0.9rem; cursor: pointer; }}
    .like-cb {{ width: 15px; height: 15px; accent-color: var(--purple);
                flex-shrink: 0; cursor: pointer; }}
    .paper-num {{ color: var(--purple-mid); font-size: 0.75rem; flex-shrink: 0; font-weight: 600; }}
    .paper-title {{ font-size: 0.88rem; flex: 1; }}
    .paper-title a {{ color: var(--text); text-decoration: none; }}
    .paper-title a:hover {{ color: var(--purple-mid); }}
    .paper-journal {{ font-size: 0.72rem; color: var(--text-muted); flex-shrink: 0; }}
    .note-btn {{ background: none; border: none; cursor: pointer; font-size: 0.9rem;
                 padding: 0 0.2rem; opacity: 0.5; flex-shrink: 0; }}
    .note-btn:hover {{ opacity: 1; }}

    /* Note area */
    .note-area {{ padding: 0.5rem 0.9rem 0.9rem; border-top: 1px solid var(--border); }}
    .note-input {{ width: 100%; background: var(--bg); border: 1px solid var(--border);
                   color: var(--text); border-radius: 6px; padding: 0.5rem; font-size: 0.85rem;
                   min-height: 80px; resize: vertical; font-family: inherit; }}
    .note-save-btn {{ margin-top: 0.4rem; background: var(--purple); color: white;
                      border: none; border-radius: 6px; padding: 0.3rem 0.8rem;
                      cursor: pointer; font-size: 0.8rem; }}
    .note-save-btn:hover {{ background: var(--purple-dark); }}
    .note-status {{ font-size: 0.75rem; color: var(--green); margin-left: 0.5rem; }}

    /* Feedback toolbar */
    .feedback-toolbar {{ display: flex; gap: 0.75rem; align-items: center;
                          margin-top: 1rem; flex-wrap: wrap; }}
    .btn {{ background: var(--purple); color: white; border: none; border-radius: 8px;
             padding: 0.45rem 1rem; cursor: pointer; font-size: 0.85rem; }}
    .btn:hover {{ background: var(--purple-dark); }}
    .btn.secondary {{ background: var(--surface2); border: 1px solid var(--border); }}
    .btn.secondary:hover {{ border-color: var(--purple); }}
    #feedback-status {{ font-size: 0.8rem; color: var(--green); }}

    /* Token modal */
    .modal-overlay {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.7);
                       z-index: 100; align-items: center; justify-content: center; }}
    .modal-overlay.open {{ display: flex; }}
    .modal {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
               padding: 1.5rem; max-width: 480px; width: 90%; }}
    .modal h3 {{ color: var(--purple-mid); margin-bottom: 0.75rem; }}
    .modal input {{ width: 100%; background: var(--bg); border: 1px solid var(--border);
                    color: var(--text); border-radius: 6px; padding: 0.5rem;
                    font-size: 0.85rem; margin-bottom: 0.75rem; }}
    .modal p {{ font-size: 0.8rem; color: var(--text-muted); margin-bottom: 1rem; }}
    .modal-btns {{ display: flex; gap: 0.5rem; }}

    /* Missed papers */
    .missed-form {{ display: flex; flex-direction: column; gap: 0.5rem; margin-bottom: 1rem; }}
    .missed-form input {{ background: var(--bg); border: 1px solid var(--border);
                           color: var(--text); border-radius: 6px; padding: 0.5rem; font-size: 0.85rem; }}
    #missed-status {{ font-size: 0.8rem; color: var(--green); margin-top: 0.3rem; }}
    .missed-list {{ display: flex; flex-direction: column; gap: 0.4rem; margin-top: 0.75rem; }}
    .missed-item {{ background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
                    padding: 0.5rem 0.75rem; font-size: 0.82rem; }}
    .missed-item .diag {{ font-size: 0.7rem; border-radius: 4px; padding: 0.1rem 0.4rem;
                           margin-left: 0.5rem; }}
    .diag-low_ranking {{ background: #4c1d95; color: #ddd6fe; }}
    .diag-already_covered {{ background: #064e3b; color: #a7f3d0; }}
    .diag-source_not_tracked {{ background: #1e3a5f; color: #bfdbfe; }}
    .diag-excluded_term {{ background: #78350f; color: #fde68a; }}
    .diag-pending {{ background: #374151; color: #d1d5db; }}

    /* Archive */
    table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
    th {{ text-align: left; color: var(--text-muted); font-weight: 500;
          padding: 0.4rem 0.5rem; border-bottom: 1px solid var(--border); }}
    td {{ padding: 0.5rem 0.5rem; border-bottom: 1px solid var(--border); }}
    td a {{ color: var(--purple-mid); text-decoration: none; }}
    td a:hover {{ text-decoration: underline; }}
    tr:last-child td {{ border-bottom: none; }}

    .header-links {{ display: flex; gap: 0.6rem; justify-content: center; margin-top: 1rem; flex-wrap: wrap; }}
    .header-badge {{ display: inline-flex; align-items: center; gap: 0.4rem;
                     background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.2);
                     color: white; font-size: 0.78rem; text-decoration: none;
                     padding: 0.35rem 0.85rem; border-radius: 999px;
                     transition: background 0.15s; }}
    .header-badge:hover {{ background: rgba(255,255,255,0.22); }}

    .mascot {{ text-align: center; font-size: 2.5rem; margin: 1.5rem 0 0.5rem;
                animation: float 3s ease-in-out infinite; }}
    @keyframes float {{ 0%, 100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-6px); }} }}
    footer {{ text-align: center; padding: 2rem; color: var(--text-muted); font-size: 0.78rem; }}
  </style>
</head>
<body>

<header>
  <h1>🔭 {html.escape(PODCAST_TITLE)}</h1>
  <p>{html.escape(PODCAST_SUBTITLE)}</p>
  <div class="header-links">
    <a href="feed.xml" class="header-badge">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
        <path d="M6.18 15.64a2.18 2.18 0 0 1 2.18 2.18C8.36 19.01 7.38 20 6.18 20 4.98 20 4 19.01 4 17.82a2.18 2.18 0 0 1 2.18-2.18M4 4.44A15.56 15.56 0 0 1 19.56 20h-2.83A12.73 12.73 0 0 0 4 7.27V4.44m0 5.66a9.9 9.9 0 0 1 9.9 9.9h-2.83A7.07 7.07 0 0 0 4 12.93V10.1z"/>
      </svg>
      Subscribe via RSS
    </a>
    <a href="https://www.notion.so/{NOTION_DATABASE_ID}" target="_blank" class="header-badge">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
        <path d="M4.459 4.208c.746.606 1.026.56 2.428.466l13.215-.793c.28 0 .047-.28-.046-.326L17.86 1.968c-.42-.326-.981-.7-2.055-.607L3.01 2.295c-.466.046-.56.28-.374.466zm.793 3.08v13.904c0 .747.373 1.027 1.214.98l14.523-.84c.841-.046.935-.56.935-1.167V6.354c0-.606-.233-.933-.748-.887l-15.177.887c-.56.047-.747.327-.747.933zm14.337.745c.093.42 0 .84-.42.888l-.7.14v10.264c-.608.327-1.168.514-1.635.514-.748 0-.935-.234-1.495-.933l-4.577-7.186v6.952L12.21 19s0 .84-1.168.84l-3.222.186c-.093-.186 0-.653.327-.746l.84-.233V9.854L7.822 9.76c-.094-.42.14-1.026.793-1.073l3.456-.233 4.764 7.279v-6.44l-1.215-.139c-.093-.514.28-.887.747-.933zM1.936 1.035l13.31-.98c1.634-.14 2.055-.047 3.082.7l4.249 2.986c.7.513.934.653.934 1.213v16.378c0 1.026-.373 1.634-1.68 1.726l-15.458.934c-.98.047-1.448-.093-1.962-.747l-3.129-4.06c-.56-.747-.793-1.306-.793-1.96V2.667c0-.839.374-1.54 1.447-1.632z"/>
      </svg>
      Paper Notes on Notion
    </a>
  </div>
</header>

<!-- GitHub token modal -->
<div class="modal-overlay" id="token-modal">
  <div class="modal">
    <h3>GitHub Token Required</h3>
    <p>Enter your GitHub Personal Access Token (repo scope) to save feedback and notes back to the repo. It's stored only in your browser.</p>
    <input type="password" id="token-input" placeholder="ghp_...">
    <div class="modal-btns">
      <button class="btn" onclick="saveToken()">Save Token</button>
      <button class="btn secondary" onclick="closeModal()">Cancel</button>
    </div>
  </div>
</div>

<main>
  <div class="mascot">🧪</div>

  {"<!-- No episodes yet -->" if not latest else f'''
  <div class="card">
    <h2>Latest Episode — {html.escape(latest_date)}</h2>
    <audio id="player" controls preload="none">
      {"<source src='" + html.escape(latest_url) + "' type='audio/mpeg'>" if latest_url else ""}
      Your browser does not support audio.
    </audio>
    <div class="episode-meta">{latest.get("paper_count", 0)} papers · click a paper to jump to its segment</div>
  </div>

  <div class="section-title">This week&apos;s papers</div>
  <ul class="papers-list" id="paper-list">
    {paper_items}
  </ul>

  <div class="feedback-toolbar">
    <button class="btn" onclick="saveFeedback()">⭐ Save feedback to GitHub</button>
    <button class="btn secondary" onclick="openModal()">🔑 Set token</button>
    <span id="feedback-status"></span>
  </div>
  <p style="font-size:0.75rem;color:var(--text-muted);margin-top:0.5rem">
    Checking papers you found interesting improves next week&apos;s ranking.
    Notes are synced to Notion if configured.
  </p>
  '''}

  <!-- Missed papers -->
  <div class="card" style="margin-top:2rem">
    <h2>📬 Submit a missed paper</h2>
    <p style="font-size:0.82rem;color:var(--text-muted);margin-bottom:0.75rem">
      Did we miss something important this week? Submit it and we'll diagnose why,
      extract topic keywords, and boost similar papers in future episodes.
    </p>
    <div class="missed-form">
      <input type="text" id="missed-title" placeholder="Paper title (required)">
      <input type="text" id="missed-url" placeholder="URL or DOI (optional)">
      <button class="btn" onclick="submitMissedPaper()" style="align-self:flex-start">Submit</button>
      <span id="missed-status"></span>
    </div>
    <div class="missed-list" id="missed-list"></div>
  </div>

  {f'''
  <div class="card">
    <h2>Episode Archive</h2>
    <table>
      <thead><tr><th>Date</th><th>Papers</th><th>Audio</th></tr></thead>
      <tbody>{archive_rows}</tbody>
    </table>
  </div>
  ''' if len(episodes) > 1 else ""}

</main>

<footer>
  Generated by Science Radar · OpenRouter + Edge TTS · All free
</footer>

<script>
const REPO = "{GITHUB_REPO}";
const segments = {segments_js};
const player = document.getElementById("player");
const items = document.querySelectorAll(".paper-item");

// ── Audio seeking ──────────────────────────────────────────────────────────────
function seekTo(ts) {{
  if (!player) return;
  player.currentTime = Math.max(0, ts - 1.5);
  player.play();
}}

if (player) {{
  player.addEventListener("timeupdate", () => {{
    const t = player.currentTime;
    const paperSegs = segments.filter(s => s.type === "deep_dive" || s.type === "roundup");
    let activeIdx = -1;
    for (let i = paperSegs.length - 1; i >= 0; i--) {{
      if (t >= paperSegs[i].ts) {{ activeIdx = paperSegs[i].index; break; }}
    }}
    items.forEach(el => el.classList.toggle("active", parseInt(el.dataset.idx) === activeIdx));
  }});
}}

// ── Token management ───────────────────────────────────────────────────────────
function getToken() {{ return localStorage.getItem("gh_token") || ""; }}
function saveToken() {{
  const t = document.getElementById("token-input").value.trim();
  if (t) localStorage.setItem("gh_token", t);
  closeModal();
}}
function openModal() {{ document.getElementById("token-modal").classList.add("open"); }}
function closeModal() {{ document.getElementById("token-modal").classList.remove("open"); }}

// ── Feedback (likes) ───────────────────────────────────────────────────────────
function saveLikeLocally(cb) {{
  const key = "likes_" + cb.closest(".paper-item").dataset.date;
  const stored = JSON.parse(localStorage.getItem(key) || "[]");
  const url = cb.closest(".paper-item").dataset.url;
  if (cb.checked) {{
    if (!stored.find(e => e.url === url)) stored.push({{
      url, title: cb.closest(".paper-item").dataset.title,
      source: cb.closest(".paper-item").dataset.journal
    }});
  }} else {{
    const i = stored.findIndex(e => e.url === url);
    if (i > -1) stored.splice(i, 1);
  }}
  localStorage.setItem(key, JSON.stringify(stored));
}}

async function saveFeedback() {{
  const token = getToken();
  if (!token) {{ openModal(); return; }}
  const status = document.getElementById("feedback-status");
  status.textContent = "Saving...";
  status.style.color = "var(--text-muted)";

  // Collect all liked items from localStorage
  const byDate = {{}};
  for (let i = 0; i < localStorage.length; i++) {{
    const k = localStorage.key(i);
    if (k.startsWith("likes_")) {{
      const date = k.replace("likes_", "");
      byDate[date] = JSON.parse(localStorage.getItem(k) || "[]");
    }}
  }}

  try {{
    // Fetch current feedback.json
    const apiUrl = `https://api.github.com/repos/${{REPO}}/contents/state/feedback.json`;
    const getResp = await fetch(apiUrl, {{ headers: {{ Authorization: `token ${{token}}` }} }});
    let existing = {{}};
    let sha = "";
    if (getResp.ok) {{
      const data = await getResp.json();
      sha = data.sha;
      existing = JSON.parse(atob(data.content.replace(/\\n/g, "")));
    }}

    // Merge
    for (const [date, entries] of Object.entries(byDate)) {{
      if (!existing[date]) existing[date] = [];
      const existingUrls = new Set(existing[date].map(e => (typeof e === "string" ? e : e.url)));
      for (const entry of entries) {{
        if (!existingUrls.has(entry.url)) existing[date].push(entry);
      }}
    }}

    const body = {{ message: "Update feedback", content: btoa(JSON.stringify(existing, null, 2)) }};
    if (sha) body.sha = sha;
    const putResp = await fetch(apiUrl, {{
      method: "PUT",
      headers: {{ Authorization: `token ${{token}}`, "Content-Type": "application/json" }},
      body: JSON.stringify(body),
    }});
    if (putResp.ok) {{
      status.textContent = "✓ Saved! Ranking improves from next week.";
      status.style.color = "var(--green)";
    }} else {{
      throw new Error(await putResp.text());
    }}
  }} catch(e) {{
    status.textContent = "✗ Error: " + e.message;
    status.style.color = "var(--red)";
  }}
}}

// ── Notes ──────────────────────────────────────────────────────────────────────
function toggleNote(btn) {{
  const area = btn.closest(".paper-item").querySelector(".note-area");
  const open = area.style.display !== "none";
  area.style.display = open ? "none" : "block";
  btn.style.opacity = open ? "0.5" : "1";
}}

async function saveNote(btn) {{
  const token = getToken();
  if (!token) {{ openModal(); return; }}
  const item = btn.closest(".paper-item");
  const url = item.dataset.url;
  const title = item.dataset.title;
  const date = item.dataset.date;
  const note = item.querySelector(".note-input").value.trim();
  const status = item.querySelector(".note-status");
  if (!note) {{ status.textContent = "Note is empty."; return; }}

  status.textContent = "Saving...";
  try {{
    const apiUrl = `https://api.github.com/repos/${{REPO}}/contents/state/paper_notes.json`;
    const getResp = await fetch(apiUrl, {{ headers: {{ Authorization: `token ${{token}}` }} }});
    let existing = {{}};
    let sha = "";
    if (getResp.ok) {{
      const data = await getResp.json();
      sha = data.sha;
      existing = JSON.parse(atob(data.content.replace(/\\n/g, "")));
    }}
    if (!existing[date]) existing[date] = {{}};
    existing[date][url || title] = {{ note, title, source: item.dataset.journal }};

    const body = {{ message: `Note: ${{title.slice(0, 60)}}`, content: btoa(JSON.stringify(existing, null, 2)) }};
    if (sha) body.sha = sha;
    const putResp = await fetch(apiUrl, {{
      method: "PUT",
      headers: {{ Authorization: `token ${{token}}`, "Content-Type": "application/json" }},
      body: JSON.stringify(body),
    }});
    if (putResp.ok) {{
      status.textContent = "✓ Saved to GitHub (Notion sync in ~1 min)";
    }} else {{
      throw new Error(await putResp.text());
    }}
  }} catch(e) {{
    status.textContent = "✗ " + e.message;
  }}
}}

// ── Missed papers ──────────────────────────────────────────────────────────────
const MISSED_API = `https://api.github.com/repos/${{REPO}}/contents/state/missed_papers.json`;

async function loadMissedPapers() {{
  try {{
    const token = getToken();
    const headers = token ? {{ Authorization: `token ${{token}}` }} : {{}};
    const resp = await fetch(MISSED_API, {{ headers }});
    if (!resp.ok) return;
    const data = await resp.json();
    const papers = JSON.parse(atob(data.content.replace(/\\n/g, "")));
    renderMissedList(papers.slice().reverse());
  }} catch(e) {{ /* silent */ }}
}}

function renderMissedList(papers) {{
  const el = document.getElementById("missed-list");
  if (!papers.length) {{ el.innerHTML = ""; return; }}
  el.innerHTML = papers.slice(0, 5).map(p => {{
    const diag = p.diagnosis || "pending";
    const kws = (p.keywords_added || []).join(", ");
    return `<div class="missed-item">
      <strong>${{p.title.slice(0, 80)}}</strong>
      <span class="diag diag-${{diag}}">${{diag.replace("_", " ")}}</span>
      ${{kws ? `<br><span style="font-size:0.7rem;color:var(--text-muted)">Keywords: ${{kws}}</span>` : ""}}
    </div>`;
  }}).join("");
}}

async function submitMissedPaper() {{
  const token = getToken();
  if (!token) {{ openModal(); return; }}
  const title = document.getElementById("missed-title").value.trim();
  const url = document.getElementById("missed-url").value.trim();
  const status = document.getElementById("missed-status");
  if (!title) {{ status.textContent = "Title is required."; status.style.color = "var(--red)"; return; }}

  status.textContent = "Submitting..."; status.style.color = "var(--text-muted)";
  try {{
    const getResp = await fetch(MISSED_API, {{ headers: {{ Authorization: `token ${{token}}` }} }});
    let existing = []; let sha = "";
    if (getResp.ok) {{
      const data = await getResp.json();
      sha = data.sha;
      existing = JSON.parse(atob(data.content.replace(/\\n/g, "")));
    }}
    if (existing.some(e => e.title.toLowerCase() === title.toLowerCase())) {{
      status.textContent = "Already submitted — thanks!"; status.style.color = "var(--green)"; return;
    }}
    existing.push({{ id: Date.now().toString(), title, url: url || null,
      date_submitted: new Date().toISOString().slice(0, 10),
      processed: false, diagnosis: null, keywords_added: [] }});

    const body = {{ message: `Missed paper: ${{title.slice(0, 60)}}`,
      content: btoa(JSON.stringify(existing, null, 2)) }};
    if (sha) body.sha = sha;
    const putResp = await fetch(MISSED_API, {{
      method: "PUT",
      headers: {{ Authorization: `token ${{token}}`, "Content-Type": "application/json" }},
      body: JSON.stringify(body),
    }});
    if (putResp.ok) {{
      status.textContent = "✓ Submitted! Processing in ~2 min."; status.style.color = "var(--green)";
      document.getElementById("missed-title").value = "";
      document.getElementById("missed-url").value = "";
      setTimeout(loadMissedPapers, 120000);
    }} else {{
      throw new Error(await putResp.text());
    }}
  }} catch(e) {{
    status.textContent = "✗ " + e.message; status.style.color = "var(--red)";
  }}
}}

// ── Init ───────────────────────────────────────────────────────────────────────
loadMissedPapers();
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
    (SITE_DIR / "index.html").write_text(build_index_html(episodes), encoding="utf-8")
    (SITE_DIR / "feed.xml").write_text(build_rss_feed(episodes), encoding="utf-8")
    print(f"Site built: {SITE_DIR}/index.html ({len(episodes)} episodes)")


if __name__ == "__main__":
    main()
