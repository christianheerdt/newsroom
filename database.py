"""
database.py – SQLite schema initialisation and connection helper
"""

import sqlite3
import os
from flask import g

DATABASE_PATH = os.environ.get("DATABASE_PATH", "newsroom.db")


def get_db():
    """Return the per-request DB connection, creating it if needed."""
    if "db" not in g:
        g.db = sqlite3.connect(
            DATABASE_PATH,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app):
    """Create all tables if they don't exist yet."""
    with app.app_context():
        db = sqlite3.connect(DATABASE_PATH)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")

        db.executescript("""
        -- ─────────────────────────────────────────
        --  ARTICLES
        -- ─────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS articles (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name             TEXT NOT NULL,
            source_tier             INTEGER NOT NULL DEFAULT 2,
            source_url              TEXT NOT NULL,
            article_url             TEXT NOT NULL,
            headline                TEXT NOT NULL,
            subheadline             TEXT,
            author                  TEXT,
            published_at            TEXT,
            fetched_at              TEXT NOT NULL,
            raw_content             TEXT,
            summary_short           TEXT,
            summary_long            TEXT,
            tern_relevance_score    INTEGER DEFAULT 0,
            tern_relevance_reasoning TEXT,
            topic_cluster           TEXT,
            tern_angle              TEXT,
            recommended_post_types  TEXT,   -- JSON array stored as text
            content_status          TEXT NOT NULL DEFAULT 'new',
                                            -- new | reviewed | ignored | used
            is_favorite             INTEGER NOT NULL DEFAULT 0,
            post_chance             TEXT,   -- high | medium | low
            dedupe_key              TEXT UNIQUE,
            created_at              TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at              TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_articles_published  ON articles(published_at DESC);
        CREATE INDEX IF NOT EXISTS idx_articles_score      ON articles(tern_relevance_score DESC);
        CREATE INDEX IF NOT EXISTS idx_articles_status     ON articles(content_status);
        CREATE INDEX IF NOT EXISTS idx_articles_cluster    ON articles(topic_cluster);
        CREATE INDEX IF NOT EXISTS idx_articles_source     ON articles(source_name);

        -- ─────────────────────────────────────────
        --  GENERATED OUTPUTS
        -- ─────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS outputs (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id          INTEGER REFERENCES articles(id) ON DELETE SET NULL,
            output_mode         TEXT NOT NULL,  -- news_based | free | hybrid
            output_type         TEXT NOT NULL,
            objective           TEXT,
            perspective         TEXT,
            tone                TEXT,
            wording_style       TEXT,
            length_setting      TEXT,
            structure_setting   TEXT,
            cta_setting         TEXT,
            title               TEXT,
            content             TEXT NOT NULL,
            rationale           TEXT,
            media_recommendation TEXT,
            first_comment       TEXT,
            hashtag_suggestion  TEXT,
            -- free-content extra fields
            target_audience     TEXT,
            reference_links     TEXT,
            user_notes          TEXT,
            created_at          TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_outputs_article  ON outputs(article_id);
        CREATE INDEX IF NOT EXISTS idx_outputs_created  ON outputs(created_at DESC);

        -- ─────────────────────────────────────────
        --  REFRESH LOG
        -- ─────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS refresh_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            triggered_by    TEXT NOT NULL,  -- scheduler | manual
            started_at      TEXT NOT NULL,
            finished_at     TEXT,
            articles_added  INTEGER DEFAULT 0,
            articles_skipped INTEGER DEFAULT 0,
            error_message   TEXT
        );
        """)

        db.commit()
        db.close()
