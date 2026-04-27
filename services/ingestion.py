"""
services/ingestion.py – Article ingestion pipeline.

Architecture:
  1. Iterate over all configured sources
  2. For each source, call the appropriate parser (RSS or scrape)
  3. Filter to articles published within the last 7 days
  4. Deduplicate against existing DB entries
  5. Run fast keyword-based pre-scoring
  6. Persist new articles
  7. Optionally enrich with AI analysis (async-safe, skipped if OpenAI unavailable)

Daily automation:
  - APScheduler fires run_full_refresh() every day at 10:00 CET/CEST
    (configured in app.py / _start_scheduler)
  - For cron-based external triggering, expose the same function via the
    /refresh POST route or call it from CLI:
        flask shell -c "from services.ingestion import run_full_refresh; run_full_refresh()"
"""

from __future__ import annotations
import hashlib
import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from dateutil import parser as dateparser
import pytz

from sources_config import SOURCES
from services.source_parsers import get_parser, fetch_article_content

logger = logging.getLogger(__name__)

DATABASE_PATH = os.environ.get("DATABASE_PATH", "newsroom.db")
INGEST_WINDOW_DAYS = 7          # Only keep articles from the last N days
MAX_CONTENT_LENGTH = 6000       # Characters of raw content to store
FETCH_FULL_CONTENT = False      # Set True to fetch full article text on ingest
                                # (slower, more bandwidth – turn on once stable)


# ──────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────

def run_full_refresh(triggered_by: str = "manual") -> dict:
    """
    Run ingestion across all configured sources.
    Returns a summary dict: {added, skipped, errors}.
    """
    db = _get_db()
    started_at = datetime.utcnow().isoformat()
    log_id = _log_start(db, triggered_by, started_at)

    total_added = 0
    total_skipped = 0
    errors = []

    for source in SOURCES:
        try:
            added, skipped = _ingest_source(db, source)
            total_added += added
            total_skipped += skipped
            logger.info(f"[{source['name']}] added={added} skipped={skipped}")
        except Exception as e:
            logger.error(f"[{source['name']}] ingestion error: {e}", exc_info=True)
            errors.append(f"{source['name']}: {e}")

    finished_at = datetime.utcnow().isoformat()
    _log_finish(db, log_id, finished_at, total_added, total_skipped,
                "; ".join(errors) if errors else None)
    db.close()

    return {"added": total_added, "skipped": total_skipped, "errors": errors}


# ──────────────────────────────────────────────────────────────
# Per-source ingestion
# ──────────────────────────────────────────────────────────────

def _ingest_source(db: sqlite3.Connection, source: dict) -> tuple[int, int]:
    parser_fn = get_parser(source)
    raw_articles = parser_fn(source.get("scrape_url", ""), source)

    if not raw_articles:
        logger.debug(f"[{source['name']}] no articles returned from parser")
        return 0, 0

    cutoff = datetime.utcnow() - timedelta(days=INGEST_WINDOW_DAYS)
    added = 0
    skipped = 0

    for art in raw_articles:
        # Date check
        pub_dt = _parse_datetime(art.get("published_at"))
        if pub_dt and pub_dt < cutoff.replace(tzinfo=timezone.utc):
            skipped += 1
            continue

        # Build dedupe key (URL-based first, headline hash fallback)
        url = art.get("article_url", "").strip()
        headline = art.get("headline", "").strip()
        if not url and not headline:
            skipped += 1
            continue

        dedupe_key = _make_dedupe_key(url, headline)

        # Check duplicate
        existing = db.execute(
            "SELECT id FROM articles WHERE dedupe_key=?", [dedupe_key]
        ).fetchone()
        if existing:
            skipped += 1
            continue

        # Optionally fetch full content
        raw_content = art.get("raw_content", "")
        if FETCH_FULL_CONTENT and url and not raw_content:
            raw_content = fetch_article_content(url)

        # Quick keyword pre-score (real AI scoring can be done on-demand)
        from services.scoring import quick_keyword_score
        pre_score_data = quick_keyword_score(headline, art.get("subheadline") or "", raw_content)

        db.execute("""
            INSERT INTO articles
                (source_name, source_tier, source_url, article_url,
                 headline, subheadline, author, published_at, fetched_at,
                 raw_content, summary_short,
                 tern_relevance_score, topic_cluster, post_chance,
                 content_status, dedupe_key)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, [
            source["name"],
            source["tier"],
            source["home_url"],
            url,
            headline,
            art.get("subheadline"),
            art.get("author"),
            art.get("published_at"),
            datetime.utcnow().isoformat(),
            raw_content[:MAX_CONTENT_LENGTH] if raw_content else None,
            art.get("subheadline"),  # Use subheadline as initial short summary
            pre_score_data["score"],
            pre_score_data["cluster"],
            pre_score_data["post_chance"],
            "new",
            dedupe_key,
        ])
        added += 1

    db.commit()
    return added, skipped


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _make_dedupe_key(url: str, headline: str) -> str:
    """Prefer URL; fall back to normalised headline hash."""
    if url:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
    normalised = headline.lower().strip()
    return "h:" + hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:31]


def _parse_datetime(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if not value.tzinfo else value
    try:
        dt = dateparser.parse(str(value), fuzzy=True)
        if dt:
            if not dt.tzinfo:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
    except Exception:
        pass
    return None


def _get_db() -> sqlite3.Connection:
    db = sqlite3.connect(
        DATABASE_PATH,
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
    )
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def _log_start(db, triggered_by: str, started_at: str) -> int:
    cur = db.execute(
        "INSERT INTO refresh_log (triggered_by, started_at) VALUES (?,?)",
        [triggered_by, started_at]
    )
    db.commit()
    return cur.lastrowid


def _log_finish(db, log_id: int, finished_at: str,
                added: int, skipped: int, error_msg: Optional[str]):
    db.execute("""
        UPDATE refresh_log
        SET finished_at=?, articles_added=?, articles_skipped=?, error_message=?
        WHERE id=?
    """, [finished_at, added, skipped, error_msg, log_id])
    db.commit()
