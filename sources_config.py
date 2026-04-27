"""
sources_config.py – Explicit source definitions with tiering, RSS feeds,
and per-source metadata.

To add a new source: append an entry to SOURCES and optionally register
a custom parser function in services/source_parsers.py.
"""

# Each source dict:
#   name          – display name
#   tier          – 1 (strongest relevance weight), 2, or 3
#   home_url      – canonical homepage
#   rss_feeds     – list of RSS/Atom feed URLs (prefer over scraping)
#   scrape_url    – fallback URL to scrape if no RSS available
#   parser_key    – key to look up a custom parser in source_parsers.py
#                   (None = use generic RSS / generic scraper)
#   base_weight   – multiplier applied to relevance scoring (0.0–1.0)

SOURCES = [
    # ─── Tier 1 ──────────────────────────────────────────────────────────
    {
        "name": "Care vor 9",
        "tier": 1,
        "home_url": "https://www.care-vor-9.de",
        "rss_feeds": [
            "https://www.care-vor-9.de/feed/",
        ],
        "scrape_url": "https://www.care-vor-9.de",
        "parser_key": None,
        "base_weight": 1.0,
    },
    {
        "name": "kma Online",
        "tier": 1,
        "home_url": "https://www.kma-online.de",
        "rss_feeds": [
            "https://www.kma-online.de/rss/neuigkeiten.rss",
            "https://www.kma-online.de/rss/pflege.rss",
        ],
        "scrape_url": "https://www.kma-online.de/aktuelles/pflege",
        "parser_key": "kma_online",
        "base_weight": 1.0,
    },
    {
        "name": "Bibliomed Pflege",
        "tier": 1,
        "home_url": "https://www.bibliomed-pflege.de",
        "rss_feeds": [
            "https://www.bibliomed-pflege.de/news/feed/",
        ],
        "scrape_url": "https://www.bibliomed-pflege.de/news/",
        "parser_key": None,
        "base_weight": 1.0,
    },
    {
        "name": "Springer Pflege",
        "tier": 1,
        "home_url": "https://www.springerpflege.de",
        "rss_feeds": [
            "https://www.springerpflege.de/rss/news",
        ],
        "scrape_url": "https://www.springerpflege.de/news",
        "parser_key": "springer_pflege",
        "base_weight": 1.0,
    },
    {
        "name": "Altenheim.net",
        "tier": 1,
        "home_url": "https://www.altenheim.net",
        "rss_feeds": [
            "https://www.altenheim.net/feed/",
        ],
        "scrape_url": "https://www.altenheim.net",
        "parser_key": None,
        "base_weight": 0.95,
    },
    {
        "name": "altenpflege-online.net",
        "tier": 1,
        "home_url": "https://www.altenpflege-online.net",
        "rss_feeds": [
            "https://www.altenpflege-online.net/feed/",
        ],
        "scrape_url": "https://www.altenpflege-online.net",
        "parser_key": None,
        "base_weight": 0.95,
    },
    # ─── Tier 2 ──────────────────────────────────────────────────────────
    {
        "name": "AOK News Pflege",
        "tier": 2,
        "home_url": "https://www.aok.de/pk/pflege/",
        "rss_feeds": [
            "https://www.aok.de/pk/rss/",
        ],
        "scrape_url": "https://www.aok.de/pk/pflege/",
        "parser_key": "aok_pflege",
        "base_weight": 0.75,
    },
    {
        "name": "Haufe Pflege",
        "tier": 2,
        "home_url": "https://www.haufe.de/sozialwesen/pflege",
        "rss_feeds": [
            "https://www.haufe.de/rss/sozialwesen.rss",
        ],
        "scrape_url": "https://www.haufe.de/sozialwesen/pflege",
        "parser_key": None,
        "base_weight": 0.75,
    },
    {
        "name": "Deutsches Pflegeportal",
        "tier": 2,
        "home_url": "https://www.deutsches-pflegeportal.de",
        "rss_feeds": [
            "https://www.deutsches-pflegeportal.de/feed/",
        ],
        "scrape_url": "https://www.deutsches-pflegeportal.de",
        "parser_key": None,
        "base_weight": 0.70,
    },
    # ─── Tier 3 ──────────────────────────────────────────────────────────
    {
        "name": "pflege.de",
        "tier": 3,
        "home_url": "https://www.pflege.de",
        "rss_feeds": [
            "https://www.pflege.de/feed/",
        ],
        "scrape_url": "https://www.pflege.de",
        "parser_key": None,
        "base_weight": 0.50,
    },
]

# Quick lookup by name
SOURCES_BY_NAME = {s["name"]: s for s in SOURCES}

# Tier → base relevance boost (added to raw keyword score before weighting)
TIER_SCORE_BOOST = {
    1: 15,
    2: 8,
    3: 0,
}
