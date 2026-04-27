"""
app.py – TERN LinkedIn Newsroom
Main Flask application entry point.
"""

import os
import json
from datetime import datetime, timedelta
from functools import wraps

from dotenv import load_dotenv
load_dotenv()

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, jsonify, g
)
from werkzeug.security import generate_password_hash, check_password_hash

from database import get_db, close_db, init_db

# ──────────────────────────────────────────────────────────────
# App factory
# ──────────────────────────────────────────────────────────────

def create_app(test_config=None):
    app = Flask(__name__)
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-insecure-key-change-me")

    if test_config:
        app.config.update(test_config)

    # Tear down DB connection after each request
    app.teardown_appcontext(close_db)

    # Initialise schema
    init_db(app)

    # Start scheduler if enabled
    if os.environ.get("ENABLE_SCHEDULER", "true").lower() == "true":
        _start_scheduler(app)

    # ──────────────────────────────────────────────────────────
    # Auth helpers
    # ──────────────────────────────────────────────────────────

    APP_USERNAME = os.environ.get("APP_USERNAME", "admin")
    APP_PASSWORD_HASH = generate_password_hash(os.environ.get("APP_PASSWORD", "tern2024"))

    def login_required(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get("logged_in"):
                return redirect(url_for("login", next=request.url))
            return f(*args, **kwargs)
        return decorated

    # ──────────────────────────────────────────────────────────
    # Template context helpers
    # ──────────────────────────────────────────────────────────

    @app.context_processor
    def inject_globals():
        return {
            "now": datetime.utcnow(),
            "app_name": "TERN LinkedIn Newsroom",
        }

    # ──────────────────────────────────────────────────────────
    # Auth routes
    # ──────────────────────────────────────────────────────────

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if session.get("logged_in"):
            return redirect(url_for("dashboard"))
        error = None
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            if username == APP_USERNAME and check_password_hash(APP_PASSWORD_HASH, password):
                session["logged_in"] = True
                session["username"] = username
                next_url = request.args.get("next") or url_for("dashboard")
                return redirect(next_url)
            error = "Ungültige Zugangsdaten."
        return render_template("login.html", error=error)

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    # ──────────────────────────────────────────────────────────
    # Dashboard
    # ──────────────────────────────────────────────────────────

    @app.route("/")
    @login_required
    def dashboard():
        db = get_db()

        days = int(request.args.get("days", 7))
        min_score = int(request.args.get("min_score", 0))
        cluster = request.args.get("cluster", "")
        source = request.args.get("source", "")
        status_filter = request.args.get("status", "")
        sort = request.args.get("sort", "score")

        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        query = """
            SELECT * FROM articles
            WHERE fetched_at >= ?
              AND tern_relevance_score >= ?
        """
        params = [cutoff, min_score]

        if cluster:
            query += " AND topic_cluster = ?"
            params.append(cluster)
        if source:
            query += " AND source_name = ?"
            params.append(source)
        if status_filter:
            query += " AND content_status = ?"
            params.append(status_filter)

        order = "tern_relevance_score DESC" if sort == "score" else "published_at DESC"
        query += f" ORDER BY {order}"

        articles = db.execute(query, params).fetchall()

        top_debate = db.execute("""
            SELECT * FROM articles
            WHERE fetched_at >= ? AND tern_relevance_score >= 70
              AND content_status NOT IN ('ignored','used')
            ORDER BY tern_relevance_score DESC LIMIT 5
        """, [cutoff]).fetchall()

        top_repost = db.execute("""
            SELECT * FROM articles
            WHERE fetched_at >= ? AND post_chance = 'high'
              AND content_status NOT IN ('ignored','used')
            ORDER BY published_at DESC LIMIT 5
        """, [cutoff]).fetchall()

        all_clusters = [r[0] for r in db.execute(
            "SELECT DISTINCT topic_cluster FROM articles WHERE topic_cluster IS NOT NULL ORDER BY topic_cluster"
        ).fetchall()]
        all_sources = [r[0] for r in db.execute(
            "SELECT DISTINCT source_name FROM articles ORDER BY source_name"
        ).fetchall()]

        recent_outputs = db.execute("""
            SELECT o.*, a.headline as article_headline
            FROM outputs o
            LEFT JOIN articles a ON o.article_id = a.id
            ORDER BY o.created_at DESC LIMIT 8
        """).fetchall()

        last_refresh = db.execute(
            "SELECT * FROM refresh_log ORDER BY started_at DESC LIMIT 1"
        ).fetchone()

        stats = {
            "total": db.execute("SELECT COUNT(*) FROM articles WHERE fetched_at >= ?", [cutoff]).fetchone()[0],
            "high_relevance": db.execute(
                "SELECT COUNT(*) FROM articles WHERE fetched_at >= ? AND tern_relevance_score >= 70", [cutoff]
            ).fetchone()[0],
            "unused": db.execute(
                "SELECT COUNT(*) FROM articles WHERE fetched_at >= ? AND content_status = 'new'", [cutoff]
            ).fetchone()[0],
            "outputs_today": db.execute(
                "SELECT COUNT(*) FROM outputs WHERE date(created_at) = date('now')"
            ).fetchone()[0],
        }

        return render_template(
            "dashboard.html",
            articles=articles,
            top_debate=top_debate,
            top_repost=top_repost,
            all_clusters=all_clusters,
            all_sources=all_sources,
            recent_outputs=recent_outputs,
            last_refresh=last_refresh,
            stats=stats,
            filters={"days": days, "min_score": min_score, "cluster": cluster,
                     "source": source, "status": status_filter, "sort": sort},
        )

    # ──────────────────────────────────────────────────────────
    # Article detail
    # ──────────────────────────────────────────────────────────

    @app.route("/article/<int:article_id>")
    @login_required
    def article_detail(article_id):
        db = get_db()
        article = db.execute("SELECT * FROM articles WHERE id = ?", [article_id]).fetchone()
        if not article:
            flash("Artikel nicht gefunden.", "error")
            return redirect(url_for("dashboard"))

        outputs = db.execute(
            "SELECT * FROM outputs WHERE article_id = ? ORDER BY created_at DESC",
            [article_id]
        ).fetchall()

        recommended_types = []
        if article["recommended_post_types"]:
            try:
                recommended_types = json.loads(article["recommended_post_types"])
            except Exception:
                recommended_types = [article["recommended_post_types"]]

        from services.generators import (
            POST_TYPES_NEWS, OBJECTIVES, PERSPECTIVES, TONES,
            WORDING_STYLES, LENGTHS, STRUCTURES, CTA_OPTIONS
        )

        return render_template(
            "article_detail.html",
            article=article,
            outputs=outputs,
            recommended_types=recommended_types,
            post_types=POST_TYPES_NEWS,
            objectives=OBJECTIVES,
            perspectives=PERSPECTIVES,
            tones=TONES,
            wording_styles=WORDING_STYLES,
            lengths=LENGTHS,
            structures=STRUCTURES,
            cta_options=CTA_OPTIONS,
        )

    @app.route("/article/<int:article_id>/status", methods=["POST"])
    @login_required
    def update_article_status(article_id):
        db = get_db()
        new_status = request.form.get("status")
        is_favorite = request.form.get("is_favorite")

        if new_status in ("new", "reviewed", "ignored", "used"):
            db.execute(
                "UPDATE articles SET content_status=?, updated_at=datetime('now') WHERE id=?",
                [new_status, article_id]
            )
        if is_favorite is not None:
            db.execute(
                "UPDATE articles SET is_favorite=?, updated_at=datetime('now') WHERE id=?",
                [1 if is_favorite == "1" else 0, article_id]
            )
        db.commit()

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"ok": True})
        return redirect(url_for("article_detail", article_id=article_id))

    # ──────────────────────────────────────────────────────────
    # Post generation from article
    # ──────────────────────────────────────────────────────────

    @app.route("/article/<int:article_id>/generate", methods=["POST"])
    @login_required
    def generate_from_article(article_id):
        db = get_db()
        article = db.execute("SELECT * FROM articles WHERE id = ?", [article_id]).fetchone()
        if not article:
            flash("Artikel nicht gefunden.", "error")
            return redirect(url_for("dashboard"))

        settings = {
            "output_type":    request.form.get("output_type", "explanatory_comment"),
            "objective":      request.form.get("objective", "Positionierung"),
            "perspective":    request.form.get("perspective", "TERN corporate"),
            "tone":           request.form.get("tone", "sachlich-einordnend"),
            "wording_style":  request.form.get("wording_style", "deutsch business-clean"),
            "length":         request.form.get("length", "mittel"),
            "structure":      request.form.get("structure", "with hook"),
            "cta":            request.form.get("cta", "ask opinion"),
        }

        from services.generators import generate_news_post
        try:
            result = generate_news_post(article=article, settings=settings)
        except Exception as e:
            flash(f"Generierung fehlgeschlagen: {e}", "error")
            return redirect(url_for("article_detail", article_id=article_id))

        db.execute("""
            INSERT INTO outputs
                (article_id, output_mode, output_type, objective, perspective, tone,
                 wording_style, length_setting, structure_setting, cta_setting,
                 title, content, rationale, media_recommendation, first_comment, hashtag_suggestion)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, [
            article_id, "news_based",
            settings["output_type"], settings["objective"], settings["perspective"],
            settings["tone"], settings["wording_style"], settings["length"],
            settings["structure"], settings["cta"],
            result.get("title", ""), result["content"],
            result.get("rationale", ""), result.get("media_recommendation", ""),
            result.get("first_comment", ""), result.get("hashtag_suggestion", ""),
        ])
        db.execute(
            "UPDATE articles SET content_status='used', updated_at=datetime('now') WHERE id=?",
            [article_id]
        )
        db.commit()
        output_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        return redirect(url_for("output_detail", output_id=output_id))

    # ──────────────────────────────────────────────────────────
    # Free content generator
    # ──────────────────────────────────────────────────────────

    @app.route("/generate", methods=["GET"])
    @login_required
    def free_generator():
        from services.generators import (
            POST_TYPES_FREE, OBJECTIVES, PERSPECTIVES, TONES,
            WORDING_STYLES, LENGTHS, STRUCTURES, CTA_OPTIONS,
            TARGET_AUDIENCES, CONTENT_TYPES_FREE
        )
        return render_template(
            "free_generator.html",
            post_types=POST_TYPES_FREE,
            objectives=OBJECTIVES,
            perspectives=PERSPECTIVES,
            tones=TONES,
            wording_styles=WORDING_STYLES,
            lengths=LENGTHS,
            structures=STRUCTURES,
            cta_options=CTA_OPTIONS,
            target_audiences=TARGET_AUDIENCES,
            content_types=CONTENT_TYPES_FREE,
        )

    @app.route("/generate", methods=["POST"])
    @login_required
    def free_generator_submit():
        db = get_db()

        settings = {
            "content_type":   request.form.get("content_type", ""),
            "output_type":    request.form.get("output_type", "opinion_stance"),
            "objective":      request.form.get("objective", "Positionierung"),
            "target_audience":request.form.get("target_audience", ""),
            "perspective":    request.form.get("perspective", "TERN corporate"),
            "tone":           request.form.get("tone", "sachlich-einordnend"),
            "wording_style":  request.form.get("wording_style", "deutsch business-clean"),
            "length":         request.form.get("length", "mittel"),
            "structure":      request.form.get("structure", "with hook"),
            "cta":            request.form.get("cta", "none"),
            "reference_links":request.form.get("reference_links", ""),
            "user_notes":     request.form.get("user_notes", ""),
            "key_points":     request.form.get("key_points", ""),
        }

        from services.generators import generate_free_post
        try:
            result = generate_free_post(settings=settings)
        except Exception as e:
            flash(f"Generierung fehlgeschlagen: {e}", "error")
            return redirect(url_for("free_generator"))

        db.execute("""
            INSERT INTO outputs
                (article_id, output_mode, output_type, objective, perspective, tone,
                 wording_style, length_setting, structure_setting, cta_setting,
                 title, content, rationale, media_recommendation, first_comment,
                 hashtag_suggestion, target_audience, reference_links, user_notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, [
            None, "free",
            settings["output_type"], settings["objective"], settings["perspective"],
            settings["tone"], settings["wording_style"], settings["length"],
            settings["structure"], settings["cta"],
            result.get("title", ""), result["content"],
            result.get("rationale", ""), result.get("media_recommendation", ""),
            result.get("first_comment", ""), result.get("hashtag_suggestion", ""),
            settings["target_audience"], settings["reference_links"], settings["user_notes"],
        ])
        db.commit()
        output_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        return redirect(url_for("output_detail", output_id=output_id))

    # ──────────────────────────────────────────────────────────
    # Outputs
    # ──────────────────────────────────────────────────────────

    @app.route("/outputs")
    @login_required
    def outputs_list():
        db = get_db()
        outputs = db.execute("""
            SELECT o.*, a.headline as article_headline, a.source_name
            FROM outputs o
            LEFT JOIN articles a ON o.article_id = a.id
            ORDER BY o.created_at DESC
        """).fetchall()
        return render_template("outputs_list.html", outputs=outputs)

    @app.route("/output/<int:output_id>")
    @login_required
    def output_detail(output_id):
        db = get_db()
        output = db.execute("SELECT * FROM outputs WHERE id = ?", [output_id]).fetchone()
        if not output:
            flash("Output nicht gefunden.", "error")
            return redirect(url_for("outputs_list"))

        article = None
        if output["article_id"]:
            article = db.execute(
                "SELECT * FROM articles WHERE id = ?", [output["article_id"]]
            ).fetchone()

        return render_template("output_detail.html", output=output, article=article)

    @app.route("/output/<int:output_id>/delete", methods=["POST"])
    @login_required
    def delete_output(output_id):
        db = get_db()
        db.execute("DELETE FROM outputs WHERE id=?", [output_id])
        db.commit()
        flash("Output gelöscht.", "info")
        return redirect(url_for("outputs_list"))

    # ──────────────────────────────────────────────────────────
    # Manual refresh
    # ──────────────────────────────────────────────────────────

    @app.route("/refresh", methods=["POST"])
    @login_required
    def manual_refresh():
        from services.ingestion import run_full_refresh
        try:
            result = run_full_refresh(triggered_by="manual")
            flash(
                f"Aktualisierung abgeschlossen: {result['added']} neue Artikel, "
                f"{result['skipped']} übersprungen.",
                "success"
            )
        except Exception as e:
            flash(f"Fehler bei der Aktualisierung: {e}", "error")
        return redirect(url_for("dashboard"))

    # ──────────────────────────────────────────────────────────
    # AI re-analysis
    # ──────────────────────────────────────────────────────────

    @app.route("/article/<int:article_id>/analyse", methods=["POST"])
    @login_required
    def analyse_article(article_id):
        db = get_db()
        article = db.execute("SELECT * FROM articles WHERE id = ?", [article_id]).fetchone()
        if not article:
            return jsonify({"error": "not found"}), 404

        from services.scoring import analyse_article_with_ai
        try:
            analysis = analyse_article_with_ai(dict(article))
            db.execute("""
                UPDATE articles SET
                    summary_short=?, summary_long=?,
                    tern_relevance_score=?, tern_relevance_reasoning=?,
                    topic_cluster=?, tern_angle=?,
                    recommended_post_types=?, post_chance=?,
                    updated_at=datetime('now')
                WHERE id=?
            """, [
                analysis.get("summary_short"),
                analysis.get("summary_long"),
                analysis.get("tern_relevance_score", 0),
                analysis.get("tern_relevance_reasoning"),
                analysis.get("topic_cluster"),
                analysis.get("tern_angle"),
                json.dumps(analysis.get("recommended_post_types", []), ensure_ascii=False),
                analysis.get("post_chance"),
                article_id,
            ])
            db.commit()
            flash("Analyse aktualisiert.", "success")
        except Exception as e:
            flash(f"Analyse fehlgeschlagen: {e}", "error")

        return redirect(url_for("article_detail", article_id=article_id))

    return app


# ──────────────────────────────────────────────────────────────
# Scheduler helper (outside factory to avoid closure issues)
# ──────────────────────────────────────────────────────────────

def _start_scheduler(app):
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        import pytz

        tz = pytz.timezone("Europe/Berlin")
        hour   = int(os.environ.get("DAILY_REFRESH_HOUR",   10))
        minute = int(os.environ.get("DAILY_REFRESH_MINUTE",  0))

        scheduler = BackgroundScheduler(timezone=tz)

        def _scheduled_refresh():
            with app.app_context():
                from services.ingestion import run_full_refresh
                run_full_refresh(triggered_by="scheduler")

        scheduler.add_job(
            _scheduled_refresh,
            trigger=CronTrigger(hour=hour, minute=minute, timezone=tz),
            id="daily_refresh",
            replace_existing=True,
        )
        scheduler.start()
        app.logger.info(f"Scheduler started – daily refresh at {hour:02d}:{minute:02d} CET/CEST")
    except Exception as e:
        app.logger.warning(f"Could not start scheduler: {e}")


# ──────────────────────────────────────────────────────────────
# Entrypoint
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = create_app()
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug, host="0.0.0.0", port=5050)
