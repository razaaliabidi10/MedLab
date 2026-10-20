"""
routes/auth_google.py
======================
Google OAuth / Supabase Authentication Stub.

This module provides the integration bridge for Google OAuth.
Database schema is already pre-configured:
  - users.password_hash is NULLABLE (for OAuth users who do not have a local password)
  - users.auth_provider is ENUM('local', 'google')
  - users.google_id is VARCHAR(120) UNIQUE NULL

Once Google Client ID or Supabase credentials are configured in .env:
  1. User clicks "Continue with Google" -> /auth/google
  2. Redirects to Google consent screen or Supabase OAuth URL
  3. Callback route /auth/google/callback extracts:
       sub / google_id, email, full_name, avatar_url
  4. Upserts user in medlab_db with role_id = 4 (patient) and auth_provider = 'google'
  5. Calls login_user(user) and redirects to patient dashboard
"""

import os
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, current_user
from db import query_db, get_db_connection
from models import User

google_bp = Blueprint("google_auth", __name__, url_prefix="/auth/google")

# Supabase / Google OAuth config flags
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")


@google_bp.route("/")
def google_redirect():
    """
    Entry point for 'Continue with Google'.
    When credentials are not yet set in .env, displays a clean placeholder page.
    """
    if current_user.is_authenticated:
        from routes.auth import ROLE_REDIRECTS
        return redirect(url_for(ROLE_REDIRECTS.get(current_user.role_id, "patient.dashboard")))

    # If OAuth is not configured yet, show the friendly setup/coming soon page
    if not GOOGLE_CLIENT_ID and not SUPABASE_URL:
        return render_template("auth/google_stub.html")

    # Production integration example (Supabase or direct Google OAuth):
    # redirect_uri = url_for('google_auth.google_callback', _external=True)
    # return redirect(f"https://accounts.google.com/o/oauth2/v2/auth?client_id={GOOGLE_CLIENT_ID}&...")
    return render_template("auth/google_stub.html")


@google_bp.route("/callback")
def google_callback():
    """
    OAuth callback route. Documented for future plug-in.
    """
    flash("Google sign-in is coming soon! Please use email and password to log in.", "info")
    return redirect(url_for("auth.login"))
