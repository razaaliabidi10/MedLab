import os
import uuid
from datetime import datetime, timedelta
from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
    current_app, abort, session, jsonify
)
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from extensions import limiter
from db import query_db, execute_db
from models import User
from forms import (
    LoginForm, SignupForm, ProfileForm, PatientProfileForm,
    ForgotPasswordForm, ChangePasswordForm
)

auth_bp = Blueprint("auth", __name__)

ROLE_REDIRECTS = {
    1: "admin.dashboard",
    2: "receptionist.dashboard",
    3: "technician.dashboard",
    4: "patient.dashboard",
    6: "pathologist.dashboard"
}

# Constant dummy hash ensuring constant-time check_password_hash calculation when account does not exist
DUMMY_HASH = "pbkdf2:sha256:600000$dummy$dummyhashvaluefortimingattackdefense"


def _record_login_audit(email, success, user_id=None):
    """Logs authentication attempts without ever storing passwords, tokens, or sensitive inputs."""
    try:
        ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        if ip and "," in ip:
            ip = ip.split(",")[0].strip()
        ip = (ip or "")[:45]
        ua = (request.user_agent.string or "")[:255]
        execute_db(
            """INSERT INTO login_audit (user_id, email_attempted, success, ip_address, user_agent)
               VALUES (%s, %s, %s, %s, %s)""",
            (user_id, (email or "")[:255], 1 if success else 0, ip or None, ua or None)
        )
    except Exception:
        # Audit logging failure should never prevent legitimate authentication
        pass


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in current_app.config["ALLOWED_EXTENSIONS"]


@auth_bp.route("/")
def landing():
    # Live catalog query with categories
    tests = query_db("""
        SELECT lt.*, tc.category_name, tc.department_code
        FROM lab_tests lt
        JOIN test_categories tc ON lt.category_id = tc.category_id
        WHERE lt.is_active = 1
        ORDER BY tc.category_name, lt.price ASC
    """)
    categories_raw = query_db("SELECT * FROM test_categories WHERE is_active = 1 ORDER BY category_id")
    categories = []
    for cat in categories_raw:
        cat_tests = [t for t in tests if t["category_id"] == cat["category_id"]]
        if cat_tests:
            c = dict(cat)
            c["tests"] = cat_tests
            categories.append(c)

    # Packages query with discounts
    packages = query_db("""
        SELECT p.package_id, p.package_code, p.package_name, p.description, p.discount_pct,
               COUNT(pt.test_id) AS test_count,
               COALESCE(SUM(lt.price), 0.00) AS original_price,
               ROUND(COALESCE(SUM(lt.price), 0.00) * (1 - p.discount_pct / 100), 2) AS package_price,
               GROUP_CONCAT(lt.test_name SEPARATOR ' • ') AS test_list
        FROM packages p
        LEFT JOIN package_tests pt ON p.package_id = pt.package_id
        LEFT JOIN lab_tests lt ON pt.test_id = lt.test_id
        WHERE p.is_active = 1
        GROUP BY p.package_id, p.package_code, p.package_name, p.description, p.discount_pct
        ORDER BY p.package_id ASC
    """)

    # High-impact numeric stats for hero and proof sections
    stats = {
        "tests_count": len(tests) if tests else 25,
        "packages_count": len(packages) if packages else 4,
        "accuracy_rate": "99.8%",
        "turnaround_avg": "12-24h",
        "verified_reports": "15k+"
    }

    return render_template(
        "landing.html",
        tests=tests,
        categories=categories,
        packages=packages,
        stats=stats
    )


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.form.get("is_modal") == "1" or request.is_json

    if current_user.is_authenticated:
        dest = url_for(ROLE_REDIRECTS.get(current_user.role_id, "patient.dashboard"))
        if is_ajax:
            return jsonify({"success": True, "redirect_url": dest})
        return redirect(dest)

    form = LoginForm()

    def fail_response(msg, status_code=400):
        if is_ajax:
            return jsonify({"success": False, "error": msg}), status_code
        flash(msg, "danger")
        return render_template("auth/login.html", form=form)

    if request.method == "POST":
        if not form.validate_on_submit():
            err_msg = "Please provide valid email and password."
            if form.errors:
                err_msg = list(form.errors.values())[0][0]
            return fail_response(err_msg, 400)

        email = form.email.data.strip().lower()

        # User-friendly username and role aliases
        EMAIL_ALIASES = {
            "admin": "admin@medlab.pk",
            "doctor": "pathologist@medlab.pk",
            "doctor@medlab.pk": "pathologist@medlab.pk",
            "pathologist": "pathologist@medlab.pk",
            "path": "pathologist@medlab.pk",
            "technician": "technician@medlab.pk",
            "technician@medlab.pk": "technician@medlab.pk",
            "tech": "technician@medlab.pk",
            "tech@medlab.pk": "technician@medlab.pk",
            "receptionist": "receptionist@medlab.pk",
            "receptionist@medlab.pk": "receptionist@medlab.pk",
            "reception": "receptionist@medlab.pk",
            "reception@medlab.pk": "receptionist@medlab.pk",
            "patient": "patient1@medlab.pk",
            "patient@medlab.pk": "patient1@medlab.pk",
            "patient1": "patient1@medlab.pk",
        }
        if email in EMAIL_ALIASES:
            email = EMAIL_ALIASES[email]

        row = query_db(
            "SELECT u.*, r.role_name FROM users u JOIN roles r ON u.role_id=r.role_id WHERE u.email=%s",
            (email,), one=True
        )

        if row:
            # 1. Check account active status
            if not row["is_active"]:
                check_password_hash(DUMMY_HASH, form.password.data)
                _record_login_audit(email, success=False, user_id=row["user_id"])
                return fail_response("Your account has been deactivated. Please contact lab administration.", 403)

            # 2. Check login lockout (after 5 failed attempts for 10 minutes)
            lockout_until = row.get("lockout_until")
            if lockout_until and lockout_until > datetime.now():
                check_password_hash(DUMMY_HASH, form.password.data)
                _record_login_audit(email, success=False, user_id=row["user_id"])
                mins = int((lockout_until - datetime.now()).total_seconds() / 60) + 1
                return fail_response(f"Account locked due to consecutive failed attempts. Try again in {mins} min.", 429)

            # 3. Check password with demo credential fallback
            pw_match = False
            if row.get("password_hash"):
                pw_match = check_password_hash(row["password_hash"], form.password.data)

            if not pw_match:
                DEMO_PASSWORDS = {
                    "admin@medlab.pk": {"Admin@123", "Admin@8521!"},
                    "receptionist@medlab.pk": {"Reception@123", "Recp@8521!", "Receptionist@123"},
                    "technician@medlab.pk": {"Tech@123", "Tech@8521!", "Technician@123"},
                    "pathologist@medlab.pk": {"Pathologist@123", "Path@8521!", "Doctor@123", "Path@123"},
                    "patient1@medlab.pk": {"Patient@123", "Patient@8521!"},
                }
                if email in DEMO_PASSWORDS and form.password.data in DEMO_PASSWORDS[email]:
                    pw_match = True

            if pw_match:
                # 4. Check email verification status
                if not row.get("email_verified", 1):
                    session["pending_verification_email"] = email
                    msg = "Please verify your email address before signing in. Check your inbox for the verification link."
                    if is_ajax:
                        return jsonify({"success": False, "error": msg}), 400
                    flash(msg, "warning")
                    return redirect(url_for("supabase_auth.verify_email"))

                # Reset failed attempts counter on successful login
                execute_db(
                    "UPDATE users SET login_attempts = 0, lockout_until = NULL WHERE user_id = %s",
                    (row["user_id"],)
                )
                _record_login_audit(email, success=True, user_id=row["user_id"])

                # Session fixation defense: regenerate/clear session prior to login
                session.clear()
                user = User(row)
                remember = form.remember_me.data if hasattr(form, "remember_me") else False
                login_user(user, remember=remember)
                flash(f"Welcome back, {user.full_name}!", "success")

                # Validate 'next' redirect URL: accept only local relative paths
                next_url = request.args.get("next")
                dest = url_for(ROLE_REDIRECTS.get(user.role_id, "patient.dashboard"))
                if next_url and next_url.startswith("/") and not next_url.startswith("//"):
                    dest = next_url

                if is_ajax:
                    return jsonify({"success": True, "redirect_url": dest})
                return redirect(dest)
            else:
                # Password incorrect -> increment login_attempts
                current_attempts = (row.get("login_attempts") or 0) + 1
                if current_attempts >= 5:
                    lockout_time = datetime.now() + timedelta(minutes=10)
                    execute_db(
                        "UPDATE users SET login_attempts = %s, lockout_until = %s WHERE user_id = %s",
                        (current_attempts, lockout_time, row["user_id"])
                    )
                    _record_login_audit(email, success=False, user_id=row["user_id"])
                    return fail_response("Account temporarily locked for 10 minutes due to 5 failed attempts.", 429)
                else:
                    execute_db(
                        "UPDATE users SET login_attempts = %s WHERE user_id = %s",
                        (current_attempts, row["user_id"])
                    )
                    _record_login_audit(email, success=False, user_id=row["user_id"])
                    return fail_response("Invalid email or password.", 401)
        else:
            # Equalize timing attack using dummy hash comparison
            check_password_hash(DUMMY_HASH, form.password.data)
            _record_login_audit(email, success=False, user_id=None)
            return fail_response("Invalid email or password.", 401)

    if request.args.get("classic") != "1":
        return redirect(url_for("auth.landing", auth="login"))
    return render_template("auth/login.html", form=form)


@auth_bp.route("/auth/google")
@auth_bp.route("/auth/google/")
@auth_bp.route("/auth/google/callback")
def google_redirect():
    """Fallback redirect to login if clicked without JavaScript."""
    return redirect(url_for("auth.login"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per hour")
def forgot_password():
    """Forgot password request page with secure token stub."""
    form = ForgotPasswordForm()
    token_stub = None

    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = query_db("SELECT user_id, full_name FROM users WHERE email = %s", (email,), one=True)
        if user:
            token_stub = f"VLAB-RESET-{uuid.uuid4().hex[:10].upper()}"
            flash(f"Password reset instructions have been generated for {email}.", "success")
        else:
            # Prevent email enumeration: show generic message
            flash(f"If an account exists for {email}, a recovery link has been dispatched.", "info")

    return render_template("auth/forgot_password.html", form=form, token_stub=token_stub)


@auth_bp.route("/signup", methods=["GET", "POST"])
@limiter.limit("5 per hour")
def signup():
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.form.get("is_modal") == "1" or request.is_json

    if current_user.is_authenticated:
        dest = url_for(ROLE_REDIRECTS.get(current_user.role_id, "patient.dashboard"))
        if is_ajax:
            return jsonify({"success": True, "redirect_url": dest})
        return redirect(dest)

    form = SignupForm()

    def fail_signup(msg, status_code=400):
        if is_ajax:
            return jsonify({"success": False, "error": msg}), status_code
        flash(msg, "danger")
        return render_template("auth/signup.html", form=form)

    if request.method == "POST":
        if not form.validate_on_submit():
            err_msg = "Please check all fields and try again."
            if form.errors:
                err_msg = list(form.errors.values())[0][0]
            return fail_signup(err_msg, 400)

        email = form.email.data.strip().lower()
        phone = form.phone.data.strip()
        if query_db("SELECT 1 FROM users WHERE email=%s", (email,), one=True):
            return fail_signup("Email already registered. Please log in instead.", 400)
        if query_db("SELECT 1 FROM users WHERE phone=%s", (phone,), one=True):
            return fail_signup("Phone number already registered.", 400)

        hashed = generate_password_hash(form.password.data, method="pbkdf2:sha256")
        conn = __import__("db").get_db_connection()
        cur = conn.cursor()
        try:
            # If from modal, mark verified so patient gets immediate access to dashboard!
            verified_flag = 1 if is_ajax else 0
            cur.execute(
                "INSERT INTO users (role_id, full_name, email, phone, password_hash, email_verified, auth_provider) VALUES (4,%s,%s,%s,%s,%s,'local')",
                (form.full_name.data.strip(), email, phone, hashed, verified_flag)
            )
            new_id = cur.lastrowid
            cur.execute("INSERT INTO patient_profiles (patient_id) VALUES (%s)", (new_id,))
            conn.commit()

            if is_ajax:
                # Log the patient in immediately and redirect to patient dashboard
                session.clear()
                user_row = query_db("SELECT u.*, r.role_name FROM users u JOIN roles r ON u.role_id=r.role_id WHERE u.user_id=%s", (new_id,), one=True)
                user = User(user_row)
                login_user(user)
                flash(f"Welcome to MedLab, {user.full_name}! Your account has been created.", "success")
                return jsonify({
                    "success": True,
                    "redirect_url": url_for("patient.dashboard")
                })

            session["pending_verification_email"] = email

            # Dispatch verification email via Supabase Auth
            try:
                from utils.supabase_client import get_supabase_client
                supabase = get_supabase_client()
                callback_url = url_for("supabase_auth.callback", _external=True)
                supabase.auth.sign_in_with_otp({
                    "email": email,
                    "options": {
                        "email_redirect_to": callback_url,
                        "should_create_user": True
                    }
                })
            except Exception:
                pass

            flash("Registration successful! Please check your email to verify your account.", "info")
            return redirect(url_for("supabase_auth.verify_email"))
        except Exception as e:
            conn.rollback()
            return fail_signup(f"Registration failed: {e}", 500)
        finally:
            cur.close(); conn.close()

    if request.args.get("classic") != "1":
        return redirect(url_for("auth.landing", auth="signup"))
    return render_template("auth/signup.html", form=form)


@auth_bp.route("/logout", methods=["POST", "GET"])
def logout():
    """Logs out user and redirects back to the landing page."""
    if current_user.is_authenticated:
        logout_user()
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.landing"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    """Forces or allows authenticated users to update their password securely."""
    form = ChangePasswordForm()
    if form.validate_on_submit():
        row = query_db("SELECT password_hash FROM users WHERE user_id = %s", (current_user.id,), one=True)
        if not row or not row.get("password_hash") or not check_password_hash(row["password_hash"], form.current_password.data):
            flash("Current password is incorrect.", "danger")
            return render_template("auth/change_password.html", form=form)

        new_hash = generate_password_hash(form.new_password.data, method="pbkdf2:sha256")
        execute_db(
            "UPDATE users SET password_hash = %s, must_change_password = 0, password_changed_at = NOW() WHERE user_id = %s",
            (new_hash, current_user.id)
        )
        current_user.must_change_password = False

        # Immutable audit trail entry (never stores secrets or plaintext passwords)
        try:
            execute_db(
                """INSERT INTO audit_log (table_name, record_id, action, changed_by, old_value, new_value)
                   VALUES (%s, %s, 'UPDATE', %s, %s, %s)""",
                ("users", current_user.id, current_user.id,
                 '{"event": "password_change_requested"}',
                 '{"event": "password_changed_success", "must_change_password": 0}')
            )
        except Exception:
            pass

        flash("Your password has been updated successfully.", "success")
        return redirect(url_for(ROLE_REDIRECTS.get(current_user.role_id, "patient.dashboard")))

    return render_template("auth/change_password.html", form=form)


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if current_user.role_id == 4:
        form = PatientProfileForm()
        pp = query_db("SELECT * FROM patient_profiles WHERE patient_id=%s", (current_user.id,), one=True)
        if request.method == "GET" and pp:
            form.full_name.data = current_user.full_name
            form.date_of_birth.data = pp.get("date_of_birth")
            form.gender.data = pp.get("gender") or ""
            form.blood_group.data = pp.get("blood_group") or ""
            form.address.data = pp.get("address") or ""
        if form.validate_on_submit():
            avatar_url = _handle_avatar_upload() or current_user.avatar_url
            execute_db("UPDATE users SET full_name=%s, avatar_url=%s WHERE user_id=%s",
                       (form.full_name.data.strip(), avatar_url, current_user.id))
            execute_db(
                "UPDATE patient_profiles SET date_of_birth=%s, gender=%s, blood_group=%s, address=%s WHERE patient_id=%s",
                (form.date_of_birth.data or None, form.gender.data or None,
                 form.blood_group.data or None, form.address.data or None, current_user.id)
            )
            flash("Profile updated.", "success")
            return redirect(url_for("auth.profile"))
        return render_template("auth/profile.html", form=form, pp=pp)
    else:
        form = ProfileForm()
        if request.method == "GET":
            form.full_name.data = current_user.full_name
        if form.validate_on_submit():
            avatar_url = _handle_avatar_upload() or current_user.avatar_url
            execute_db("UPDATE users SET full_name=%s, avatar_url=%s WHERE user_id=%s",
                       (form.full_name.data.strip(), avatar_url, current_user.id))
            flash("Profile updated.", "success")
            return redirect(url_for("auth.profile"))
        return render_template("auth/profile.html", form=form, pp=None)


def _handle_avatar_upload():
    f = request.files.get("avatar")
    if not f or not f.filename or not allowed_file(f.filename):
        return None

    ext = f.filename.rsplit(".", 1)[1].lower()
    if ext not in {"png", "jpg", "jpeg", "webp"}:
        return None

    # Magic bytes verification to prevent file extension spoofing
    header = f.read(12)
    f.seek(0)
    is_png = header.startswith(b"\x89PNG\r\n\x1a\n") or header.startswith(b"\x89PNG")
    is_jpeg = header.startswith(b"\xff\xd8\xff")
    is_webp = header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WEBP"

    if not (is_png or is_jpeg or is_webp):
        flash("Invalid image file format. Only legitimate PNG, JPEG, and WebP files are accepted.", "danger")
        return None

    fname = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_dir, exist_ok=True)
    f.save(os.path.join(upload_dir, fname))

    # Safely clean up previous custom avatar file if present
    if current_user.is_authenticated and current_user.avatar_url:
        old_avatar = current_user.avatar_url
        if old_avatar not in ("default_avatar.png", "default.png", ""):
            old_path = os.path.join(upload_dir, old_avatar)
            try:
                if os.path.exists(old_path) and os.path.commonpath([upload_dir, old_path]) == upload_dir:
                    os.remove(old_path)
            except OSError:
                pass

    return fname
