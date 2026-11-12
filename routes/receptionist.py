import random
from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from db import query_db, execute_db, get_db_connection
from models import role_required
from forms import PaymentForm
from routes.notifications import notify_roles

receptionist_bp = Blueprint("receptionist", __name__, url_prefix="/receptionist")
PKT = timezone(timedelta(hours=5))


def _escape_like(text: str) -> str:
    """Escapes special SQL LIKE wildcard characters % and _ with backslashes."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _gen_barcode(item_id=None):
    today = datetime.now().strftime("%Y%m%d")
    if item_id is not None:
        return f"SMP-{today}-{int(item_id):05d}"
    row = query_db("SELECT MAX(sample_id) AS m FROM samples", one=True)
    nxt = (row["m"] or 0) + 1 if row else 1
    return f"SMP-{today}-{nxt:05d}"


@receptionist_bp.route("/dashboard")
@login_required
@role_required(2)
def dashboard():
    q = request.args.get("q", "").strip()
    if q:
        safe_q = f"%{_escape_like(q)}%"
        bookings = query_db(
            "SELECT b.*, u.full_name, u.phone, i.invoice_number, i.total_amount, i.payment_status "
            "FROM bookings b JOIN users u ON b.patient_id=u.user_id "
            "LEFT JOIN invoices i ON b.booking_id=i.booking_id "
            "WHERE b.booking_ref LIKE %s OR u.full_name LIKE %s OR u.phone LIKE %s "
            "ORDER BY b.created_at DESC",
            (safe_q, safe_q, safe_q)
        )
    else:
        bookings = query_db(
            "SELECT b.*, u.full_name, u.phone, i.invoice_number, i.total_amount, i.payment_status "
            "FROM bookings b JOIN users u ON b.patient_id=u.user_id "
            "LEFT JOIN invoices i ON b.booking_id=i.booking_id "
            "ORDER BY b.created_at DESC LIMIT 50"
        )
    pay_form = PaymentForm()
    return render_template("receptionist/dashboard.html", bookings=bookings, q=q, pay_form=pay_form)


@receptionist_bp.route("/booking/<int:booking_id>")
@login_required
@role_required(2)
def booking_detail(booking_id):
    booking = query_db(
        "SELECT b.*, u.full_name, u.phone, u.email, i.invoice_id, i.invoice_number, "
        "i.total_amount, i.payment_status, i.payment_method "
        "FROM bookings b JOIN users u ON b.patient_id=u.user_id "
        "LEFT JOIN invoices i ON b.booking_id=i.booking_id WHERE b.booking_id=%s",
        (booking_id,), one=True
    )
    items = query_db(
        "SELECT bi.*, lt.test_name, lt.sample_type, s.barcode_string, s.sample_id, s.collected_at "
        "FROM booking_items bi JOIN lab_tests lt ON bi.test_id=lt.test_id "
        "LEFT JOIN samples s ON bi.item_id=s.item_id WHERE bi.booking_id=%s",
        (booking_id,)
    )
    pay_form = PaymentForm()
    return render_template("receptionist/booking_detail.html", booking=booking, items=items, pay_form=pay_form)


@receptionist_bp.route("/invoice/<int:booking_id>/pay", methods=["POST"])
@login_required
@role_required(2)
def collect_payment(booking_id):
    form = PaymentForm()
    if form.validate_on_submit():
        execute_db(
            "UPDATE invoices SET payment_status='Paid', payment_method=%s, received_by=%s, paid_at=NOW() "
            "WHERE booking_id=%s AND payment_status='Unpaid'",
            (form.payment_method.data, current_user.id, booking_id)
        )
        flash("Payment collected successfully.", "success")
    return redirect(url_for("receptionist.booking_detail", booking_id=booking_id))


@receptionist_bp.route("/booking/<int:booking_id>/proceed-to-technician", methods=["POST"])
@receptionist_bp.route("/booking/<int:booking_id>/transfer-to-technician", methods=["POST"])
@login_required
@role_required(2)
def proceed_to_technician(booking_id):
    booking = query_db(
        "SELECT b.*, u.full_name, i.payment_status FROM bookings b "
        "JOIN users u ON b.patient_id = u.user_id "
        "LEFT JOIN invoices i ON b.booking_id = i.booking_id "
        "WHERE b.booking_id = %s",
        (booking_id,), one=True
    )
    if not booking:
        flash("Booking not found.", "danger")
        return redirect(url_for("receptionist.dashboard"))

    if booking["payment_status"] != "Paid":
        flash("Please collect payment before transferring patient to the Lab Technician.", "warning")
        return redirect(url_for("receptionist.booking_detail", booking_id=booking_id))

    execute_db(
        "UPDATE bookings SET booking_status = 'Confirmed' WHERE booking_id = %s AND booking_status = 'Booked'",
        (booking_id,)
    )

    notify_roles(
        [1, 3],
        "booking",
        "New Work: Patient Transferred to Lab",
        f"Receptionist {current_user.full_name} transferred patient {booking['full_name']} ({booking['booking_ref']}) to Lab Technician. Ready for sample collection.",
        booking_id
    )

    flash(f"Patient {booking['full_name']} successfully transferred to Lab Technician for sample collection.", "success")
    return redirect(url_for("receptionist.booking_detail", booking_id=booking_id))


@receptionist_bp.route("/barcode/<int:item_id>/print")
@login_required
@role_required(2)
def print_barcode(item_id):
    sample = query_db(
        "SELECT s.*, bi.item_id, lt.test_name, lt.sample_type, b.booking_ref, u.full_name, u.phone "
        "FROM samples s JOIN booking_items bi ON s.item_id=bi.item_id "
        "JOIN lab_tests lt ON bi.test_id=lt.test_id "
        "JOIN bookings b ON bi.booking_id=b.booking_id "
        "JOIN users u ON b.patient_id=u.user_id WHERE s.item_id=%s",
        (item_id,), one=True
    )
    return render_template("receptionist/barcode_print.html", sample=sample)


@receptionist_bp.route("/barcode/<barcode_string>/download")
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


@receptionist_bp.route("/tests")
@login_required
@role_required(2)
def tests():
    raw_tests = query_db(
        "SELECT lt.*, tc.category_name FROM lab_tests lt "
        "JOIN test_categories tc ON lt.category_id=tc.category_id "
        "ORDER BY tc.category_name, lt.test_name"
    )
    categories = query_db("SELECT * FROM test_categories WHERE is_active=1 ORDER BY category_name")
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
    return render_template("receptionist/tests.html", tests=raw_tests, categories=grouped_categories)


@receptionist_bp.route("/walk-in", methods=["GET", "POST"])
@login_required
@role_required(2)
def walk_in():
    tests = query_db(
        "SELECT lt.*, tc.category_name FROM lab_tests lt "
        "JOIN test_categories tc ON lt.category_id=tc.category_id ORDER BY tc.category_name ASC, lt.test_name ASC"
    )
    patients = query_db("SELECT user_id, full_name, phone, email FROM users WHERE role_id=4 AND is_active=1 ORDER BY full_name")

    if request.method == "POST":
        patient_mode = request.form.get("patient_mode", "existing")
        selected_ids = request.form.getlist("test_ids")
        appt_date = request.form.get("appointment_date")
        appt_slot = request.form.get("appointment_slot", "08:00 AM - 10:00 AM")

        if not selected_ids or not appt_date:
            flash("Appointment date and at least one diagnostic test are required.", "warning")
            return render_template("receptionist/walk_in.html", tests=tests, patients=patients)

        # Validate appointment_date against Asia/Karachi today
        today_pkt = datetime.now(PKT).date()
        try:
            booking_date = datetime.strptime(appt_date, "%Y-%m-%d").date()
            if booking_date < today_pkt:
                flash("Appointment date cannot be in the past. Please select today or a future date.", "danger")
                return render_template("receptionist/walk_in.html", tests=tests, patients=patients)
        except (ValueError, TypeError):
            flash("Invalid appointment date format.", "danger")
            return render_template("receptionist/walk_in.html", tests=tests, patients=patients)

        # Enforce max 10 customers per slot capacity limit
        slot_count_row = query_db(
            "SELECT COUNT(*) AS c FROM bookings WHERE appointment_date = %s AND appointment_slot = %s AND booking_status != 'Cancelled'",
            (appt_date, appt_slot), one=True
        )
        if slot_count_row and slot_count_row["c"] >= 10:
            flash(f"The time slot '{appt_slot}' is currently unavailable (fully booked). Please select an alternate slot.", "warning")
            return render_template("receptionist/walk_in.html", tests=tests, patients=patients)

        # Handle Patient: Existing selection or Inline New Customer Registration
        if patient_mode == "new":
            new_name = request.form.get("new_full_name", "").strip()
            new_phone = request.form.get("new_phone", "").strip()
            new_email = request.form.get("new_email", "").strip()
            new_gender = request.form.get("new_gender", "")
            new_dob = request.form.get("new_dob", "") or None
            new_address = request.form.get("new_address", "").strip()

            if not new_name or not new_phone:
                flash("Full name and phone number are required to register a new customer.", "warning")
                return render_template("receptionist/walk_in.html", tests=tests, patients=patients)

            # Check if user already exists
            existing_user = None
            if new_email:
                existing_user = query_db("SELECT user_id, full_name FROM users WHERE email = %s", (new_email,), one=True)
            if not existing_user and new_phone:
                existing_user = query_db("SELECT user_id, full_name FROM users WHERE phone = %s", (new_phone,), one=True)

            if existing_user:
                patient_id = existing_user["user_id"]
                patient_name = existing_user["full_name"]
            else:
                if not new_email:
                    clean_phone = "".join(filter(str.isdigit, new_phone)) or str(random.randint(10000, 99999))
                    new_email = f"walkin_{clean_phone}_{random.randint(100, 999)}@medlab.local"

                temp_pw = f"MedLab@{random.randint(1000, 9999)}P"
                pw_hash = generate_password_hash(temp_pw)

                conn_p = get_db_connection()
                cur_p = conn_p.cursor()
                try:
                    cur_p.execute(
                        "INSERT INTO users (role_id, full_name, phone, email, password_hash, is_active) VALUES (4, %s, %s, %s, %s, 1)",
                        (new_name, new_phone, new_email, pw_hash)
                    )
                    patient_id = cur_p.lastrowid
                    patient_name = new_name
                    cur_p.execute(
                        "INSERT INTO patient_profiles (patient_id, date_of_birth, gender, address) VALUES (%s, %s, %s, %s)",
                        (patient_id, new_dob, new_gender if new_gender else None, new_address if new_address else None)
                    )
                    conn_p.commit()
                except Exception as e:
                    conn_p.rollback()
                    flash(f"Failed to register customer: {e}", "danger")
                    return render_template("receptionist/walk_in.html", tests=tests, patients=patients)
                finally:
                    cur_p.close()
                    conn_p.close()
        else:
            patient_id = request.form.get("patient_id")
            if not patient_id:
                flash("Please select an existing patient or switch to register a new customer.", "warning")
                return render_template("receptionist/walk_in.html", tests=tests, patients=patients)
            p_row = query_db("SELECT full_name FROM users WHERE user_id = %s", (patient_id,), one=True)
            patient_name = p_row["full_name"] if p_row else "Patient"

        selected_tests = query_db(
            f"SELECT * FROM lab_tests WHERE test_id IN ({','.join(['%s']*len(selected_ids))})",
            tuple(selected_ids)
        )

        # Enforce rejection of inactive tests on backend
        inactive_tests = [t for t in selected_tests if not t.get("is_active")]
        if inactive_tests:
            names = ", ".join(t["test_name"] for t in inactive_tests)
            flash(f"Booking rejected: One or more selected tests are currently unavailable ({names}).", "danger")
            return render_template("receptionist/walk_in.html", tests=tests, patients=patients)

        total = sum(float(t["price"]) for t in selected_tests)
        booking_ref = f"BK-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"
        invoice_num = f"INV-{datetime.now().strftime('%Y%m%d')}-{random.randint(1000, 9999)}"

        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO bookings (booking_ref, patient_id, appointment_date, appointment_slot) VALUES (%s, %s, %s, %s)",
                (booking_ref, patient_id, appt_date, appt_slot)
            )
            booking_id = cur.lastrowid
            for t in selected_tests:
                cur.execute(
                    "INSERT INTO booking_items (booking_id, test_id, price_at_booking) VALUES (%s, %s, %s)",
                    (booking_id, t["test_id"], float(t["price"]))
                )
            cur.execute(
                "INSERT INTO invoices (booking_id, invoice_number, total_amount, payment_status) VALUES (%s, %s, %s, 'Unpaid')",
                (booking_id, invoice_num, total)
            )
            conn.commit()

            # Fire notifications to Admin (1) and Lab Technician (3)
            notify_roles(
                [1, 3],
                "booking",
                "New Walk-in Booking Registered",
                f"Walk-in booking registered for {patient_name} on {appt_date} ({appt_slot}). Ref: {booking_ref}",
                booking_id
            )

            flash(f"Walk-in booking created for {patient_name}! Reference: {booking_ref}", "success")
            return redirect(url_for("receptionist.booking_detail", booking_id=booking_id))
        except Exception as e:
            conn.rollback()
            flash(f"Booking failed: {e}", "danger")
        finally:
            cur.close()
            conn.close()

    return render_template("receptionist/walk_in.html", tests=tests, patients=patients)


