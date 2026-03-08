# 🔭 Science Radar Podcast

An automated weekly podcast that scans the world's top scientific journals, identifies the most surprising and groundbreaking papers, and generates a ~1 hour audio episode — entirely using free tools and APIs.

---

## What It Does

Every Tuesday at 01:00 UTC, the pipeline automatically:

1. **Fetches papers** from Nature, Science, Cell, NEJM, The Lancet, and the full Nature/Science journal families published in the past 7 days
2. **Analyzes each paper** through 3 special lenses using an LLM:
   - **Contradicts consensus** — challenges established scientific belief
   - **New frontier** — opens a genuinely new research direction
   - **Cross-disciplinary** — bridges two distant fields unexpectedly
3. **Ranks and selects** the top ~35 most interesting papers
4. **Generates a podcast script** with deep-dive segments for high-scoring papers and quick roundups for the rest
5. **Adds a synthesis segment** — the LLM finds hidden connections *across* papers from different fields
6. **Converts to audio** using Microsoft Edge TTS (free, no key needed)
7. **Publishes** the MP3 as a GitHub Release and updates the GitHub Pages website

---

## Everything Is Free

| Component | Tool | Cost |
|---|---|---|
| Paper metadata | OpenAlex API | Free, no key needed |
| Preprints | arXiv API | Free, no key needed |
| RSS feeds | Nature, Science, Quanta Magazine, Science News | Free |
| Full text extraction | PyMuPDF + newspaper4k | Free Python libraries |
| LLM — analysis + script | Gemini 2.0 Flash via OpenRouter | Free tier |
| Text-to-speech | Microsoft Edge TTS | Free, no key needed |
| TTS fallback | Google TTS (gTTS) | Free |
| Audio processing | ffmpeg | Free, open source |
| Hosting (site) | GitHub Pages | Free |
| Hosting (MP3s) | GitHub Releases | Free |
| Automation | GitHub Actions | Free (2000 min/month) |

---

## Journals Tracked

Only journals with Impact Factor > 17, or undisputed field leaders:

| Journal | Impact Factor |
|---|---|
| Nature | ~69 |
| Science | ~67 |
| Cell | ~66 |
| New England Journal of Medicine | ~176 |
| The Lancet | ~168 |
| Nature Medicine | ~87 |
| Nature Biotechnology | ~68 |
| Nature Materials | ~41 |
| Nature Climate Change | ~29 |
| Nature Human Behaviour | ~29 |
| Nature Physics | ~27 |
| Science Robotics | ~26 |
| Nature Neuroscience | ~25 |
| Nature Chemistry | ~24 |
| Science Immunology | ~24 |
| Nature Ecology & Evolution | ~20 |
| Science Translational Medicine | ~19 |
| Nature Astronomy | ~19 |
| Physical Review Letters | ~9 (field leader, physics) |
| Astrophysical Journal Letters | ~7 (field leader, astrophysics) |

Plus arXiv preprints across: `q-bio`, `physics`, `cond-mat`, `astro-ph`, `cs.AI`, `cs.LG`, `math-ph`, `quant-ph`, `nlin`.

---

## Project Structure

```
science-radar-podcast/
├── run_weekly.py                  # Main pipeline entry point
├── config.yaml                    # All settings: journals, models, podcast config
├── requirements.txt
├── .env.example                   # Environment variables template
│
├── src/
│   ├── collectors/
│   │   ├── openalex.py            # Fetch from high-impact journals via OpenAlex API
│   │   ├── arxiv.py               # Fetch preprints from arXiv API
│   │   └── rss.py                 # Fetch from journal RSS feeds
│   │
│   ├── processing/
│   │   ├── extractor.py           # Extract full text from PDFs and web pages
│   │   ├── analyzer.py            # LLM analysis: score each paper on 3 lenses
│   │   ├── ranker.py              # Score, rank, select top papers with diversity
│   │   └── script_generator.py   # Generate podcast script + synthesis segment
│   │
│   ├── outputs/
│   │   ├── tts.py                 # Text-to-speech (Edge TTS → gTTS fallback)
│   │   └── audio.py               # Concatenate MP3s with transition SFX via ffmpeg
│   │
│   └── utils/
│       └── dedup.py               # Track seen papers across weeks (no repeats)
│
├── tools/
│   └── build_site.py              # Build GitHub Pages site (purple theme)
│
├── docs/                          # GitHub Pages site (auto-generated, do not edit)
│   ├── index.html
│   └── feed.xml                   # RSS podcast feed for podcast apps
│
├── state/                         # Persistent state (committed to git)
│   └── seen_ids.json              # Paper IDs already covered (prevents repeats)
│
├── data/
│   └── analysis_cache/            # Cached LLM analyses keyed by paper URL hash
│
├── output/
│   └── YYYY-MM-DD/
│       ├── podcast_YYYY-MM-DD.mp3 # Final episode audio
│       ├── script.txt             # Human-readable full script
│       ├── script.json            # Script segments as JSON
│       ├── selected.json          # Papers selected with LLM scores
│       ├── candidates.json        # All papers fetched before ranking
│       ├── episode.json           # Episode index with timestamps for seeking
│       └── segments/              # Individual MP3 per segment (before merge)
│
└── .github/
    └── workflows/
        └── weekly_podcast.yml     # GitHub Actions: runs every Tuesday 01:00 UTC
```

---

## Episode Structure (~1 hour)

```
[Intro]
  ↓
[Section 1] Challenging What We Know
  → Deep-dive segments (~300 words each) on papers that contradict established consensus
  ↓
[Section 2] New Frontiers
  → Deep-dive segments on papers opening genuinely new research directions
  ↓
[Section 3] Bridging Worlds
  → Deep-dive segments on cross-disciplinary papers
  ↓
[Section 4] This Week's Highlights
  → Quick roundups (~100 words each) of remaining selected papers
  ↓
[The Big Picture] — Synthesis segment (~500 words)
  → LLM finds unexpected connections across ALL papers this week
  → Suggests bold hypotheses emerging from cross-field patterns
  ↓
[Outro]
```

---

## Setup (One-Time)

### Prerequisites
- A GitHub account
- Python 3.11+ (for local testing only)
- `ffmpeg` installed (`sudo apt install ffmpeg` on Ubuntu)

### Step 1: Fork or clone this repo
```bash
git clone https://github.com/WenyueDai/science-radar-podcast.git
cd science-radar-podcast
```

### Step 2: Get a free OpenRouter API key
1. Sign up at [openrouter.ai](https://openrouter.ai) — no credit card needed
2. Go to **Keys** → **Create Key** → copy it
3. Keep it safe — never commit it to git

### Step 3: Create a GitHub Personal Access Token
1. Go to [github.com/settings/tokens](https://github.com/settings/tokens)
2. **Generate new token (classic)**
3. Scopes: check **repo** and **workflow**
4. Copy the token (`ghp_...`)

### Step 4: Add secrets to your GitHub repo
Go to your repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:

| Secret name | Value |
|---|---|
| `OPENROUTER_API_KEY` | Your OpenRouter key (`sk-or-v1-...`) |
| `GH_PAT` | Your GitHub token (`ghp_...`) |

### Step 5: Set GitHub Actions permissions
Repo → **Settings** → **Actions** → **General** → **Workflow permissions** → **Read and write permissions** → Save

### Step 6: Enable GitHub Pages
Repo → **Settings** → **Pages** → Source: **Deploy from a branch** → Branch: `main` / folder: `/docs` → Save

### Step 7: Run it
Repo → **Actions** → **Weekly Science Radar Podcast** → **Run workflow**

First run takes ~15–25 minutes. After that it runs automatically every Tuesday at 01:00 UTC.

---

## Local Testing

```bash
# Install dependencies
pip install -r requirements.txt
sudo apt install ffmpeg

# Set your API key
export OPENROUTER_API_KEY=sk-or-v1-...

# Run the pipeline
python run_weekly.py

# Build the site locally
python tools/build_site.py
```

**Useful environment variables:**

| Variable | Default | Description |
|---|---|---|
| `RUN_DATE` | today | Override episode date (`YYYY-MM-DD`) |
| `FORCE_REGEN` | `false` | Re-run even if episode already exists |
| `REGEN_SCRIPT` | `false` | Regenerate script reusing cached LLM analyses |
| `PODCAST_ATEMPO` | `1.0` | Audio playback speed via ffmpeg (1.2 = 20% faster) |

---

## Configuration

All settings live in `config.yaml`:

| Setting | Description |
|---|---|
| `target_journals` | Journals to track via OpenAlex |
| `arxiv_categories` | arXiv subject areas to scan |
| `rss_sources` | Direct RSS feeds |
| `limits.max_papers_total` | Papers per episode (default: 35) |
| `limits.max_papers_per_journal` | Diversity cap per journal (default: 4) |
| `llm.script_model` | Model for script generation |
| `llm.analysis_model` | Model for paper analysis |
| `podcast.voice` | Edge TTS voice (default: `en-GB-RyanNeural`) |
| `podcast.voice_rate` | Speaking rate (default: `+20%`) |
| `scoring.weights` | How much each lens contributes to ranking |

---

## Output Files

After each run, `output/YYYY-MM-DD/` contains:

| File | Description |
|---|---|
| `podcast_YYYY-MM-DD.mp3` | The full episode audio |
| `script.txt` | Complete script in plain text — readable without audio |
| `selected.json` | All selected papers with LLM scores and analysis |
| `candidates.json` | All fetched papers before ranking |
| `episode.json` | Timestamps per segment — used by website for audio seeking |

---

## The Website

The GitHub Pages site at `https://WenyueDai.github.io/science-radar-podcast`:

- Audio player for the latest episode
- Click any paper title to **jump directly to that segment** in the audio
- Episode archive with download links to all past MP3s
- `feed.xml` — subscribe in any podcast app (Apple Podcasts, Pocket Casts, etc.)

---

## LLM Models

Accessed via [OpenRouter](https://openrouter.ai) free tier — no Google API key needed:

| Model | Used for |
|---|---|
| `google/gemini-2.0-flash-exp:free` | Paper analysis (3-lens scoring) |
| `google/gemini-2.0-flash-exp:free` | Podcast script generation |
| `google/gemini-2.0-flash-exp:free` | Cross-paper synthesis segment |

To switch models, edit `config.yaml`. Browse all free models at [openrouter.ai/models?q=free](https://openrouter.ai/models?q=free).

---

## Inspiration

Built on patterns from [openclaw-knowledge-radio](https://github.com/WenyueDai/protein_design_podcast) — a daily protein design podcast using the same free-tier stack.
