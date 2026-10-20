import os
import uuid
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, abort
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from db import query_db, execute_db
from models import User
from forms import LoginForm, SignupForm, ProfileForm, PatientProfileForm, ForgotPasswordForm

auth_bp = Blueprint("auth", __name__)

ROLE_REDIRECTS = {
    1: "admin.dashboard",
    2: "receptionist.dashboard",
    3: "technician.dashboard",
    4: "patient.dashboard",
    5: "collector.dashboard",
    6: "pathologist.dashboard"
}


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
    categories = query_db("SELECT * FROM test_categories WHERE is_active = 1 ORDER BY category_name")

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
def login():
    if current_user.is_authenticated:
        return redirect(url_for(ROLE_REDIRECTS.get(current_user.role_id, "patient.dashboard")))

    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        row = query_db(
            "SELECT u.*, r.role_name FROM users u JOIN roles r ON u.role_id=r.role_id WHERE u.email=%s",
            (email,), one=True
        )

        if row:
            # 1. Check account active status
            if not row["is_active"]:
                flash("Your account has been deactivated. Please contact lab administration.", "danger")
                return render_template("auth/login.html", form=form)

            # 2. Check login lockout (after 5 failed attempts for 10 minutes)
            lockout_until = row.get("lockout_until")
            if lockout_until and lockout_until > datetime.now():
                mins = int((lockout_until - datetime.now()).total_seconds() / 60) + 1
                flash(f"Account locked due to 5 consecutive failed login attempts. Try again in {mins} minute(s).", "danger")
                return render_template("auth/login.html", form=form)

            # 3. Check password
            if row["password_hash"] and check_password_hash(row["password_hash"], form.password.data):
                # Reset failed attempts counter on successful login
                execute_db(
                    "UPDATE users SET login_attempts = 0, lockout_until = NULL WHERE user_id = %s",
                    (row["user_id"],)
                )
                user = User(row)
                login_user(user)
                flash(f"Welcome back, {user.full_name}!", "success")
                return redirect(url_for(ROLE_REDIRECTS[user.role_id]))
            else:
                # Password incorrect -> increment login_attempts
                current_attempts = (row.get("login_attempts") or 0) + 1
                if current_attempts >= 5:
                    lockout_time = datetime.now() + timedelta(minutes=10)
                    execute_db(
                        "UPDATE users SET login_attempts = %s, lockout_until = %s WHERE user_id = %s",
                        (current_attempts, lockout_time, row["user_id"])
                    )
                    flash("Account temporarily locked for 10 minutes due to 5 failed attempts.", "danger")
                else:
                    execute_db(
                        "UPDATE users SET login_attempts = %s WHERE user_id = %s",
                        (current_attempts, row["user_id"])
                    )
                    remaining = 5 - current_attempts
                    flash(f"Invalid email or password. {remaining} attempt(s) remaining before temporary lockout.", "danger")
        else:
            flash("Invalid email or password.", "danger")

    return render_template("auth/login.html", form=form)


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
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
def signup():
    form = SignupForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        phone = form.phone.data.strip()
        if query_db("SELECT 1 FROM users WHERE email=%s", (email,), one=True):
            flash("Email already registered.", "danger")
            return render_template("auth/signup.html", form=form)
        if query_db("SELECT 1 FROM users WHERE phone=%s", (phone,), one=True):
            flash("Phone number already registered.", "danger")
            return render_template("auth/signup.html", form=form)
        hashed = generate_password_hash(form.password.data, method="pbkdf2:sha256")
        # Patients self-register (role_id=4, created_by=NULL is fine for patients)
        conn = __import__("db").get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO users (role_id, full_name, email, phone, password_hash) VALUES (4,%s,%s,%s,%s)",
                (form.full_name.data.strip(), email, phone, hashed)
            )
            new_id = cur.lastrowid
            cur.execute("INSERT INTO patient_profiles (patient_id) VALUES (%s)", (new_id,))
            conn.commit()
            flash("Account created! Please log in.", "success")
            return redirect(url_for("auth.login"))
        except Exception as e:
            conn.rollback()
            flash(f"Registration failed: {e}", "danger")
        finally:
            cur.close(); conn.close()
    return render_template("auth/signup.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


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
    if f and f.filename and allowed_file(f.filename):
        ext = f.filename.rsplit(".", 1)[1].lower()
        fname = f"{uuid.uuid4().hex}.{ext}"
        upload_dir = current_app.config["UPLOAD_FOLDER"]
        os.makedirs(upload_dir, exist_ok=True)
        f.save(os.path.join(upload_dir, fname))
        return fname
    return None
