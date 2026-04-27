"""
services/scoring.py – TERN relevance scoring, topic cluster classification,
TERN angle recommendation, and AI-powered deep analysis.

Two scoring modes:
  1. quick_keyword_score()  – fast, synchronous, keyword-based; used during
                              ingestion to pre-score every article immediately.
  2. analyse_article_with_ai() – GPT-4o-powered deep analysis; called on-demand
                                 when the user opens an article or triggers
                                 re-analysis.
"""

from __future__ import annotations
import json
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")

# ──────────────────────────────────────────────────────────────
# TERN Relevance keyword taxonomy
# (weights sum roughly to 100 for a perfectly matching article)
# ──────────────────────────────────────────────────────────────

HIGH_PRIORITY_KEYWORDS = {
    # Staffing shortage
    "fachkräftemangel": 12,
    "personalmangel": 10,
    "pflegepersonal": 10,
    "pflegenotstand": 10,
    "personalengpass": 10,
    "pflegekräfte": 8,
    "pflegekraft": 8,
    "pflegemitarbeiter": 7,
    # International recruiting
    "internationale rekrutierung": 15,
    "auslandsrekrutierung": 14,
    "internationale fachkräfte": 14,
    "ausländische fachkräfte": 13,
    "fachkräftezuwanderung": 13,
    "zuwanderung fachkräfte": 12,
    "anwerbung": 9,
    "recruiting": 8,
    # Recognition and qualification pathways
    "anerkennung": 10,
    "anerkennungsverfahren": 11,
    "berufsanerkennung": 11,
    "ausländische abschlüsse": 12,
    "qualifikationsanerkennung": 11,
    "gleichwertigkeitsprüfung": 10,
    "defizitprüfung": 8,
    # Labour migration
    "einwanderung": 7,
    "migration": 7,
    "visa": 8,
    "fachkräfteeinwanderungsgesetz": 12,
    "aufenthaltserlaubnis": 8,
    "arbeitsmigration": 10,
    "zuwanderer": 7,
    "migranten": 6,
    # Employer attractiveness
    "arbeitgeberattraktivität": 10,
    "employer branding": 10,
    "fachkräftebindung": 8,
    "mitarbeiterbindung": 7,
    "mitarbeitergewinnung": 9,
    # Healthcare staffing
    "krankenhauspersonal": 10,
    "klinikmitarbeiter": 9,
    "altenpflegepersonal": 10,
    "pflegeberufe": 8,
    "healthcare recruiting": 10,
    "cross-border": 9,
    "grenzüberschreitend": 8,
    # Digitalization in recruiting
    "digitalisierung recruiting": 10,
    "hr-digitalisierung": 8,
    "digitale personalgewinnung": 9,
}

MEDIUM_PRIORITY_KEYWORDS = {
    "pflegepolitik": 5,
    "krankenhausmanagement": 5,
    "klinikmanagement": 5,
    "pflegeheimbetrieb": 4,
    "einrichtungsmanagement": 4,
    "ambulante pflege": 5,
    "pflegeheim": 4,
    "altenheim": 4,
    "altenpflege": 5,
    "pflegewirtschaft": 5,
    "gesundheitswirtschaft": 5,
    "pflegereform": 5,
    "krankenhausreform": 5,
    "pflegefinanzierung": 4,
    "pflegeversicherung": 4,
    "digitale gesundheit": 4,
    "digitalisierung pflege": 6,
    "telemedizin": 3,
    "pflegetechnologie": 5,
    "ausbildung pflege": 6,
    "pflegeausbildung": 6,
    "qualifizierung": 5,
    "weiterbildung pflege": 5,
    "generalistik": 5,
}

LOW_PRIORITY_KEYWORDS = {
    "pflege": 2,
    "gesundheit": 1,
    "krankenhaus": 2,
    "klinik": 2,
    "arzt": 1,
    "patient": 1,
    "versorgung": 2,
    "gesundheitsversorgung": 3,
    "pflegeleistung": 2,
    "häusliche pflege": 2,
    "sozialwesen": 2,
}

# ──────────────────────────────────────────────────────────────
# Topic cluster taxonomy
# ──────────────────────────────────────────────────────────────

TOPIC_CLUSTERS = [
    "Pflegepolitik",
    "Krankenhausmanagement",
    "Altenpflege / stationäre Pflege",
    "Ambulante Pflege",
    "Personal / Recruiting",
    "Internationale Fachkräfte",
    "Ausbildung / Qualifizierung",
    "Anerkennung / Migration / Visa",
    "Digitalisierung",
    "Finanzierung / Trägerdruck",
    "Arbeitgeberattraktivität / Employer Branding",
    "Gesundheitswirtschaft",
    "Versorgung / Strukturfragen",
    "Sonstiges",
]

# Keywords that map strongly to each cluster
CLUSTER_SIGNALS: dict[str, list[str]] = {
    "Internationale Fachkräfte": [
        "international", "ausland", "ausländisch", "migration", "zuwanderung",
        "visa", "anwerbung", "rekrutierung", "cross-border", "overseas",
        "anerkennung", "anerkennungsverfahren",
    ],
    "Anerkennung / Migration / Visa": [
        "anerkennung", "anerkennungsverfahren", "gleichwertigkeit", "defizit",
        "visa", "aufenthaltserlaubnis", "einwanderung", "fachkräfteeinwanderungsgesetz",
    ],
    "Personal / Recruiting": [
        "fachkräftemangel", "personalmangel", "recruiting", "personalgewinnung",
        "mitarbeitergewinnung", "employer", "arbeitgeberattraktivität", "fachkraft",
    ],
    "Arbeitgeberattraktivität / Employer Branding": [
        "arbeitgeberattraktivität", "employer branding", "mitarbeiterbindung",
        "fachkräftebindung", "arbeitgebermarke", "arbeitskultur",
    ],
    "Ausbildung / Qualifizierung": [
        "ausbildung", "pflegeausbildung", "qualifizierung", "weiterbildung",
        "generalistik", "lehrplan", "schule", "studium",
    ],
    "Digitalisierung": [
        "digitalisierung", "digital", "ki", "künstliche intelligenz",
        "software", "plattform", "technologie", "telemedizin", "app",
    ],
    "Pflegepolitik": [
        "politik", "gesetz", "reform", "bundesgesundheitsminister", "bundestag",
        "pflegepolitik", "pflegereform", "krankenhausreform",
    ],
    "Krankenhausmanagement": [
        "krankenhaus", "klinik", "klinikum", "krankenhausmanagement",
        "klinikreform", "stationär", "akut",
    ],
    "Altenpflege / stationäre Pflege": [
        "altenheim", "pflegeheim", "altenpflege", "stationäre pflege",
        "seniorenheim", "langzeitpflege",
    ],
    "Ambulante Pflege": [
        "ambulant", "häusliche pflege", "pflegedienst", "sozialstation",
    ],
    "Finanzierung / Trägerdruck": [
        "finanzierung", "pflegeversicherung", "eigenanteil", "kosten",
        "träger", "insolvenz", "refinanzierung",
    ],
    "Gesundheitswirtschaft": [
        "gesundheitswirtschaft", "gesundheitsmarkt", "gesundheitsökonomie",
        "wirtschaft", "umsatz", "markt",
    ],
    "Versorgung / Strukturfragen": [
        "versorgung", "unterversorgung", "strukturwandel", "lücke",
        "versorgungslücke", "fachkräftelücke",
    ],
}

# ──────────────────────────────────────────────────────────────
# TERN angle taxonomy
# ──────────────────────────────────────────────────────────────

TERN_ANGLES = {
    "international_recruiting": "🌍 Recruiting-Twist: Was das für internationale Rekrutierung bedeutet",
    "staffing_gap": "⚠️ Was hier im Recruiting fehlt – strukturelle Lücken",
    "clinic_impact": "🏥 Was das für Kliniken und Träger bedeutet",
    "care_facility_impact": "🏠 Was das für Pflegeeinrichtungen bedeutet",
    "symptom_only": "🔎 Warum das nur Symptombekämpfung ist – und was fehlt",
    "structural_solution": "🔧 Welche strukturelle Lösung jetzt gebraucht wird",
    "policy_twist": "📋 System-/Pflegepolitik-Twist aus Trägerperspektive",
    "employer_perspective": "👔 Arbeitgeber-/Träger-Twist",
    "digitalization_twist": "💻 Digitalisierungstwist: Prozesslösung als Antwort",
    "recognition_pathway": "📄 Anerkennungsweg – was TERN hier konkret löst",
}

# ──────────────────────────────────────────────────────────────
# 1. FAST KEYWORD SCORING (used during ingestion)
# ──────────────────────────────────────────────────────────────

def quick_keyword_score(headline: str, subheadline: str, content: str) -> dict:
    """
    Fast keyword-based relevance scoring. No external API calls.
    Returns: {score: int 0-100, cluster: str, post_chance: str}
    """
    text = f"{headline} {subheadline} {content}".lower()
    raw_score = 0

    for keyword, weight in HIGH_PRIORITY_KEYWORDS.items():
        if keyword in text:
            raw_score += weight

    for keyword, weight in MEDIUM_PRIORITY_KEYWORDS.items():
        if keyword in text:
            raw_score += weight

    for keyword, weight in LOW_PRIORITY_KEYWORDS.items():
        if keyword in text:
            raw_score += weight

    # Cap at 100
    score = min(raw_score, 100)

    # Cluster classification
    cluster = _classify_cluster(text)

    # Post chance
    if score >= 65:
        post_chance = "high"
    elif score >= 35:
        post_chance = "medium"
    else:
        post_chance = "low"

    return {"score": score, "cluster": cluster, "post_chance": post_chance}


def _classify_cluster(text_lower: str) -> str:
    """Return the best-matching topic cluster for a lowercased text block."""
    best_cluster = "Sonstiges"
    best_score = 0

    for cluster, signals in CLUSTER_SIGNALS.items():
        hit_count = sum(1 for s in signals if s in text_lower)
        if hit_count > best_score:
            best_score = hit_count
            best_cluster = cluster

    return best_cluster


# ──────────────────────────────────────────────────────────────
# 2. AI-POWERED DEEP ANALYSIS (on-demand via OpenAI)
# ──────────────────────────────────────────────────────────────

def analyse_article_with_ai(article: dict) -> dict:
    """
    Use GPT-4o to produce a full analysis of the article:
    - short summary (3 sentences)
    - detailed summary (1–2 paragraphs)
    - TERN relevance score 0–100
    - reasoning for the score
    - topic cluster
    - TERN angle recommendation
    - recommended LinkedIn post types
    - post chance (high / medium / low)

    Raises RuntimeError if OpenAI is not configured.
    """
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OpenAI API key nicht konfiguriert. "
            "Bitte OPENAI_API_KEY in .env setzen."
        )

    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)

    headline = article.get("headline", "")
    subheadline = article.get("subheadline") or ""
    raw_content = article.get("raw_content") or ""
    source_name = article.get("source_name", "")
    published_at = article.get("published_at", "")

    # Build the content blob to analyse (limit tokens)
    article_text = f"{headline}\n{subheadline}\n\n{raw_content}"[:4000]

    system_prompt = """Du bist ein erfahrener Redaktionsanalyst und LinkedIn-Content-Stratege für TERN Healthcare Recruiting.

TERN ist ein spezialisiertes Unternehmen für:
- Internationale Rekrutierung von Pflegefachkräften
- Unterstützung bei Anerkennungsverfahren für ausländische Pflegeabschlüsse
- Digitale Prozessunterstützung für Kliniken und Pflegeeinrichtungen
- Strukturelle Lösungen für den Pflegepersonalmangel in Deutschland

Deine Aufgabe: Analysiere jeden Artikel präzise aus der TERN-Perspektive.

Relevanzkriterien (hoch):
- Fachkräftemangel in Pflege/Gesundheitswesen
- Internationale Rekrutierung / Fachkräftezuwanderung
- Anerkennung ausländischer Abschlüsse
- Pflegepersonal / Krankenhauspersonal
- Arbeitsmarkt Pflege / Gesundheitswesen
- Visa, Migration, Arbeitsmobilität, Qualifizierungswege
- Employer Attractiveness / Arbeitgebermarke in Healthcare
- Strukturelle Versorgungslücken / Cross-border workforce
- Digitalisierung im Recruiting / Workforce-Prozessen

Relevanzkriterien (mittel):
- Pflegepolitik allgemein, Krankenhausmanagement
- Pflegeheimbetrieb / Einrichtungsmanagement
- Ambulante Pflege
- Pflegewirtschaft / Digital Health mit Personalimplikationen

Relevanzkriterien (niedrig):
- Rein klinische/pflegepraktische Themen ohne Recruiting-/Managementbezug
- Verbraucherorientierte Pflegeinhalte
- Lokale Einzelfallgeschichten ohne strategische Relevanz"""

    user_prompt = f"""Analysiere diesen Artikel für das TERN-Redaktionsteam:

Quelle: {source_name}
Datum: {published_at}
Artikel:
---
{article_text}
---

Antworte NUR als valides JSON mit dieser exakten Struktur:
{{
  "summary_short": "Kurzzusammenfassung in 2-3 Sätzen",
  "summary_long": "Ausführliche Zusammenfassung in 2 Absätzen",
  "tern_relevance_score": <Zahl 0-100>,
  "tern_relevance_reasoning": "Begründung der Relevanzeinstufung für TERN (2-4 Sätze)",
  "topic_cluster": "<einer aus: Pflegepolitik | Krankenhausmanagement | Altenpflege / stationäre Pflege | Ambulante Pflege | Personal / Recruiting | Internationale Fachkräfte | Ausbildung / Qualifizierung | Anerkennung / Migration / Visa | Digitalisierung | Finanzierung / Trägerdruck | Arbeitgeberattraktivität / Employer Branding | Gesundheitswirtschaft | Versorgung / Strukturfragen | Sonstiges>",
  "tern_angle": "Konkrete TERN-spezifische Perspektive und Kommentarrichtung (3-5 Sätze)",
  "tern_angle_type": "<einer aus: international_recruiting | staffing_gap | clinic_impact | care_facility_impact | symptom_only | structural_solution | policy_twist | employer_perspective | digitalization_twist | recognition_pathway>",
  "recommended_post_types": ["<post_type_1>", "<post_type_2>", "<post_type_3>"],
  "post_chance": "<high | medium | low>",
  "linkedin_performance_reasoning": "Kurze Einschätzung warum dieses Thema auf LinkedIn gut/schlecht performen würde"
}}

Mögliche Post-Typen: neutral_summary, explanatory_comment, positive_comment, critical_comment, pointed_debate, thought_leadership, whats_missing, recruiting_twist, policy_twist, digitalization_twist, employer_perspective, international_recruiting_perspective"""

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
        max_tokens=1500,
    )

    raw = response.choices[0].message.content
    result = json.loads(raw)

    # Enrich with human-readable angle label
    angle_type = result.get("tern_angle_type", "")
    if angle_type in TERN_ANGLES:
        result["tern_angle_label"] = TERN_ANGLES[angle_type]
    else:
        result["tern_angle_label"] = result.get("tern_angle", "")

    return result


# ──────────────────────────────────────────────────────────────
# Exposed constants for templates
# ──────────────────────────────────────────────────────────────

def get_topic_clusters() -> list[str]:
    return TOPIC_CLUSTERS


def get_tern_angles() -> dict[str, str]:
    return TERN_ANGLES
