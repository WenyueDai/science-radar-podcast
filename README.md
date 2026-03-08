# 🔭 Science Radar Podcast

An automated weekly podcast that scans the world's top scientific journals, identifies the most surprising and groundbreaking papers, and generates a ~1 hour audio episode — entirely using free tools and APIs.

---

## What It Does

Every Tuesday at 01:00 UTC, the pipeline automatically:

1. **Fetches papers** from Nature, Science, Cell, PNAS, eLife, arXiv, and 20+ other high-impact journals published in the past 7 days
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
| Paper metadata | OpenAlex API | Free, no key |
| Preprints | arXiv API | Free, no key |
| RSS feeds | Nature, Science, etc. | Free |
| Full text extraction | PyMuPDF + newspaper4k | Free libraries |
| LLM (analysis + script) | Gemini 2.0 Flash via OpenRouter | Free tier |
| Text-to-speech | Microsoft Edge TTS | Free, no key |
| Audio processing | ffmpeg | Free |
| Hosting (site + MP3) | GitHub Pages + GitHub Releases | Free |
| Automation | GitHub Actions | Free (2000 min/month) |

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
│   │   ├── openalex.py            # Fetch from high-impact journals via OpenAlex
│   │   ├── arxiv.py               # Fetch preprints from arXiv
│   │   └── rss.py                 # Fetch from journal RSS feeds
│   │
│   ├── processing/
│   │   ├── extractor.py           # Extract full text from PDFs and web pages
│   │   ├── analyzer.py            # LLM analysis: score each paper on 3 lenses
│   │   ├── ranker.py              # Score, rank, select top papers
│   │   └── script_generator.py   # Generate podcast script + synthesis segment
│   │
│   ├── outputs/
│   │   ├── tts.py                 # Text-to-speech (Edge TTS → gTTS fallback)
│   │   └── audio.py               # Concatenate MP3s with transition SFX
│   │
│   └── utils/
│       └── dedup.py               # Track seen papers across weeks
│
├── tools/
│   └── build_site.py              # Build GitHub Pages site (purple theme)
│
├── docs/                          # GitHub Pages site (auto-generated)
│   ├── index.html
│   └── feed.xml                   # RSS podcast feed
│
├── state/                         # Persistent state (committed to git)
│   └── seen_ids.json              # Papers already covered (prevents repeats)
│
├── data/
│   └── analysis_cache/            # Cached LLM analyses (by paper URL hash)
│
├── output/
│   └── YYYY-MM-DD/
│       ├── podcast_YYYY-MM-DD.mp3
│       ├── script.txt             # Human-readable full script
│       ├── script.json
│       ├── selected.json          # Papers selected with scores
│       ├── candidates.json        # All papers fetched before ranking
│       ├── episode.json           # Episode index with timestamps
│       └── segments/              # Individual MP3 per segment
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
  → Deep-dive segments on papers that contradict established consensus
  ↓
[Section 2] New Frontiers
  → Deep-dive segments on papers opening new research directions
  ↓
[Section 3] Bridging Worlds
  → Deep-dive segments on cross-disciplinary papers
  ↓
[Section 4] This Week's Highlights
  → Quick roundups of remaining selected papers
  ↓
[The Big Picture] — Synthesis segment
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
1. Sign up at [openrouter.ai](https://openrouter.ai) (no credit card needed)
2. Go to **Keys** → **Create Key**
3. Copy the key — keep it safe, never commit it

### Step 3: Create a GitHub Personal Access Token
1. Go to [github.com/settings/tokens](https://github.com/settings/tokens)
2. Generate new token (classic)
3. Scopes: check **repo** and **workflow**
4. Copy the token

### Step 4: Add secrets to your GitHub repo
Go to your repo → **Settings** → **Secrets and variables** → **Actions**:

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
| `REGEN_SCRIPT` | `false` | Regenerate script using cached LLM analyses |
| `PODCAST_ATEMPO` | `1.0` | Audio playback speed (1.2 = 20% faster) |

---

## Configuration

All settings are in `config.yaml`:

- **`target_journals`** — list of journals to track via OpenAlex
- **`arxiv_categories`** — arXiv subject areas to scan
- **`rss_sources`** — direct RSS feeds
- **`limits.max_papers_total`** — how many papers per episode (default: 35)
- **`limits.max_papers_per_journal`** — diversity cap per journal (default: 4)
- **`llm.script_model`** — LLM model for script generation
- **`llm.analysis_model`** — LLM model for paper analysis
- **`podcast.voice`** — Edge TTS voice (default: `en-GB-RyanNeural`)
- **`podcast.voice_rate`** — speaking rate (default: `+20%`)

---

## Output Files

After each run, `output/YYYY-MM-DD/` contains:

- **`podcast_YYYY-MM-DD.mp3`** — the full episode audio
- **`script.txt`** — the complete script in plain text (great for reading)
- **`selected.json`** — all selected papers with their LLM scores
- **`episode.json`** — timestamps for each segment (used by the website for seeking)

---

## The Website

The GitHub Pages site at `https://WenyueDai.github.io/science-radar-podcast` features:

- Audio player for the latest episode
- Click any paper in the list to **jump directly to that segment** in the audio
- Episode archive with links to all past MP3s
- RSS feed (`feed.xml`) — subscribe in any podcast app

---

## LLM Models Used

Both models are accessed via [OpenRouter](https://openrouter.ai) free tier:

- **`google/gemini-2.0-flash-exp:free`** — paper analysis and script generation
- No Google API key needed — OpenRouter handles it

To switch models, edit `config.yaml`:
```yaml
llm:
  script_model: "google/gemini-2.0-flash-exp:free"
  analysis_model: "google/gemini-2.0-flash-exp:free"
```
Browse free models at [openrouter.ai/models?q=free](https://openrouter.ai/models?q=free).

---

## Inspiration

Built on patterns from [openclaw-knowledge-radio](https://github.com/WenyueDai/protein_design_podcast) — a daily protein design podcast using the same free-tier stack.
