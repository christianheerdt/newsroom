"""
services/source_parsers.py – Per-source parsing logic.

Each parser receives a BeautifulSoup object (or raw HTML string) plus the
source config dict and must return a list of article dicts with at minimum:
    headline, article_url, published_at (ISO string or None), subheadline, author, raw_content

Generic parsers handle most RSS sources automatically.
Custom parsers are registered here for sources that need special treatment.
"""

from __future__ import annotations
import re
import logging
from datetime import datetime
from typing import Optional

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

logger = logging.getLogger(__name__)

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; TERN-Newsroom-Bot/1.0; "
        "+https://tern-healthcare.com)"
    )
}
REQUEST_TIMEOUT = 15


# ──────────────────────────────────────────────────────────────
# Generic RSS parser (used for most sources)
# ──────────────────────────────────────────────────────────────

def parse_rss_feed(feed_url: str, source_config: dict) -> list[dict]:
    """Parse a standard RSS/Atom feed and return normalised article dicts."""
    articles = []
    try:
        feed = feedparser.parse(feed_url)
        if feed.bozo and not feed.entries:
            logger.warning(f"RSS parse warning for {feed_url}: {feed.bozo_exception}")
            return []

        for entry in feed.entries:
            headline = _clean(entry.get("title", ""))
            if not headline:
                continue

            article_url = entry.get("link", "")
            published_at = _parse_date(
                entry.get("published") or entry.get("updated") or ""
            )
            subheadline = _clean(entry.get("summary", ""))[:300] or None
            author = entry.get("author", None)
            # Try to get full content if syndicated
            raw_content = ""
            if hasattr(entry, "content") and entry.content:
                raw_content = entry.content[0].get("value", "")
            elif entry.get("summary"):
                raw_content = entry.summary

            articles.append({
                "headline": headline,
                "article_url": article_url,
                "published_at": published_at,
                "subheadline": subheadline,
                "author": author,
                "raw_content": _strip_html(raw_content)[:4000],
            })
    except Exception as e:
        logger.error(f"RSS fetch failed for {feed_url}: {e}")

    return articles


# ──────────────────────────────────────────────────────────────
# Generic scrape-based parser (fallback when RSS unavailable/broken)
# ──────────────────────────────────────────────────────────────

def parse_generic_scrape(scrape_url: str, source_config: dict) -> list[dict]:
    """
    Best-effort scraper: finds <article> or news-card-like elements.
    Returns partial data; headline + URL is the minimum requirement.
    """
    articles = []
    try:
        resp = requests.get(scrape_url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # Remove nav/footer noise
        for tag in soup.find_all(["nav", "footer", "header", "aside", "script", "style"]):
            tag.decompose()

        candidates = (
            soup.find_all("article") or
            soup.find_all(class_=re.compile(r"article|post|news|card|teaser", re.I)) or
            soup.find_all("li", class_=re.compile(r"article|post|news|item", re.I))
        )

        for el in candidates[:30]:
            # Headline
            h = (
                el.find(["h1", "h2", "h3"]) or
                el.find(class_=re.compile(r"title|headline|heading", re.I))
            )
            if not h:
                continue
            headline = _clean(h.get_text())
            if not headline or len(headline) < 15:
                continue

            # URL
            link_el = el.find("a", href=True)
            href = link_el["href"] if link_el else ""
            article_url = _absolute_url(href, scrape_url)
            if not article_url:
                continue

            # Date (best effort)
            time_el = el.find("time")
            date_str = ""
            if time_el:
                date_str = time_el.get("datetime", "") or time_el.get_text()
            published_at = _parse_date(date_str)

            # Subheadline / teaser
            p = el.find("p")
            subheadline = _clean(p.get_text())[:300] if p else None

            articles.append({
                "headline": headline,
                "article_url": article_url,
                "published_at": published_at,
                "subheadline": subheadline,
                "author": None,
                "raw_content": "",
            })
    except Exception as e:
        logger.error(f"Scrape failed for {scrape_url}: {e}")

    return articles


# ──────────────────────────────────────────────────────────────
# Full-article content fetcher (used after initial ingestion)
# ──────────────────────────────────────────────────────────────

def fetch_article_content(url: str) -> str:
    """
    Attempt to fetch the body text of a single article page.
    Returns cleaned plain text (max 6000 chars) or empty string on failure.
    This is a heuristic approach – not guaranteed for all sites.
    """
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # Remove noise
        for tag in soup.find_all(["nav", "footer", "header", "aside",
                                   "script", "style", "noscript",
                                   "figure", "figcaption"]):
            tag.decompose()

        # Try article body first
        body = (
            soup.find("article") or
            soup.find(class_=re.compile(r"article.?body|post.?body|entry.?content|content.?body", re.I)) or
            soup.find("main")
        )
        if not body:
            body = soup.find("body")

        if body:
            text = body.get_text(separator=" ", strip=True)
            return re.sub(r"\s{2,}", " ", text)[:6000]
    except Exception as e:
        logger.debug(f"Could not fetch article content for {url}: {e}")
    return ""


# ──────────────────────────────────────────────────────────────
# Custom per-source parsers
# ──────────────────────────────────────────────────────────────
# Register under the same key as parser_key in sources_config.py

def parse_kma_online(scrape_url: str, source_config: dict) -> list[dict]:
    """kma-online.de – has RSS but also a clean HTML structure."""
    # Try RSS first
    for feed_url in source_config.get("rss_feeds", []):
        articles = parse_rss_feed(feed_url, source_config)
        if articles:
            return articles
    # Fallback scrape
    return parse_generic_scrape(scrape_url, source_config)


def parse_springer_pflege(scrape_url: str, source_config: dict) -> list[dict]:
    """springerpflege.de – adapt if RSS is unreliable."""
    for feed_url in source_config.get("rss_feeds", []):
        articles = parse_rss_feed(feed_url, source_config)
        if articles:
            return articles
    return parse_generic_scrape(scrape_url, source_config)


def parse_aok_pflege(scrape_url: str, source_config: dict) -> list[dict]:
    """AOK news page – often has broad RSS; filter Pflege category."""
    for feed_url in source_config.get("rss_feeds", []):
        candidates = parse_rss_feed(feed_url, source_config)
        # Only keep entries whose URL or title suggests Pflege
        filtered = [
            a for a in candidates
            if "pflege" in a["article_url"].lower()
            or "pflege" in a["headline"].lower()
        ]
        if filtered:
            return filtered
    return parse_generic_scrape(scrape_url, source_config)


# ──────────────────────────────────────────────────────────────
# Parser registry – maps parser_key → callable
# ──────────────────────────────────────────────────────────────

PARSER_REGISTRY: dict[str, callable] = {
    "kma_online": parse_kma_online,
    "springer_pflege": parse_springer_pflege,
    "aok_pflege": parse_aok_pflege,
}


def get_parser(source_config: dict):
    """Return the appropriate parser function for this source."""
    key = source_config.get("parser_key")
    if key and key in PARSER_REGISTRY:
        return PARSER_REGISTRY[key]

    # Default: try RSS first, fall back to scrape
    def _default(url, cfg):
        for feed_url in cfg.get("rss_feeds", []):
            articles = parse_rss_feed(feed_url, cfg)
            if articles:
                return articles
        return parse_generic_scrape(cfg.get("scrape_url", ""), cfg)

    return _default


# ──────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip())


def _strip_html(html: str) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "lxml").get_text(separator=" ", strip=True)


def _parse_date(date_str: str) -> Optional[str]:
    if not date_str:
        return None
    try:
        dt = dateparser.parse(date_str, fuzzy=True)
        if dt:
            return dt.isoformat()
    except Exception:
        pass
    return None


def _absolute_url(href: str, base_url: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    from urllib.parse import urljoin
    return urljoin(base_url, href)
