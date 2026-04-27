"""
services/generators.py – LinkedIn post generation.

Two modes:
  generate_news_post()  – article-based generation
  generate_free_post()  – free content generation

Both return a structured "posting package" dict:
  {title, content, rationale, media_recommendation,
   first_comment, hashtag_suggestion}
"""

from __future__ import annotations
import json
import logging
import os

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")

# ──────────────────────────────────────────────────────────────
# UI option sets (used by both templates and route handlers)
# ──────────────────────────────────────────────────────────────

POST_TYPES_NEWS = [
    ("neutral_summary",                   "Neutrale Zusammenfassung / Repost"),
    ("explanatory_comment",               "Erklärender Kommentar"),
    ("positive_comment",                  "Positiver Kommentar"),
    ("critical_comment",                  "Kritischer Kommentar"),
    ("pointed_debate",                    "Pointiert / debattenstark"),
    ("thought_leadership",                "Thought Leadership"),
    ("whats_missing",                     "\"Was hier fehlt\"-Post"),
    ("recruiting_twist",                  "Recruiting-Twist"),
    ("policy_twist",                      "Politik-/System-Twist"),
    ("digitalization_twist",              "Digitalisierungs-Twist"),
    ("employer_perspective",              "Arbeitgeber-/Trägerperspektive"),
    ("international_recruiting_perspective", "Internationale Rekrutierungsperspektive"),
]

POST_TYPES_FREE = [
    ("event_announcement",                "Eventbesuch / Ankündigung"),
    ("event_recap",                       "Event-Recap"),
    ("development_comment",               "Kommentar zu aktueller Entwicklung"),
    ("company_update",                    "Unternehmens-Update"),
    ("partnership_update",                "Partnerschafts-Update"),
    ("product_thought",                   "Produkt-/Feature-Gedanke"),
    ("opinion_stance",                    "Meinung / Haltung"),
    ("behind_scenes",                     "Behind the Scenes"),
    ("market_observation",                "Marktbeobachtung"),
    ("success_story",                     "Erfolgsgeschichte / Case"),
    ("team_job_update",                   "Team- / Stellenupdate"),
    ("political_positioning",             "Politische Positionierung"),
    ("congress_fair",                     "Kongress / Messe / Veranstaltung"),
    ("invitation_exchange",               "Einladung zum Austausch"),
    ("reaction_post",                     "Reaktions-Post"),
    ("carousel_intro",                    "Karussell-Intro-Post"),
    ("video_caption",                     "Video-Untertiteltext"),
]

CONTENT_TYPES_FREE = [
    ("recruiting",        "Recruiting / Fachkräftethema"),
    ("policy",            "Politik / Positionierung"),
    ("event",             "Veranstaltung / Kongress"),
    ("product",           "Produkt / Leistung / Feature"),
    ("company",           "Unternehmen / Team / Kultur"),
    ("market",            "Marktentwicklung"),
    ("personal",          "Persönliche Erfahrung / Perspektive"),
    ("partnership",       "Partnerschaft / Kooperation"),
    ("opinion",           "Meinung / Stellungnahme"),
    ("education",         "Ausbildung / Qualifizierung / Anerkennung"),
]

OBJECTIVES = [
    ("Reichweite",            "Reichweite"),
    ("Positionierung",        "Positionierung"),
    ("Thought Leadership",    "Thought Leadership"),
    ("Lead-Anbahnung",        "Lead-Anbahnung"),
    ("Event Awareness",       "Event Awareness"),
    ("Partnerpflege",         "Partnerpflege"),
    ("politische Sichtbarkeit", "Politische Sichtbarkeit"),
    ("Arbeitgebermarke",      "Arbeitgebermarke"),
    ("Recruiting Awareness",  "Recruiting Awareness"),
]

PERSPECTIVES = [
    ("TERN corporate",             "TERN Unternehmen (Wir)"),
    ("Geschäftsführer",            "Geschäftsführer-Perspektive"),
    ("Sales",                      "Sales-Perspektive"),
    ("Public Affairs",             "Public Affairs / Politik"),
    ("Recruiting",                 "Recruiting-Perspektive"),
    ("Marketing",                  "Marketing / Events"),
    ("personal_ich",               "Persönlich (Ich-Perspektive)"),
    ("wir_team",                   "Team-\"Wir\"-Perspektive"),
]

TONES = [
    ("neutral",                "Neutral"),
    ("sachlich-einordnend",    "Sachlich-einordnend"),
    ("professionell-locker",   "Professionell-locker"),
    ("pointiert",              "Pointiert"),
    ("kritisch",               "Kritisch"),
    ("optimistisch",           "Optimistisch"),
    ("provokant aber seriös",  "Provokant aber seriös"),
    ("politisch sensibel",     "Politisch sensibel"),
    ("visionär",               "Visionär"),
    ("debattenstark",          "Debattenstark"),
]

WORDING_STYLES = [
    ("deutsch business-clean",        "Deutsch business-clean"),
    ("deutsch meinungsstärker",       "Deutsch meinungsstärker"),
    ("sehr formal",                   "Sehr formal"),
    ("linkedin-prägnant",             "LinkedIn-prägnant"),
    ("wenig buzzwords",               "Wenig Buzzwords"),
    ("ohne emojis",                   "Ohne Emojis"),
    ("wenige emojis",                 "Wenige Emojis"),
    ("ohne hashtags",                 "Ohne Hashtags"),
    ("mit wenigen hashtags",          "Mit wenigen Hashtags"),
]

LENGTHS = [
    ("kurz",                   "Kurz (bis ~800 Zeichen)"),
    ("mittel",                 "Mittel (~1000–1500 Zeichen)"),
    ("ausführlich",            "Ausführlich (~1500–2500 Zeichen)"),
]

STRUCTURES = [
    ("with hook",              "Mit starkem Hook-Opener"),
    ("with statistic",         "Mit Statistik-Einstieg"),
    ("with question",          "Mit Frage-Einstieg"),
    ("with thesis",            "Mit starker These"),
    ("with 3 points",          "Mit 3 Kernpunkten"),
    ("with conclusion_cta",    "Mit Fazit + CTA"),
]

CTA_OPTIONS = [
    ("none",                   "Kein CTA"),
    ("ask_opinion",            "Nach Meinung fragen"),
    ("invite_exchange",        "Zum Austausch einladen"),
    ("invite_dm",              "Zu DM einladen"),
    ("point_event",            "Auf Event hinweisen"),
    ("point_resource",         "Auf Ressource hinweisen"),
    ("point_booking",          "Zu Gespräch / Buchung"),
    ("point_link",             "Zu Link / PDF"),
    ("wie_sehen_sie_das",      "\"Wie sehen Sie das?\""),
]

TARGET_AUDIENCES = [
    ("Kliniken und Träger",              "Kliniken und Träger"),
    ("HR-Verantwortliche",               "HR-Verantwortliche"),
    ("Pflegeeinrichtungen",              "Pflegeeinrichtungen"),
    ("Politik und Verwaltung",           "Politik und Verwaltung"),
    ("Pflegefachkräfte",                 "Pflegefachkräfte"),
    ("Investoren / Entscheider",         "Investoren / Entscheider"),
    ("Allgemeine Fachöffentlichkeit",    "Allgemeine Fachöffentlichkeit"),
    ("Partnerorganisationen",            "Partnerorganisationen"),
]

# ──────────────────────────────────────────────────────────────
# Media recommendation logic
# ──────────────────────────────────────────────────────────────

MEDIA_RECOMMENDATIONS = {
    "neutral_summary":                   "Screenshot des Artikelheadlines als Statement Card",
    "explanatory_comment":               "Infografik oder Statement Card mit Kernaussage",
    "positive_comment":                  "Statement Card oder kein Bild nötig",
    "critical_comment":                  "Keine Medien (stärkere Wirkung reiner Text)",
    "pointed_debate":                    "Kein Bild – lässt den Text wirken",
    "thought_leadership":                "Statement Card oder professionelles Portrait-Foto",
    "whats_missing":                     "Infografik: \"Was fehlt\"-Gegenüberstellung",
    "recruiting_twist":                  "Teamfoto oder Karussell mit Lösungsansätzen",
    "policy_twist":                      "Screenshot oder Statement Card mit Zitat",
    "digitalization_twist":              "Screenshot einer digitalen Lösung / App-UI",
    "employer_perspective":              "Teamfoto oder Arbeitgeberbrand-Visual",
    "international_recruiting_perspective": "Foto internationaler Teamaufstellung",
    "event_announcement":                "Event-Bannerbild oder Kongressfoto",
    "event_recap":                       "Foto vom Event, ggf. Karussell",
    "development_comment":               "Statement Card",
    "company_update":                    "Teamfoto oder Bürofoto",
    "partnership_update":                "Gemeinsames Logo oder Handshake-Foto",
    "product_thought":                   "Screenshot / Demo-Bild des Produkts",
    "opinion_stance":                    "Kein Bild oder minimales Statement Card",
    "behind_scenes":                     "Authentisches Team- / Behind-the-scenes-Foto",
    "market_observation":                "Infografik oder Diagramm",
    "success_story":                     "Foto der Person / Einrichtung (anonymisiert)",
    "team_job_update":                   "Teamfoto oder Stellenausschreibungs-Grafik",
    "political_positioning":             "Kein Bild oder Statement Card mit Kernaussage",
    "congress_fair":                     "Standfotos oder Messe-Banner",
    "invitation_exchange":               "Portrait oder informelles Foto",
    "reaction_post":                     "Screenshot des Original-Posts / Artikels",
    "carousel_intro":                    "Erstes Karussell-Slide als Teaser",
    "video_caption":                     "Talking-Head-Video oder animiertes Statement",
}


def get_media_recommendation(output_type: str) -> str:
    return MEDIA_RECOMMENDATIONS.get(output_type, "Statement Card oder kein Bild")


# ──────────────────────────────────────────────────────────────
# System prompt base
# ──────────────────────────────────────────────────────────────

TERN_CONTEXT = """Du bist ein erfahrener LinkedIn-Content-Stratege für TERN Healthcare Recruiting.

TERN ist ein spezialisiertes Unternehmen für:
- Internationale Rekrutierung von Pflegefachkräften für deutsche Kliniken und Pflegeeinrichtungen
- Unterstützung bei Anerkennungsverfahren für ausländische Pflegeabschlüsse
- Digitale Prozessunterstützung für die Personalgewinnung
- Strukturelle Lösungen für den Pflegepersonalmangel in Deutschland

LinkedIn-Kompetenz:
- Starke Hooks in den ersten 2-3 Zeilen (vor „Mehr anzeigen")
- Klare Struktur ohne unnötigen Fülltext
- Persönlichkeit und Haltung statt generischer Phrasen
- Konkreter, handlungsrelevanter Inhalt
- Natürliche Sprache – nicht wie ein Pressemitteilungs-Generator
- Keine übertriebene Emoji-Nutzung
- CTA nur wenn sinnvoll und natürlich

Qualitätskriterien für einen starken Post:
- Relevanz: Warum ist das jetzt für die Zielgruppe wichtig?
- Perspektive: Was ist die konkrete TERN-Sichtweise?
- Mehrwert: Was lernt der Leser oder was bringt ihm der Post?
- Call-to-action: Nur wenn er organisch passt"""


def _build_style_instructions(settings: dict) -> str:
    parts = []

    length = settings.get("length", "mittel")
    if length == "kurz":
        parts.append("Länge: Kurz und prägnant, ca. 500–800 Zeichen.")
    elif length == "ausführlich":
        parts.append("Länge: Ausführlich, ca. 1500–2500 Zeichen. Mit Tiefe und Substanz.")
    else:
        parts.append("Länge: Mittel, ca. 1000–1500 Zeichen.")

    tone = settings.get("tone", "")
    if tone:
        parts.append(f"Ton: {tone}")

    wording = settings.get("wording_style", "")
    if wording:
        parts.append(f"Schreibstil: {wording}")

    structure = settings.get("structure", "")
    structure_map = {
        "with hook":           "Starte mit einem starken Hook in den ersten 2 Zeilen.",
        "with statistic":      "Beginne mit einer konkreten Zahl oder Statistik.",
        "with question":       "Eröffne mit einer direkten, relevanten Frage.",
        "with thesis":         "Beginne mit einer pointierten These / Behauptung.",
        "with 3 points":       "Strukturiere den Post um 3 klar benannte Kernpunkte.",
        "with conclusion_cta": "Schließe mit einem klaren Fazit, dann optionalem CTA.",
    }
    if structure in structure_map:
        parts.append(f"Struktur: {structure_map[structure]}")

    cta = settings.get("cta", "none")
    cta_map = {
        "none":               "Kein expliziter CTA.",
        "ask_opinion":        "Ende: Frage nach der Meinung der Leser.",
        "invite_exchange":    "Ende: Lade zum fachlichen Austausch ein.",
        "invite_dm":          "Ende: Lade zu einer direkten Nachricht ein.",
        "point_event":        "Ende: Verweise auf eine Veranstaltung.",
        "point_resource":     "Ende: Verweise auf eine Ressource oder Studie.",
        "point_booking":      "Ende: Lade zu einem Gespräch oder einer Buchung ein.",
        "point_link":         "Ende: Verweise auf einen Link oder ein PDF.",
        "wie_sehen_sie_das":  "Ende: \"Wie sehen Sie das?\" als abschließende Frage.",
    }
    if cta in cta_map:
        parts.append(f"CTA: {cta_map[cta]}")

    perspective = settings.get("perspective", "")
    if perspective:
        parts.append(f"Perspektive / Absender: {perspective}")

    objective = settings.get("objective", "")
    if objective:
        parts.append(f"Ziel des Posts: {objective}")

    return "\n".join(f"- {p}" for p in parts)


# ──────────────────────────────────────────────────────────────
# News-based post generator
# ──────────────────────────────────────────────────────────────

def generate_news_post(article, settings: dict) -> dict:
    """
    Generate a LinkedIn post package based on a news article.
    article: sqlite3.Row or dict
    settings: dict with output_type, objective, perspective, tone, etc.
    """
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OpenAI API key nicht konfiguriert. "
            "Bitte OPENAI_API_KEY in .env setzen."
        )

    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)

    # Extract article data
    if hasattr(article, "keys"):
        art = dict(article)
    else:
        art = article

    headline = art.get("headline", "")
    summary = art.get("summary_short") or art.get("subheadline") or ""
    summary_long = art.get("summary_long") or ""
    tern_angle = art.get("tern_angle") or ""
    source = art.get("source_name", "")
    article_url = art.get("article_url", "")
    cluster = art.get("topic_cluster", "")
    output_type = settings.get("output_type", "explanatory_comment")

    style_block = _build_style_instructions(settings)

    post_type_label = dict(POST_TYPES_NEWS).get(output_type, output_type)

    user_prompt = f"""Erstelle einen starken LinkedIn-Post für TERN Healthcare Recruiting.

ARTIKEL:
Überschrift: {headline}
Quelle: {source}
Zusammenfassung: {summary}
Ausführliche Zusammenfassung: {summary_long}
TERN-Winkel: {tern_angle}
Themencluster: {cluster}
Original-URL: {article_url}

POST-TYP: {post_type_label}

STILANFORDERUNGEN:
{style_block}

Antworte NUR als valides JSON:
{{
  "title": "Kurzer interner Titel für den Draft (nicht der Post-Opener)",
  "content": "Der vollständige LinkedIn-Post-Text",
  "rationale": "Kurze Begründung (2-3 Sätze): Warum dieser Winkel, warum dieser Stil",
  "first_comment": "Vorgeschlagener erster Kommentar unter dem Post (kann Hashtags, Kontext oder Link enthalten)",
  "hashtag_suggestion": "3-6 empfohlene Hashtags als Leerzeichen-getrennte Zeichenkette",
  "media_recommendation": "Konkrete Empfehlung für Bildmaterial / Media-Format"
}}"""

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": TERN_CONTEXT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
        max_tokens=1800,
    )

    result = json.loads(response.choices[0].message.content)

    # Enrich with rule-based media recommendation if AI didn't specify
    if not result.get("media_recommendation"):
        result["media_recommendation"] = get_media_recommendation(output_type)

    return result


# ──────────────────────────────────────────────────────────────
# Free content post generator
# ──────────────────────────────────────────────────────────────

def generate_free_post(settings: dict) -> dict:
    """
    Generate a LinkedIn post package from user-defined settings (no source article).
    """
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OpenAI API key nicht konfiguriert. "
            "Bitte OPENAI_API_KEY in .env setzen."
        )

    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)

    output_type = settings.get("output_type", "opinion_stance")
    content_type = settings.get("content_type", "")
    target_audience = settings.get("target_audience", "")
    reference_links = settings.get("reference_links", "")
    user_notes = settings.get("user_notes", "")
    key_points = settings.get("key_points", "")

    style_block = _build_style_instructions(settings)
    post_type_label = dict(POST_TYPES_FREE).get(output_type, output_type)
    content_type_label = dict(CONTENT_TYPES_FREE).get(content_type, content_type)

    notes_block = ""
    if user_notes:
        notes_block += f"\nHinweise / Kontext: {user_notes}"
    if key_points:
        notes_block += f"\nKernpunkte / Stichworte: {key_points}"
    if reference_links:
        notes_block += f"\nReferenz-Links: {reference_links}"

    user_prompt = f"""Erstelle einen starken LinkedIn-Post für TERN Healthcare Recruiting.

POST-TYP: {post_type_label}
INHALTSBEREICH: {content_type_label}
ZIELGRUPPE: {target_audience}
{notes_block}

STILANFORDERUNGEN:
{style_block}

Antworte NUR als valides JSON:
{{
  "title": "Kurzer interner Titel für den Draft",
  "content": "Der vollständige LinkedIn-Post-Text",
  "rationale": "Kurze Begründung (2-3 Sätze): Warum dieser Ansatz stark ist",
  "first_comment": "Vorgeschlagener erster Kommentar unter dem Post",
  "hashtag_suggestion": "3-6 empfohlene Hashtags als Leerzeichen-getrennte Zeichenkette",
  "media_recommendation": "Konkrete Empfehlung für Bildmaterial / Media-Format"
}}"""

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": TERN_CONTEXT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.75,
        max_tokens=1800,
    )

    result = json.loads(response.choices[0].message.content)

    if not result.get("media_recommendation"):
        result["media_recommendation"] = get_media_recommendation(output_type)

    return result
