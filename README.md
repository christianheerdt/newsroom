# TERN LinkedIn Newsroom

An internal LinkedIn content intelligence and post generation system for TERN Healthcare Recruiting.

---

## What This Is

A Flask-based editorial tool that:
- Monitors 10 configured German healthcare/nursing news sources (RSS + scraping)
- Scores every article for TERN relevance (0–100) using keyword analysis + GPT-4o
- Classifies articles into topic clusters and suggests TERN-specific commentary angles
- Generates structured LinkedIn post packages (post + first comment + hashtags + media recommendation)
- Supports both news-based and free-form post creation
- Persists everything in SQLite
- Runs a daily auto-refresh at 10:00 CET/CEST via APScheduler

---

## Quickstart

### 1. Install dependencies

```bash
cd tern-newsroom
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and set your OPENAI_API_KEY
```

### 3. Run

```bash
python app.py
```

Open: http://localhost:5050

Default login: `admin` / `tern2024` (change in `.env`)

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `FLASK_SECRET_KEY` | `dev-insecure-key` | Session secret – **change in production** |
| `APP_USERNAME` | `admin` | Login username |
| `APP_PASSWORD` | `tern2024` | Login password |
| `OPENAI_API_KEY` | – | Required for AI analysis and post generation |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI model to use |
| `DATABASE_PATH` | `newsroom.db` | SQLite database path |
| `ENABLE_SCHEDULER` | `true` | Enable built-in APScheduler for daily refresh |
| `DAILY_REFRESH_HOUR` | `10` | Refresh hour (24h, CET/CEST) |
| `DAILY_REFRESH_MINUTE` | `0` | Refresh minute |

---

## Architecture

```
tern-newsroom/
├── app.py                  # Flask app, routes, auth
├── database.py             # SQLite schema init and connection helper
├── sources_config.py       # All 10 sources with tiering and RSS feeds
├── services/
│   ├── ingestion.py        # Ingestion pipeline and deduplication
│   ├── source_parsers.py   # Per-source RSS/scrape parsers
│   ├── scoring.py          # Keyword scoring + GPT-4o deep analysis
│   └── generators.py       # LinkedIn post generation (news + free)
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── dashboard.html
│   ├── article_detail.html
│   ├── free_generator.html
│   ├── output_detail.html
│   └── outputs_list.html
├── static/
│   └── styles.css
├── .env.example
├── requirements.txt
└── README.md
```

---

## Daily Refresh

### Built-in scheduler (default)

When `ENABLE_SCHEDULER=true`, APScheduler runs `run_full_refresh()` daily at the configured time in the `Europe/Berlin` timezone. This starts automatically with the Flask app.

**Important:** This requires the Flask process to remain running. In production, use a process manager like `gunicorn` + `supervisor` or `systemd`.

### External cron (alternative)

If you prefer external scheduling, set `ENABLE_SCHEDULER=false` and add a cron job:

```cron
0 10 * * * cd /path/to/tern-newsroom && /path/to/venv/bin/python -c "from services.ingestion import run_full_refresh; run_full_refresh(triggered_by='cron')"
```

Or trigger via the HTTP API (requires a valid session cookie):
```
POST /refresh
```

### Manual refresh

Click the **↻ Jetzt aktualisieren** button in the dashboard, or **↻ Aktualisieren** in the navbar.

---

## Source Tiering

| Tier | Sources | Score boost |
|---|---|---|
| 1 | Care vor 9, kma Online, Bibliomed Pflege, Springer Pflege, Altenheim.net, altenpflege-online.net | +15 pts |
| 2 | AOK News Pflege, Haufe Pflege, Deutsches Pflegeportal | +8 pts |
| 3 | pflege.de | +0 pts |

---

## AI Features

**Requires an OpenAI API key.**

Two AI-powered features:

1. **Article deep analysis** (`/article/<id>/analyse`) – Triggered on-demand from the article detail page. Produces summaries, TERN relevance reasoning, topic cluster, TERN angle, and recommended post types via GPT-4o.

2. **Post generation** – All post generation (news-based and free) uses GPT-4o to produce a full posting package: main text, rationale, first comment, hashtag suggestions, and media recommendation.

**Without an API key:** Ingestion still works (keyword-based pre-scoring). Post generation and deep analysis will return an error message.

---

## Adding a New Source

1. Add an entry to `SOURCES` in `sources_config.py`
2. Provide RSS feed URLs where available (preferred)
3. If the source needs special parsing, write a function in `services/source_parsers.py` and register it in `PARSER_REGISTRY`
4. Restart the app

---

## Production Notes

- Use `gunicorn app:app` instead of the built-in Flask server
- Store `newsroom.db` on a persistent volume
- Set a strong `FLASK_SECRET_KEY` in `.env`
- Change the default `APP_PASSWORD`
- Consider adding HTTPS via a reverse proxy (nginx, Caddy)
- The SQLite WAL mode is already enabled for concurrent reads

---

## Known Limitations

- Article full-text extraction is heuristic (`fetch_article_content`). Not all sites can be fully parsed. RSS content is used where available.
- Some sources may block scraping. RSS is always preferred.
- AOK's RSS feed is broad – content is filtered by URL/title keyword matching for Pflege.
- The scheduler requires the Flask process to stay alive. For high-availability deployments, use an external cron.
