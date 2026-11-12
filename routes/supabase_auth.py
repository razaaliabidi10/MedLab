"""
routes/supabase_auth.py
=======================
Supabase Authentication Blueprint.

Endpoints:
- GET  /auth/callback         : Browser landing page for OAuth / OTP redirects
- POST /auth/supabase-login   : Server-side token verification and account linking/creation
- GET/POST /auth/complete-profile : Mandatory phone entry for new Google OAuth users
- GET  /auth/verify-email     : "Check your email" instruction page with 60s resend
"""

import time
from datetime import datetime
from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
    session, jsonify, current_app
)
from flask_login import login_user, logout_user, current_user
from extensions import limiter
from db import query_db, execute_db, get_db_connection
from models import User
from forms import CompleteProfilePhoneForm
from utils.supabase_client import verify_supabase_token

supabase_auth_bp = Blueprint("supabase_auth", __name__, url_prefix="/auth")

ROLE_REDIRECTS = {
    1: "admin.dashboard",
    2: "receptionist.dashboard",
    3: "technician.dashboard",
    4: "patient.dashboard",
    5: "collector.dashboard",
    6: "pathologist.dashboard"
}


@supabase_auth_bp.route("/callback")
def callback():
    """
    Browser-facing OAuth/OTP callback.
    supabase-js extracts the token from URL hash (PKCE flow) and posts it
    to /auth/supabase-login via fetch.
    """
    if current_user.is_authenticated:
        dest = ROLE_REDIRECTS.get(current_user.role_id, "patient.dashboard")
        return redirect(url_for(dest))
    return render_template("auth/callback.html")


@supabase_auth_bp.route("/supabase-login", methods=["POST"])
@limiter.limit("10 per minute")
def supabase_login():
    """
    Server-side verification of Supabase access token.
    Enforces all security rules:
      - Validates JWT with Supabase Auth API
      - Checks confirmed email
      - Blocks staff accounts from Google OAuth
      - Handles email verification links (sets email_verified=1, no auto-login)
      - Links existing patients
      - Initiates phone capture session for new Google patients
    """
    data = request.get_json(silent=True) or {}
    access_token = data.get("access_token", "").strip()

    if not access_token:
        return jsonify({"success": False, "error": "Missing access token"}), 400

    verified = verify_supabase_token(access_token)
    if not verified:
        return jsonify({"success": False, "error": "Invalid or expired authentication token."}), 401

    email = verified["email"]
    uid = verified["uid"]
    provider = verified["provider"]
    email_confirmed = verified["email_confirmed_at"] is not None

    # Security Rule A: Must have confirmed email
    if not email_confirmed:
        return jsonify({
            "success": False,
            "error": "Email address has not been confirmed with identity provider."
        }), 403

    # Handle Email Verification flow (from signup OTP/magic link)
    if provider == "email":
        row = query_db(
            "SELECT u.*, r.role_name FROM users u JOIN roles r ON u.role_id=r.role_id WHERE u.email=%s",
            (email,), one=True
        )
        if row:
            execute_db(
                "UPDATE users SET email_verified = 1, supabase_uid = COALESCE(supabase_uid, %s) WHERE user_id = %s",
                (uid, row["user_id"])
            )
            flash("Email verified successfully! You may now sign in.", "success")
            return jsonify({
                "success": True,
                "action": "redirect",
                "redirect_url": url_for("auth.login")
            })
        else:
            flash("Account not found. Please register first.", "danger")
            return jsonify({
                "success": True,
                "action": "redirect",
                "redirect_url": url_for("auth.signup")
            })

    # Google OAuth Flow
    row = query_db(
        "SELECT u.*, r.role_name FROM users u JOIN roles r ON u.role_id=r.role_id WHERE u.email=%s",
        (email,), one=True
    )

    if row:
        # Security Rule B1: Staff accounts must sign in with email/password
        if row["role_id"] != 4:
            return jsonify({
                "success": False,
                "error": "Staff accounts must sign in with email and password."
            }), 403

        # Security Rule B2: Inactive accounts
        if not row["is_active"]:
            return jsonify({
                "success": False,
                "error": "Your account has been deactivated. Please contact lab administration."
            }), 403

        # Security Rule B3: Existing patient -> link account and log in
        execute_db(
            "UPDATE users SET supabase_uid = %s, email_verified = 1 WHERE user_id = %s",
            (uid, row["user_id"])
        )
        # Clear session before login
        session.clear()
        user = User(row)
        login_user(user)
        flash(f"Welcome back, {user.full_name}!", "success")
        return jsonify({
            "success": True,
            "action": "redirect",
            "redirect_url": url_for("patient.dashboard")
        })

    # Security Rule C: New Google user -> phone is mandatory and unique
    # Store verified details in signed Flask session (valid for 15 minutes)
    session["oauth_pending"] = {
        "uid": uid,
        "email": email,
        "full_name": verified["full_name"] or email.split("@")[0].title(),
        "created_at": time.time()
    }

    return jsonify({
        "success": True,
        "action": "redirect",
        "redirect_url": url_for("supabase_auth.complete_profile")
    })


@supabase_auth_bp.route("/complete-profile", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def complete_profile():
    """
    Prompts new Google users for mandatory and unique phone number.
    Only after valid phone is supplied: inserts role 4 patient in a single transaction.
    """
    if current_user.is_authenticated:
        return redirect(url_for("patient.dashboard"))

    pending = session.get("oauth_pending")
    if not pending:
        flash("Google sign-in session expired. Please try again.", "warning")
        return redirect(url_for("auth.login"))

    # Expire pending session after 15 minutes (900 seconds)
    if time.time() - pending.get("created_at", 0) > 900:
        session.pop("oauth_pending", None)
        flash("Google sign-in session expired (15 minute limit). Please try again.", "warning")
        return redirect(url_for("auth.login"))

    form = CompleteProfilePhoneForm()

    if form.validate_on_submit():
        phone = form.phone.data.strip()
        email = pending["email"]
        full_name = pending["full_name"]
        uid = pending["uid"]

        # Check phone uniqueness
        if query_db("SELECT 1 FROM users WHERE phone = %s", (phone,), one=True):
            flash("This phone number is already registered. Please provide another number.", "danger")
            return render_template("auth/complete_profile.html", form=form, email=email, name=full_name)

        conn = get_db_connection()
        cur = conn.cursor(dictionary=True)
        try:
            # Single transaction: insert user + patient_profiles
            cur.execute("""
                INSERT INTO users (role_id, full_name, email, phone, password_hash, email_verified, supabase_uid, auth_provider, is_active)
                VALUES (4, %s, %s, %s, NULL, 1, %s, 'google', 1)
            """, (full_name, email, phone, uid))
            new_id = cur.lastrowid

            cur.execute("INSERT INTO patient_profiles (patient_id) VALUES (%s)", (new_id,))
            conn.commit()

            # Retrieve created user
            cur.execute("SELECT u.*, r.role_name FROM users u JOIN roles r ON u.role_id=r.role_id WHERE u.user_id = %s", (new_id,))
            new_user_row = cur.fetchone()

            session.pop("oauth_pending", None)
            session.clear()

            user = User(new_user_row)
            login_user(user)
            flash(f"Account created successfully! Welcome to MedLab, {user.full_name}.", "success")
            return redirect(url_for("patient.dashboard"))
        except Exception as e:
            conn.rollback()
            flash(f"Account creation failed: {e}", "danger")
        finally:
            cur.close()
            conn.close()

    return render_template("auth/complete_profile.html", form=form, email=pending["email"], name=pending["full_name"])


@supabase_auth_bp.route("/verify-email")
def verify_email():
    """
    Renders 'Check your email' screen for unverified patient signups.
    """
    if current_user.is_authenticated:
        return redirect(url_for(ROLE_REDIRECTS.get(current_user.role_id, "patient.dashboard")))

    pending_email = session.get("pending_verification_email", "")
    return render_template("auth/verify_email.html", email=pending_email)
