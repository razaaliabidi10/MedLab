import json
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
    ALLOWED_COLS = {"employee_code"}
    if table_col not in ALLOWED_COLS:
        raise ValueError(f"Unauthorized column name: {table_col}")
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
        "pending_samples": (query_db("SELECT COUNT(*) AS v FROM bookings WHERE booking_status IN ('Booked', 'Confirmed')", one=True) or {}).get("v", 0),
        "active_staff": (query_db("SELECT COUNT(*) AS v FROM users WHERE role_id IN (2,3,6) AND is_active=1", one=True) or {}).get("v", 0),
    }
    recent = query_db(
        "SELECT b.booking_id, b.booking_ref, u.full_name, u.phone, b.appointment_date, b.appointment_slot, b.booking_status, "
        "i.total_amount, i.payment_status, "
        "GROUP_CONCAT(DISTINCT lt.test_name SEPARATOR ', ') AS test_names, "
        "COUNT(DISTINCT bi.item_id) AS total_tests, "
        "MAX(s.barcode_string) AS barcode_string, "
        "b.released_at, "
        "u_path.full_name AS pathologist_name "
        "FROM bookings b JOIN users u ON b.patient_id=u.user_id "
        "LEFT JOIN booking_items bi ON b.booking_id=bi.booking_id "
        "LEFT JOIN lab_tests lt ON bi.test_id=lt.test_id "
        "LEFT JOIN samples s ON bi.item_id=s.item_id "
        "LEFT JOIN users u_path ON b.released_by=u_path.user_id "
        "LEFT JOIN invoices i ON b.booking_id=i.booking_id "
        "GROUP BY b.booking_id, u.user_id, i.invoice_id ORDER BY b.created_at DESC LIMIT 50"
    )
    return render_template("admin/dashboard.html", kpis=kpis, recent=recent)


@admin_bp.route("/staff")
@login_required
@role_required(1)
def staff():
    staff_list = query_db("SELECT * FROM vw_staff_directory ORDER BY created_at DESC")
    tech_form = StaffForm(prefix="tech")
    recp_form = StaffForm(prefix="recp")
    path_form = StaffForm(prefix="path")
    toggle_form = ToggleStaffForm()
    categories = query_db("SELECT * FROM test_categories")
    staff_dict = {
        int(s["user_id"]): {
            "id": int(s["user_id"]),
            "name": str(s["full_name"]),
            "email": str(s["email"]),
            "phone": str(s["phone"] or ""),
            "qualification": str(s["qualification"] or ""),
            "shift": str(s["shift_timing"] or "Morning"),
        }
        for s in staff_list
    }
    return render_template("admin/staff.html", staff_list=staff_list,
                           tech_form=tech_form, recp_form=recp_form, path_form=path_form, toggle_form=toggle_form,
                           staff_json=json.dumps(staff_dict))


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


@admin_bp.route("/staff/add-pathologist", methods=["POST"])
@login_required
@role_required(1)
def add_pathologist():
    form = StaffForm(prefix="path")
    if form.validate_on_submit():
        _onboard_staff(form, role_id=6, prefix="PATH")
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
            "INSERT INTO users (role_id,full_name,email,phone,password_hash,created_by,must_change_password) VALUES (%s,%s,%s,%s,%s,%s,1)",
            (role_id, form.full_name.data.strip(), email, phone, hashed, current_user.id)
        )
        new_id = cur.lastrowid
        cur.execute(
            "INSERT INTO staff_profiles (staff_id,employee_code,qualification,shift_timing,joining_date) VALUES (%s,%s,%s,%s,%s)",
            (new_id, emp_code, form.qualification.data.strip(), form.shift_timing.data, form.joining_date.data)
        )
        # Log staff creation to audit_log (never log passwords)
        cur.execute(
            """INSERT INTO audit_log (table_name, record_id, action, changed_by, old_value, new_value)
               VALUES ('users', %s, 'INSERT', %s, NULL, %s)""",
            (new_id, current_user.id,
             f'{{"event": "staff_onboarded", "role_id": {role_id}, "email": "{email}", "employee_code": "{emp_code}"}}')
        )
        conn.commit()
        if role_id == 3:
            role_label = "Lab Technician"
        elif role_id == 6:
            role_label = "Pathologist"
        elif role_id == 5:
            role_label = "Sample Collector"
        else:
            role_label = "Receptionist"
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
    if not user_id:
        flash("Invalid user ID specified.", "danger")
        return redirect(url_for("admin.staff"))

    # Defense: Prevent admin from suspending their own active session
    if str(user_id) == str(current_user.id):
        flash("You cannot suspend your own administrative account.", "danger")
        return redirect(url_for("admin.staff"))

    target = query_db("SELECT user_id, role_id, is_active FROM users WHERE user_id=%s AND role_id IN (1,2,3,5,6)", (user_id,), one=True)
    if not target:
        flash("Staff member not found.", "danger")
        return redirect(url_for("admin.staff"))

    # Defense: Prevent suspending the last remaining active administrator
    if target["role_id"] == 1 and target["is_active"]:
        active_admins = query_db("SELECT COUNT(*) AS c FROM users WHERE role_id=1 AND is_active=1", one=True)
        if active_admins and active_admins["c"] <= 1:
            flash("Cannot suspend the only remaining active administrator.", "danger")
            return redirect(url_for("admin.staff"))

    new_state = 0 if target["is_active"] else 1
    execute_db("UPDATE users SET is_active=%s WHERE user_id=%s", (new_state, user_id))
    action_label = "suspended" if new_state == 0 else "reactivated"

    try:
        execute_db(
            """INSERT INTO audit_log (table_name, record_id, action, changed_by, old_value, new_value)
               VALUES ('users', %s, 'UPDATE', %s, %s, %s)""",
            (user_id, current_user.id,
             f'{{"is_active": {target["is_active"]}}}',
             f'{{"is_active": {new_state}, "action": "{action_label}"}}')
        )
    except Exception:
        pass

    flash(f"Account {action_label}.", "success")
    return redirect(url_for("admin.staff"))


@admin_bp.route("/staff/edit/<int:user_id>", methods=["POST"])
@login_required
@role_required(1)
def edit_staff(user_id):
    staff_member = query_db("SELECT * FROM users WHERE user_id=%s AND role_id IN (2,3,6)", (user_id,), one=True)
    if not staff_member:
        flash("Staff member not found.", "danger")
        return redirect(url_for("admin.staff"))

    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    phone = request.form.get("phone", "").strip()
    qualification = request.form.get("qualification", "").strip()
    shift_timing = request.form.get("shift_timing", "Morning")
    new_password = request.form.get("new_password", "").strip()

    if not full_name or not email or not phone:
        flash("Full name, email, and phone are required.", "danger")
        return redirect(url_for("admin.staff"))

    # Check email uniqueness
    dup_email = query_db("SELECT user_id FROM users WHERE email=%s AND user_id!=%s", (email, user_id), one=True)
    if dup_email:
        flash("Email address is already in use by another account.", "danger")
        return redirect(url_for("admin.staff"))

    # Check phone uniqueness
    dup_phone = query_db("SELECT user_id FROM users WHERE phone=%s AND user_id!=%s", (phone, user_id), one=True)
    if dup_phone:
        flash("Phone number is already in use by another account.", "danger")
        return redirect(url_for("admin.staff"))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        if new_password:
            hashed = generate_password_hash(new_password, method="pbkdf2:sha256")
            cur.execute(
                "UPDATE users SET full_name=%s, email=%s, phone=%s, password_hash=%s WHERE user_id=%s",
                (full_name, email, phone, hashed, user_id)
            )
        else:
            cur.execute(
                "UPDATE users SET full_name=%s, email=%s, phone=%s WHERE user_id=%s",
                (full_name, email, phone, user_id)
            )

        cur.execute(
            "UPDATE staff_profiles SET qualification=%s, shift_timing=%s WHERE staff_id=%s",
            (qualification, shift_timing, user_id)
        )
        conn.commit()
        flash(f"Staff details for '{full_name}' updated successfully.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Failed to update staff: {e}", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("admin.staff"))


@admin_bp.route("/users")
@login_required
@role_required(1)
def users():
    q = request.args.get("q", "").strip()
    if q:
        safe_q = f"%{q}%"
        patient_list = query_db(
            """
            SELECT u.user_id, u.full_name, u.email, u.phone, u.avatar_url, u.is_active, u.created_at,
                   pp.date_of_birth, pp.gender, pp.blood_group, pp.address,
                   COUNT(DISTINCT b.booking_id) AS total_bookings,
                   COALESCE(SUM(CASE WHEN i.payment_status = 'Paid' THEN i.total_amount ELSE 0 END), 0) AS total_spent
            FROM users u
            LEFT JOIN patient_profiles pp ON u.user_id = pp.patient_id
            LEFT JOIN bookings b ON u.user_id = b.patient_id
            LEFT JOIN invoices i ON b.booking_id = i.booking_id
            WHERE u.role_id = 4 AND (u.full_name LIKE %s OR u.email LIKE %s OR u.phone LIKE %s)
            GROUP BY u.user_id, pp.patient_id
            ORDER BY u.created_at DESC
            """,
            (safe_q, safe_q, safe_q)
        )
    else:
        patient_list = query_db(
            """
            SELECT u.user_id, u.full_name, u.email, u.phone, u.avatar_url, u.is_active, u.created_at,
                   pp.date_of_birth, pp.gender, pp.blood_group, pp.address,
                   COUNT(DISTINCT b.booking_id) AS total_bookings,
                   COALESCE(SUM(CASE WHEN i.payment_status = 'Paid' THEN i.total_amount ELSE 0 END), 0) AS total_spent
            FROM users u
            LEFT JOIN patient_profiles pp ON u.user_id = pp.patient_id
            LEFT JOIN bookings b ON u.user_id = b.patient_id
            LEFT JOIN invoices i ON b.booking_id = i.booking_id
            WHERE u.role_id = 4
            GROUP BY u.user_id, pp.patient_id
            ORDER BY u.created_at DESC
            """
        )
    users_dict = {
        int(p["user_id"]): {
            "id": int(p["user_id"]),
            "name": str(p["full_name"]),
            "email": str(p["email"]),
            "phone": str(p["phone"] or ""),
            "gender": str(p["gender"] or ""),
            "blood_group": str(p["blood_group"] or ""),
            "address": str(p["address"] or ""),
            "is_active": int(p["is_active"]),
        }
        for p in patient_list
    }
    return render_template("admin/users.html", patient_list=patient_list, q=q, users_json=json.dumps(users_dict))


@admin_bp.route("/users/delete/<int:user_id>", methods=["POST"])
@login_required
@role_required(1)
def delete_user(user_id):
    """Permanently delete a patient user and all their associated data."""
    patient = query_db("SELECT user_id, full_name FROM users WHERE user_id=%s AND role_id=4", (user_id,), one=True)
    if not patient:
        flash("Patient user not found.", "danger")
        return redirect(url_for("admin.users"))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Cascade delete: notifications, booking items, samples, test_results, invoices, bookings, patient_profile, user
        cur.execute("DELETE FROM notifications WHERE user_id=%s", (user_id,))
        # Get booking IDs first
        booking_ids = query_db("SELECT booking_id FROM bookings WHERE patient_id=%s", (user_id,))
        for bk in (booking_ids or []):
            bid = bk["booking_id"]
            cur.execute("DELETE FROM test_results WHERE item_id IN (SELECT item_id FROM booking_items WHERE booking_id=%s)", (bid,))
            cur.execute("DELETE FROM samples WHERE item_id IN (SELECT item_id FROM booking_items WHERE booking_id=%s)", (bid,))
            cur.execute("DELETE FROM booking_items WHERE booking_id=%s", (bid,))
            cur.execute("DELETE FROM invoices WHERE booking_id=%s", (bid,))
        cur.execute("DELETE FROM bookings WHERE patient_id=%s", (user_id,))
        cur.execute("DELETE FROM patient_profiles WHERE patient_id=%s", (user_id,))
        cur.execute("DELETE FROM users WHERE user_id=%s AND role_id=4", (user_id,))
        conn.commit()
        flash(f"Patient '{patient['full_name']}' and all their data have been permanently deleted.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Failed to delete user: {e}", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("admin.users"))


@admin_bp.route("/users/toggle/<int:user_id>", methods=["POST"])
@login_required
@role_required(1)
def toggle_user(user_id):
    patient = query_db("SELECT user_id, is_active, full_name FROM users WHERE user_id=%s AND role_id=4", (user_id,), one=True)
    if not patient:
        flash("Patient user not found.", "danger")
        return redirect(url_for("admin.users"))

    new_state = 0 if patient["is_active"] else 1
    execute_db("UPDATE users SET is_active=%s WHERE user_id=%s", (new_state, user_id))
    label = "suspended" if new_state == 0 else "reactivated"
    flash(f"Patient '{patient['full_name']}' has been {label}.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/edit/<int:user_id>", methods=["POST"])
@login_required
@role_required(1)
def edit_user(user_id):
    patient = query_db("SELECT * FROM users WHERE user_id=%s AND role_id=4", (user_id,), one=True)
    if not patient:
        flash("Patient not found.", "danger")
        return redirect(url_for("admin.users"))

    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    phone = request.form.get("phone", "").strip()
    gender = request.form.get("gender", "")
    blood_group = request.form.get("blood_group", "")
    address = request.form.get("address", "").strip()
    new_password = request.form.get("new_password", "").strip()
    is_active_val = request.form.get("is_active")

    if not full_name or not email or not phone:
        flash("Full name, email, and phone are required.", "danger")
        return redirect(url_for("admin.users"))

    dup_email = query_db("SELECT user_id FROM users WHERE email=%s AND user_id!=%s", (email, user_id), one=True)
    if dup_email:
        flash("Email address is already in use.", "danger")
        return redirect(url_for("admin.users"))

    dup_phone = query_db("SELECT user_id FROM users WHERE phone=%s AND user_id!=%s", (phone, user_id), one=True)
    if dup_phone:
        flash("Phone number is already in use.", "danger")
        return redirect(url_for("admin.users"))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        new_active = int(is_active_val) if is_active_val is not None else patient["is_active"]
        if new_password:
            hashed = generate_password_hash(new_password, method="pbkdf2:sha256")
            cur.execute(
                "UPDATE users SET full_name=%s, email=%s, phone=%s, password_hash=%s, is_active=%s WHERE user_id=%s",
                (full_name, email, phone, hashed, new_active, user_id)
            )
        else:
            cur.execute(
                "UPDATE users SET full_name=%s, email=%s, phone=%s, is_active=%s WHERE user_id=%s",
                (full_name, email, phone, new_active, user_id)
            )

        # Update or insert patient profile
        profile = query_db("SELECT patient_id FROM patient_profiles WHERE patient_id=%s", (user_id,), one=True)
        if profile:
            cur.execute(
                "UPDATE patient_profiles SET gender=%s, blood_group=%s, address=%s WHERE patient_id=%s",
                (gender or None, blood_group or None, address or None, user_id)
            )
        else:
            cur.execute(
                "INSERT INTO patient_profiles (patient_id, gender, blood_group, address) VALUES (%s, %s, %s, %s)",
                (user_id, gender or None, blood_group or None, address or None)
            )
        conn.commit()
        status_note = " (suspended)" if new_active == 0 else ""
        flash(f"Patient profile for '{full_name}' updated successfully{status_note}.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Update failed: {e}", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("admin.users"))


@admin_bp.route("/catalog/edit-test/<int:test_id>", methods=["POST"])
@login_required
@role_required(1)
def edit_test(test_id):
    test = query_db("SELECT * FROM lab_tests WHERE test_id=%s", (test_id,), one=True)
    if not test:
        flash("Test not found.", "danger")
        return redirect(url_for("admin.catalog"))

    price = request.form.get("price", "").strip()
    tat = request.form.get("turnaround_hours", "").strip()
    instructions = request.form.get("pre_test_instructions", "").strip()
    is_active = 1 if request.form.get("is_active") == "1" else 0

    try:
        p_val = float(price)
        t_val = int(tat) if tat else test["turnaround_hours"]
        execute_db(
            "UPDATE lab_tests SET price=%s, turnaround_hours=%s, pre_test_instructions=%s, is_active=%s WHERE test_id=%s",
            (p_val, t_val, instructions or test["pre_test_instructions"], is_active, test_id)
        )
        flash(f"Test '{test['test_name']}' updated successfully. New Price: PKR {p_val:,.0f}.", "success")
    except ValueError:
        flash("Invalid price or turnaround time value.", "danger")

    return redirect(url_for("admin.catalog"))


@admin_bp.route("/catalog")
@login_required
@role_required(1)
def catalog():
    raw_tests = query_db(
        "SELECT lt.*, tc.category_name, COUNT(tp.param_id) AS param_count FROM lab_tests lt "
        "JOIN test_categories tc ON lt.category_id=tc.category_id "
        "LEFT JOIN test_parameters tp ON lt.test_id=tp.test_id "
        "GROUP BY lt.test_id, tc.category_name ORDER BY tc.category_name, lt.test_name"
    )
    params = query_db(
        "SELECT tp.*, lt.test_name FROM test_parameters tp "
        "JOIN lab_tests lt ON tp.test_id=lt.test_id ORDER BY lt.test_name, tp.display_order"
    )
    categories = query_db("SELECT * FROM test_categories WHERE is_active=1 ORDER BY category_name")
    
    # Group tests by category for accordions
    cats_dict = {}
    for t in raw_tests:
        c_name = t["category_name"]
        if c_name not in cats_dict:
            cats_dict[c_name] = {"category_id": t["category_id"], "category_name": c_name, "tests": []}
        cats_dict[c_name]["tests"].append(t)
    for c in categories:
        if c["category_name"] not in cats_dict:
            cats_dict[c["category_name"]] = {"category_id": c["category_id"], "category_name": c["category_name"], "tests": []}
    grouped_categories = list(cats_dict.values())

    all_tests = query_db("SELECT test_id, test_name FROM lab_tests ORDER BY test_name")
    test_form = AddTestForm()
    test_form.category_id.choices = [(c["category_id"], c["category_name"]) for c in categories]
    param_form = AddParamForm()
    param_form.test_id.choices = [(t["test_id"], t["test_name"]) for t in all_tests]
    return render_template("admin/catalog.html", tests=raw_tests, categories=grouped_categories,
                           params=params, test_form=test_form, param_form=param_form)


@admin_bp.route("/catalog/toggle-test/<int:test_id>", methods=["POST"])
@login_required
@role_required(1)
def toggle_test(test_id):
    test = query_db("SELECT test_id, test_name, is_active FROM lab_tests WHERE test_id=%s", (test_id,), one=True)
    if not test:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
            return {"success": False, "error": "Test not found"}, 404
        flash("Test not found.", "danger")
        return redirect(url_for("admin.catalog"))
    new_state = 0 if test["is_active"] else 1
    execute_db("UPDATE lab_tests SET is_active=%s WHERE test_id=%s", (new_state, test_id))
    status_str = "activated" if new_state else "disabled"
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
        return {"success": True, "test_id": test_id, "is_active": new_state, "status": status_str}
    flash(f"Test '{test['test_name']}' {status_str}.", "success")
    return redirect(url_for("admin.catalog"))


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


@admin_bp.route("/barcode/<barcode_string>/download")
@login_required
def download_barcode_image(barcode_string):
    import io, re
    from flask import send_file
    from utils.barcode_generator import generate_barcode_png
    png_bytes = generate_barcode_png(barcode_string)
    clean_name = re.sub(r'[^A-Za-z0-9\-_.]', '', str(barcode_string))
    return send_file(
        io.BytesIO(png_bytes),
        mimetype="image/png",
        as_attachment=True,
        download_name=f"Barcode-{clean_name}.png"
    )
