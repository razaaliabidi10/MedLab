"""
utils/supabase_client.py
========================
Supabase Python Client initialization and JWT verification helper.

Flask NEVER trusts browser-supplied identity. It verifies the access token
server-side via Supabase Auth and extracts uid, email, provider, and
email confirmation status directly from the verified Supabase User object.
"""

import os
from dotenv import load_dotenv
from flask import current_app
from supabase import create_client, Client

load_dotenv()


_client_instance: Client = None


def get_supabase_client() -> Client:
    """
    Returns an initialized Supabase client using configured public credentials.
    """
    global _client_instance
    if _client_instance is not None:
        return _client_instance

    url = ""
    key = ""
    try:
        url = current_app.config.get("SUPABASE_URL", "")
        key = current_app.config.get("SUPABASE_PUBLISHABLE_KEY", "")
    except Exception:
        pass

    if not url:
        url = os.environ.get("SUPABASE_URL", "")
    if not key:
        key = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")

    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY must be set in .env")

    _client_instance = create_client(url, key)
    return _client_instance


def reset_supabase_client():
    """Reset cached client (used if env vars update)."""
    global _client_instance
    _client_instance = None


def verify_supabase_token(access_token: str) -> dict:
    """
    Verifies a Supabase access token (JWT) server-side.
    Returns normalized user information dictionary if valid, or None if invalid.
    """
    if not access_token:
        return None

    try:
        client = get_supabase_client()
        # client.auth.get_user(jwt=access_token) contacts Supabase Auth API
        user_response = client.auth.get_user(jwt=access_token)
        if not user_response or not user_response.user:
            return None

        user = user_response.user

        # Extract provider from app_metadata or identities
        provider = "google"
        if hasattr(user, "app_metadata") and user.app_metadata:
            if isinstance(user.app_metadata, dict):
                provider = user.app_metadata.get("provider", "google")
            else:
                provider = getattr(user.app_metadata, "provider", "google")

        # Extract full name from user_metadata
        full_name = ""
        if hasattr(user, "user_metadata") and user.user_metadata:
            meta = user.user_metadata if isinstance(user.user_metadata, dict) else {}
            full_name = meta.get("full_name") or meta.get("name") or ""

        return {
            "uid": user.id,
            "email": (user.email or "").strip().lower(),
            "full_name": full_name.strip(),
            "provider": provider,
            "email_confirmed_at": getattr(user, "email_confirmed_at", None),
        }
    except Exception as e:
        # Invalid / expired token or network issue
        return None
