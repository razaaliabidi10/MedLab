import random
import string
from datetime import date
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from db import query_db, execute_db, get_db_connection
from models import role_required
from forms import StaffForm, AddTestForm, AddParamForm, ToggleStaffForm

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _gen_code(prefix, table_col):
    existing = query_db(f"SELECT {table_col} FROM staff_profiles WHERE {table_col} LIKE %s", (f"{prefix}-%",))
    nums = [int(r[table_col].split("-")[1]) for r in existing if r[table_col].split("-")[1].isdigit()]
    nxt = max(nums, default=0) + 1
    return f"{prefix}-{nxt:03d}"


@admin_bp.route("/dashboard")
@login_required
@role_required(1)
def dashboard():
    kpis = {
        "total_revenue": (query_db("SELECT COALESCE(SUM(total_amount),0) AS v FROM invoices WHERE payment_status='Paid'", one=True) or {}).get("v", 0),
        "total_bookings": (query_db("SELECT COUNT(*) AS v FROM bookings", one=True) or {}).get("v", 0),
        "pending_samples": (query_db("SELECT COUNT(*) AS v FROM bookings WHERE booking_status='Booked'", one=True) or {}).get("v", 0),
        "active_staff": (query_db("SELECT COUNT(*) AS v FROM users WHERE role_id IN (2,3) AND is_active=1", one=True) or {}).get("v", 0),
    }
    recent = query_db(
        "SELECT b.booking_ref, u.full_name, b.appointment_date, b.booking_status, i.total_amount, i.payment_status "
        "FROM bookings b JOIN users u ON b.patient_id=u.user_id "
        "LEFT JOIN invoices i ON b.booking_id=i.booking_id ORDER BY b.created_at DESC LIMIT 10"
    )
    return render_template("admin/dashboard.html", kpis=kpis, recent=recent)


@admin_bp.route("/staff")
@login_required
@role_required(1)
def staff():
    staff_list = query_db("SELECT * FROM vw_staff_directory ORDER BY created_at DESC")
    tech_form = StaffForm(prefix="tech")
    recp_form = StaffForm(prefix="recp")
    toggle_form = ToggleStaffForm()
    categories = query_db("SELECT * FROM test_categories")
    return render_template("admin/staff.html", staff_list=staff_list,
                           tech_form=tech_form, recp_form=recp_form, toggle_form=toggle_form)


@admin_bp.route("/staff/add-technician", methods=["POST"])
@login_required
@role_required(1)
def add_technician():
    form = StaffForm(prefix="tech")
    if form.validate_on_submit():
        _onboard_staff(form, role_id=3, prefix="TECH")
    else:
        for field, errs in form.errors.items():
            flash(f"{field}: {', '.join(errs)}", "danger")
    return redirect(url_for("admin.staff"))


@admin_bp.route("/staff/add-receptionist", methods=["POST"])
@login_required
@role_required(1)
def add_receptionist():
    form = StaffForm(prefix="recp")
    if form.validate_on_submit():
        _onboard_staff(form, role_id=2, prefix="RECP")
    else:
        for field, errs in form.errors.items():
            flash(f"{field}: {', '.join(errs)}", "danger")
    return redirect(url_for("admin.staff"))


def _onboard_staff(form, role_id, prefix):
    email = form.email.data.strip().lower()
    phone = form.phone.data.strip()
    if query_db("SELECT 1 FROM users WHERE email=%s", (email,), one=True):
        flash("Email already exists.", "danger"); return
    if query_db("SELECT 1 FROM users WHERE phone=%s", (phone,), one=True):
        flash("Phone already exists.", "danger"); return
    hashed = generate_password_hash(form.password.data, method="pbkdf2:sha256")
    emp_code = _gen_code(prefix, "employee_code")
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users (role_id,full_name,email,phone,password_hash,created_by) VALUES (%s,%s,%s,%s,%s,%s)",
            (role_id, form.full_name.data.strip(), email, phone, hashed, current_user.id)
        )
        new_id = cur.lastrowid
        cur.execute(
            "INSERT INTO staff_profiles (staff_id,employee_code,qualification,shift_timing,joining_date) VALUES (%s,%s,%s,%s,%s)",
            (new_id, emp_code, form.qualification.data.strip(), form.shift_timing.data, form.joining_date.data)
        )
        conn.commit()
        role_label = "Lab Technician" if role_id == 3 else "Receptionist"
        flash(f"{role_label} '{form.full_name.data}' onboarded successfully (Code: {emp_code}).", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Onboarding failed: {e}", "danger")
    finally:
        cur.close(); conn.close()


@admin_bp.route("/staff/toggle-active", methods=["POST"])
@login_required
@role_required(1)
def toggle_active():
    user_id = request.form.get("user_id")
    row = query_db("SELECT is_active FROM users WHERE user_id=%s AND role_id IN (2,3)", (user_id,), one=True)
    if row:
        new_state = 0 if row["is_active"] else 1
        execute_db("UPDATE users SET is_active=%s WHERE user_id=%s", (new_state, user_id))
        flash(f"Account {'activated' if new_state else 'suspended'}.", "success")
    return redirect(url_for("admin.staff"))


@admin_bp.route("/catalog")
@login_required
@role_required(1)
def catalog():
    tests = query_db(
        "SELECT lt.*, tc.category_name FROM lab_tests lt "
        "JOIN test_categories tc ON lt.category_id=tc.category_id ORDER BY tc.category_name, lt.test_name"
    )
    params = query_db(
        "SELECT tp.*, lt.test_name FROM test_parameters tp "
        "JOIN lab_tests lt ON tp.test_id=lt.test_id ORDER BY lt.test_name, tp.display_order"
    )
    categories = query_db("SELECT * FROM test_categories WHERE is_active=1")
    all_tests = query_db("SELECT test_id, test_name FROM lab_tests ORDER BY test_name")
    test_form = AddTestForm()
    test_form.category_id.choices = [(c["category_id"], c["category_name"]) for c in categories]
    param_form = AddParamForm()
    param_form.test_id.choices = [(t["test_id"], t["test_name"]) for t in all_tests]
    return render_template("admin/catalog.html", tests=tests, params=params,
                           test_form=test_form, param_form=param_form)


@admin_bp.route("/catalog/add-test", methods=["POST"])
@login_required
@role_required(1)
def add_test():
    categories = query_db("SELECT * FROM test_categories WHERE is_active=1")
    form = AddTestForm()
    form.category_id.choices = [(c["category_id"], c["category_name"]) for c in categories]
    if form.validate_on_submit():
        execute_db(
            "INSERT INTO lab_tests (category_id,test_code,test_name,sample_type,price,turnaround_hours,pre_test_instructions) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (form.category_id.data, form.test_code.data.strip().upper(), form.test_name.data.strip(),
             form.sample_type.data, float(form.price.data), int(form.turnaround_hours.data),
             form.pre_test_instructions.data or "No special preparation required.")
        )
        flash("Lab test added.", "success")
    else:
        for field, errs in form.errors.items():
            flash(f"{field}: {', '.join(errs)}", "danger")
    return redirect(url_for("admin.catalog"))


@admin_bp.route("/catalog/add-param", methods=["POST"])
@login_required
@role_required(1)
def add_param():
    all_tests = query_db("SELECT test_id, test_name FROM lab_tests ORDER BY test_name")
    form = AddParamForm()
    form.test_id.choices = [(t["test_id"], t["test_name"]) for t in all_tests]
    if form.validate_on_submit():
        execute_db(
            "INSERT INTO test_parameters (test_id,param_name,unit,min_range,max_range,display_order) VALUES (%s,%s,%s,%s,%s,%s)",
            (form.test_id.data, form.param_name.data.strip(), form.unit.data.strip(),
             float(form.min_range.data), float(form.max_range.data), int(form.display_order.data or 1))
        )
        flash("Biomarker parameter added.", "success")
    else:
        for field, errs in form.errors.items():
            flash(f"{field}: {', '.join(errs)}", "danger")
    return redirect(url_for("admin.catalog"))
