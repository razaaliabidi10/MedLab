import os
from flask import Flask, render_template
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from config import Config
from models import User

login_manager = LoginManager()
csrf = CSRFProtect()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "warning"
    csrf.init_app(app)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.receptionist import receptionist_bp
    from routes.technician import technician_bp
    from routes.patient import patient_bp
    from routes.collector import collector_bp
    from routes.pathologist import pathologist_bp
    from routes.auth_google import google_bp
    from routes.notifications import notifications_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(receptionist_bp)
    app.register_blueprint(technician_bp)
    app.register_blueprint(patient_bp)
    app.register_blueprint(collector_bp)
    app.register_blueprint(pathologist_bp)
    app.register_blueprint(google_bp)
    app.register_blueprint(notifications_bp)

    @app.context_processor
    def inject_notifications():
        from flask_login import current_user
        from db import query_db
        if current_user and current_user.is_authenticated:
            try:
                unread = query_db(
                    "SELECT COUNT(*) AS c FROM notifications WHERE user_id = %s AND is_read = 0",
                    (current_user.id,), one=True
                )
                recent_notifs = query_db(
                    "SELECT * FROM notifications WHERE user_id = %s ORDER BY created_at DESC LIMIT 5",
                    (current_user.id,)
                )
                return {
                    "unread_notification_count": unread["c"] if unread else 0,
                    "recent_notifications": recent_notifs or []
                }
            except Exception:
                pass
        return {
            "unread_notification_count": 0,
            "recent_notifications": []
        }

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("errors/500.html"), 500

    return app


@login_manager.user_loader
def load_user(user_id):
    return User.load(int(user_id))


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
