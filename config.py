import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

_raw_secret = os.environ.get("SECRET_KEY", "").strip()
_is_debug = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true", "yes")

if not _raw_secret or _raw_secret in ("change-me-in-production", "default_secret_key"):
    if _is_debug:
        _raw_secret = "dev-insecure-secret-key-change-in-production-only"
    else:
        raise RuntimeError(
            "CRITICAL SECURITY ERROR: SECRET_KEY environment variable is missing or set to default! "
            "Generate a key via `python -c \"import secrets; print(secrets.token_hex(32))\"` "
            "and set SECRET_KEY in your .env file."
        )

_cookie_secure = os.environ.get("COOKIE_SECURE", "0").lower() in ("1", "true", "yes")


class Config:
    SECRET_KEY = _raw_secret
    DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
    DB_PORT = int(os.environ.get("DB_PORT", 3306))
    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_NAME = os.environ.get("DB_NAME", "medlab_db")
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads", "avatars")
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 2 * 1024 * 1024))
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
    WTF_CSRF_ENABLED = True

    # Session & Cookie Security
    SESSION_COOKIE_SECURE = _cookie_secure
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_NAME = "__Host_medlab_session" if _cookie_secure else "medlab_session"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)

    # Remember-me hardening: short duration, strict flags
    REMEMBER_COOKIE_SECURE = _cookie_secure
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_DURATION = timedelta(days=1)

    # Supabase Auth
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_PUBLISHABLE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
