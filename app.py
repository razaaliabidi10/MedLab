import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, request, redirect, url_for, flash
import mysql.connector

from config import Config
from models import User
from extensions import login_manager, csrf, limiter


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize extensions
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "warning"
    csrf.init_app(app)
    limiter.init_app(app)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs("logs", exist_ok=True)

    # Production-grade rotating log file handler (never logs secrets/tokens)
    file_handler = RotatingFileHandler(
        os.path.join("logs", "app.log"),
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
    ))
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)

    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.receptionist import receptionist_bp
    from routes.technician import technician_bp
    from routes.patient import patient_bp
    from routes.pathologist import pathologist_bp
    from routes.notifications import notifications_bp
    from routes.supabase_auth import supabase_auth_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(receptionist_bp)
    app.register_blueprint(technician_bp)
    app.register_blueprint(patient_bp)
    app.register_blueprint(pathologist_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(supabase_auth_bp)

    @app.route("/barcode/<barcode_string>/download", endpoint="download_barcode_image")
    def global_download_barcode_image(barcode_string):
        import io, re
        from flask import send_file, abort
        from flask_login import current_user
        if not current_user.is_authenticated:
            abort(401)
        from utils.barcode_generator import generate_barcode_png
        png_bytes = generate_barcode_png(barcode_string)
        clean_name = re.sub(r'[^A-Za-z0-9\-_.]', '', str(barcode_string))
        return send_file(
            io.BytesIO(png_bytes),
            mimetype="image/png",
            as_attachment=True,
            download_name=f"Barcode-{clean_name}.png"
        )

    @app.before_request
    def enforce_password_change():
        """Force users flagged with must_change_password=1 to update their password before proceeding."""
        from flask_login import current_user
        if current_user and current_user.is_authenticated:
            if getattr(current_user, "must_change_password", False):
                allowed_endpoints = {"auth.change_password", "auth.logout", "static"}
                if request.endpoint and request.endpoint not in allowed_endpoints:
                    flash("Your password requires an update. Please set a new password to continue.", "warning")
                    return redirect(url_for("auth.change_password"))

    @app.after_request
    def apply_security_headers(response):
        """Single after_request hook injecting robust HTTP security headers."""
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        # HSTS only enabled when HTTPS / COOKIE_SECURE is turned on
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Prevent browser caching of sensitive authenticated pages (Back button after logout shows nothing)
        from flask_login import current_user
        if current_user and current_user.is_authenticated:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"

        # Content-Security-Policy in REPORT-ONLY mode (Safe for testing; covers CDNs & Supabase)
        csp_report_only = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://unpkg.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://*.supabase.co;"
        )
        response.headers["Content-Security-Policy-Report-Only"] = csp_report_only
        return response

    @app.context_processor
    def inject_globals():
        from datetime import datetime, timezone, timedelta
        from flask_login import current_user
        from db import query_db

        # Server-side Asia/Karachi timezone (PKT, UTC+5)
        PKT = timezone(timedelta(hours=5))
        now_pkt = datetime.now(PKT)
        today_iso = now_pkt.date().isoformat()

        res = {
            "today_karachi": today_iso,
            "now_karachi_time": now_pkt.strftime("%H:%M"),
            "unread_notification_count": 0,
            "recent_notifications": [],
            "supabase_url": app.config.get("SUPABASE_URL", ""),
            "supabase_publishable_key": app.config.get("SUPABASE_PUBLISHABLE_KEY", "")
        }

        if current_user and current_user.is_authenticated:
            try:
                unread = query_db(
                    "SELECT COUNT(*) AS c FROM notifications WHERE user_id = %s AND is_read = 0",
                    (current_user.id,), one=True
                )
                recent_notifs = query_db(
                    "SELECT * FROM notifications WHERE user_id = %s ORDER BY created_at DESC LIMIT 6",
                    (current_user.id,)
                )
                res["unread_notification_count"] = unread["c"] if unread else 0
                res["recent_notifications"] = recent_notifs or []
            except Exception as e:
                app.logger.warning("Context processor error querying notifications: %s", e)
        return res

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(mysql.connector.Error)
    def handle_database_error(e):
        """Intercept database trigger violations (SQLSTATE 45000 / Error 1644) and flash user-friendly messages."""
        sqlstate = getattr(e, "sqlstate", "")
        errno = getattr(e, "errno", None)
        msg = getattr(e, "msg", str(e))
        app.logger.error("MySQL Error [%s / %s]: %s", sqlstate, errno, msg)

        if errno == 1644 or sqlstate == "45000":
            flash(f"Validation rejected: {msg}", "danger")
            return redirect(request.referrer or url_for("auth.landing"))

        return render_template("errors/500.html"), 500

    @app.errorhandler(500)
    def server_error(e):
        app.logger.error("Internal Server Error: %s", e, exc_info=True)
        return render_template("errors/500.html"), 500

    return app


@login_manager.user_loader
def load_user(user_id):
    return User.load(int(user_id))


app = create_app()

if __name__ == "__main__":
    is_debug = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true", "yes")
    app.run(debug=is_debug, host="127.0.0.1", port=5000)
