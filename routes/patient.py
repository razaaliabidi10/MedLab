import io
import json
from datetime import datetime, timezone, timedelta, time
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify, send_file
from flask_login import login_required, current_user
from db import query_db, execute_db, get_db_connection
from models import role_required
from forms import BookTestForm
from routes.notifications import notify_roles
from utils.pdf_generator import generate_diagnostic_report_pdf

patient_bp = Blueprint("patient", __name__, url_prefix="/patient")

PKT = timezone(timedelta(hours=5))
SLOT_START_TIMES = {
    "08:00 AM - 10:00 AM": time(8, 0),
    "10:00 AM - 12:00 PM": time(10, 0),
    "02:00 PM - 04:00 PM": time(14, 0),
    "04:00 PM - 06:00 PM": time(16, 0),
}


def _gen_booking_ref():
    today = datetime.now().strftime("%Y%m%d")
    existing = query_db("SELECT booking_ref FROM bookings WHERE booking_ref LIKE %s", (f"BK-{today}-%",))
    nxt = len(existing) + 1
    return f"BK-{today}-{nxt:04d}"


def _gen_invoice_num():
    today = datetime.now().strftime("%Y%m%d")
    existing = query_db("SELECT invoice_number FROM invoices WHERE invoice_number LIKE %s", (f"INV-{today}-%",))
    nxt = len(existing) + 1
    return f"INV-{today}-{nxt:04d}"


@patient_bp.route("/dashboard")
@login_required
@role_required(4)
def dashboard():
    bookings = query_db(
        "SELECT b.*, i.invoice_number, i.total_amount, i.payment_status "
        "FROM bookings b LEFT JOIN invoices i ON b.booking_id=i.booking_id "
        "WHERE b.patient_id=%s ORDER BY b.created_at DESC",
        (current_user.id,)
    )

    # Highlighted unviewed ready reports
    ready_reports = query_db("""
        SELECT b.booking_id, b.booking_ref, b.appointment_date, b.appointment_slot,
               b.released_at, u_path.full_name AS pathologist_name,
               GROUP_CONCAT(lt.test_name SEPARATOR ', ') AS test_names
        FROM bookings b
        JOIN booking_items bi ON b.booking_id = bi.booking_id
        JOIN lab_tests lt ON bi.test_id = lt.test_id
        LEFT JOIN users u_path ON b.released_by = u_path.user_id
        WHERE b.patient_id = %s
          AND b.booking_status = 'Completed'
          AND b.released_at IS NOT NULL
          AND b.patient_viewed_at IS NULL
        GROUP BY b.booking_id, b.booking_ref, b.appointment_date, b.appointment_slot,
                 b.released_at, u_path.full_name
        ORDER BY b.released_at DESC
    """, (current_user.id,))

    return render_template("patient/dashboard.html", bookings=bookings, ready_reports=ready_reports)


def check_slot_available(query_date, slot_label, now_pkt=None):
    """Calculates slot availability based on past time, capacity limit (10 max), and lab scheduling."""
    if now_pkt is None:
        now_pkt = datetime.now(PKT)
    today_pkt = now_pkt.date()
    start_t = SLOT_START_TIMES.get(slot_label, time(0, 0))

    is_past = (query_date == today_pkt and now_pkt.time() >= start_t) or (query_date < today_pkt)
    if is_past:
        return False, "Unavailable"

    count_row = query_db(
        "SELECT COUNT(*) AS c FROM bookings WHERE appointment_date = %s AND appointment_slot = %s AND booking_status != 'Cancelled'",
        (query_date, slot_label), one=True
    )
    booked = count_row["c"] if count_row else 0
    if booked >= 10:
        return False, "Unavailable"

    # Lab scheduling capacity: dynamically marks 1-2 slots unavailable per day
    slot_keys = list(SLOT_START_TIMES.keys())
    if slot_label in slot_keys:
        slot_idx = slot_keys.index(slot_label)
        unavail_indices = {query_date.day % 4, (query_date.day + 1) % 4} if query_date.day % 2 == 0 else {query_date.day % 4}
        if slot_idx in unavail_indices:
            return False, "Unavailable"

    return True, "Available"


@patient_bp.route("/api/slot-availability")
@login_required
def slot_availability():
    """Returns slot availability without exposing internal booking counts."""
    date_str = request.args.get("date", "").strip()
    now_pkt = datetime.now(PKT)
    today_pkt = now_pkt.date()

    try:
        query_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        query_date = today_pkt

    slots_status = {}
    for slot_label in SLOT_START_TIMES.keys():
        is_avail, label = check_slot_available(query_date, slot_label, now_pkt)
        slots_status[slot_label] = {"available": is_avail, "status_label": label}

    return jsonify(slots_status)


def _render_book_test(form, tests):
    categories = sorted(list({t["category_name"] for t in tests}))
    tests_data = {
        int(t["test_id"]): {
            "id": int(t["test_id"]),
            "name": str(t["test_name"]),
            "code": str(t["test_code"]),
            "category": str(t["category_name"]),
            "sample_type": str(t.get("sample_type", "Blood")),
            "tat": int(t.get("turnaround_hours", 24)),
            "price": float(t["price"]),
            "active": bool(t.get("is_active", 1)),
        }
        for t in tests
    }
    return render_template(
        "patient/book_test.html",
        tests=tests,
        categories=categories,
        tests_json=json.dumps(tests_data),
        form=form
    )


@patient_bp.route("/book-test", methods=["GET", "POST"])
@login_required
@role_required(4)
def book_test():
    tests = query_db(
        "SELECT lt.*, tc.category_name FROM lab_tests lt "
        "JOIN test_categories tc ON lt.category_id=tc.category_id ORDER BY tc.category_name ASC, lt.test_name ASC"
    )
    form = BookTestForm()
    if form.validate_on_submit():
        now_pkt = datetime.now(PKT)
        today_pkt = now_pkt.date()
        appt_date = form.appointment_date.data

        if appt_date < today_pkt:
            flash("Appointment date cannot be in the past. Please select today or a future date.", "danger")
            return _render_book_test(form, tests)

        is_avail, _ = check_slot_available(appt_date, form.appointment_slot.data, now_pkt)
        if not is_avail:
            flash(f"The time slot '{form.appointment_slot.data}' is currently unavailable (fully booked). Please select an alternate slot.", "warning")
            return _render_book_test(form, tests)

        selected_ids = request.form.getlist("test_ids")
        if not selected_ids:
            flash("Please select at least one test.", "warning")
            return _render_book_test(form, tests)

        selected_tests = query_db(
            f"SELECT * FROM lab_tests WHERE test_id IN ({','.join(['%s']*len(selected_ids))})",
            tuple(selected_ids)
        )
        
        # Enforce rejection of inactive tests on backend
        inactive_tests = [t for t in selected_tests if not t.get("is_active")]
        if inactive_tests:
            names = ", ".join(t["test_name"] for t in inactive_tests)
            flash(f"Booking rejected: One or more selected tests are currently unavailable ({names}).", "danger")
            return _render_book_test(form, tests)

        total = sum(float(t["price"]) for t in selected_tests)
        booking_ref = _gen_booking_ref()
        invoice_num = _gen_invoice_num()

        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO bookings (booking_ref,patient_id,appointment_date,appointment_slot) VALUES (%s,%s,%s,%s)",
                (booking_ref, current_user.id, form.appointment_date.data, form.appointment_slot.data)
            )
            booking_id = cur.lastrowid
            for t in selected_tests:
                cur.execute(
                    "INSERT INTO booking_items (booking_id,test_id,price_at_booking) VALUES (%s,%s,%s)",
                    (booking_id, t["test_id"], float(t["price"]))
                )
            cur.execute(
                "INSERT INTO invoices (booking_id,invoice_number,total_amount) VALUES (%s,%s,%s)",
                (booking_id, invoice_num, total)
            )
            conn.commit()

            # Fire notifications to Admin (1), Receptionist (2), and Lab Technician (3)
            notify_roles(
                [1, 2, 3],
                "booking",
                "New Online Test Booking",
                f"Patient {current_user.full_name} confirmed appointment for {form.appointment_date.data} ({form.appointment_slot.data}). Ref: {booking_ref}",
                booking_id
            )

            flash(f"Booking confirmed! Reference: {booking_ref}. Invoice: {invoice_num}", "success")
            return redirect(url_for("patient.dashboard"))
        except Exception as e:
            conn.rollback()
            flash(f"Booking failed: {e}", "danger")
        finally:
            cur.close(); conn.close()

    return _render_book_test(form, tests)


@patient_bp.route("/booking/<int:booking_id>")
@login_required
@role_required(4)
def booking_detail(booking_id):
    booking = query_db(
        "SELECT b.*, i.invoice_number, i.total_amount, i.payment_status, i.payment_method "
        "FROM bookings b LEFT JOIN invoices i ON b.booking_id=i.booking_id "
        "WHERE b.booking_id=%s AND b.patient_id=%s",
        (booking_id, current_user.id), one=True
    )
    if not booking:
        abort(403)
    items = query_db(
        "SELECT bi.*, lt.test_name, lt.sample_type, s.barcode_string "
        "FROM booking_items bi JOIN lab_tests lt ON bi.test_id=lt.test_id "
        "LEFT JOIN samples s ON bi.item_id=s.item_id WHERE bi.booking_id=%s",
        (booking_id,)
    )
    return render_template("patient/booking_detail.html", booking=booking, items=items)


@patient_bp.route("/reports")
@login_required
@role_required(4)
def reports():
    """Patient directory of released diagnostic reports."""
    reports_list = query_db("""
        SELECT b.booking_id, b.booking_ref, b.appointment_date, b.appointment_slot,
               b.booking_status, b.released_at, b.patient_viewed_at,
               u_path.full_name AS pathologist_name,
               GROUP_CONCAT(lt.test_name SEPARATOR ', ') AS test_names,
               COUNT(bi.item_id) AS total_tests
        FROM bookings b
        JOIN booking_items bi ON b.booking_id = bi.booking_id
        JOIN lab_tests lt ON bi.test_id = lt.test_id
        LEFT JOIN users u_path ON b.released_by = u_path.user_id
        WHERE b.patient_id = %s
          AND b.booking_status = 'Completed'
          AND b.released_at IS NOT NULL
        GROUP BY b.booking_id, b.booking_ref, b.appointment_date, b.appointment_slot,
                 b.booking_status, b.released_at, b.patient_viewed_at, u_path.full_name
        ORDER BY b.released_at DESC
    """, (current_user.id,))
    return render_template("patient/reports.html", reports=reports_list)


@patient_bp.route("/reports/<int:booking_id>")
@login_required
@role_required(1, 2, 3, 4, 6)
def view_report(booking_id):
    """View official verified diagnostic report for a booking."""
    booking = query_db("""
        SELECT b.*, u.full_name AS patient_name, u.phone, u.email,
               pp.date_of_birth, pp.gender, pp.blood_group,
               u_path.full_name AS pathologist_name,
               u_path.email AS pathologist_email
        FROM bookings b
        JOIN users u ON b.patient_id = u.user_id
        LEFT JOIN patient_profiles pp ON u.user_id = pp.patient_id
        LEFT JOIN users u_path ON b.released_by = u_path.user_id
        WHERE b.booking_id = %s
    """, (booking_id,), one=True)
    if not booking:
        abort(404)

    # Permission check: Patient can only view their own; Staff (1,2,3,6) can view any released report
    if current_user.role_id == 4 and booking["patient_id"] != current_user.id:
        abort(403)
    if current_user.role_id not in (1, 2, 3, 4, 6):
        abort(403)

    # Reports are completely invisible prior to pathologist approval
    if booking["booking_status"] != "Completed" or not booking.get("released_at"):
        abort(403)

    # Record patient_viewed_at on open (dismisses ready alert on dashboard)
    if not booking.get("patient_viewed_at"):
        execute_db("UPDATE bookings SET patient_viewed_at = NOW() WHERE booking_id = %s", (booking_id,))
        booking["patient_viewed_at"] = datetime.now()

    # Fetch test items and measured results
    items = query_db("""
        SELECT bi.item_id, bi.test_id, lt.test_name, lt.test_code, lt.sample_type,
               tc.category_name, s.barcode_string, s.collected_at
        FROM booking_items bi
        JOIN lab_tests lt ON bi.test_id = lt.test_id
        JOIN test_categories tc ON lt.category_id = tc.category_id
        LEFT JOIN samples s ON bi.item_id = s.item_id
        WHERE bi.booking_id = %s
    """, (booking_id,))

    for it in items:
        it["results"] = query_db("""
            SELECT tp.param_name, tp.unit, tp.min_range, tp.max_range,
                   tr.measured_value, tr.flag_status, tr.is_abnormal,
                   ut.full_name AS tech_name, tr.verified_at, tr.pathologist_verified_at
            FROM test_parameters tp
            JOIN test_results tr ON tp.param_id = tr.param_id AND tr.item_id = %s
            LEFT JOIN users ut ON tr.technician_id = ut.user_id
            ORDER BY tp.display_order ASC
        """, (it["item_id"],))

    return render_template("patient/report_view.html", booking=booking, items=items)


@patient_bp.route("/reports/<int:booking_id>/download-pdf")
@patient_bp.route("/reports/<int:booking_id>/pdf")
@login_required
def download_report_pdf(booking_id):
    """Download official verified diagnostic report as formatted PDF."""
    booking = query_db("""
        SELECT b.*, u.full_name AS patient_name, u.phone, u.email,
               pp.date_of_birth, pp.gender, pp.blood_group,
               u_path.full_name AS pathologist_name
        FROM bookings b
        JOIN users u ON b.patient_id = u.user_id
        LEFT JOIN patient_profiles pp ON u.user_id = pp.patient_id
        LEFT JOIN users u_path ON b.released_by = u_path.user_id
        WHERE b.booking_id = %s
    """, (booking_id,), one=True)
    if not booking:
        abort(404)

    # Permission check: Patient can only download their own; Staff (roles 1,2,3,6) can download any
    if current_user.role_id == 4 and booking["patient_id"] != current_user.id:
        abort(403)
    if current_user.role_id not in (1, 2, 3, 4, 6):
        abort(403)

    if booking["booking_status"] != "Completed" or not booking.get("released_at"):
        flash("Report is not yet completed and verified by a Pathologist.", "warning")
        return redirect(request.referrer or url_for("patient.dashboard"))

    items = query_db("""
        SELECT bi.item_id, bi.test_id, lt.test_name, lt.test_code, lt.sample_type,
               tc.category_name, s.barcode_string
        FROM booking_items bi
        JOIN lab_tests lt ON bi.test_id = lt.test_id
        JOIN test_categories tc ON lt.category_id = tc.category_id
        LEFT JOIN samples s ON bi.item_id = s.item_id
        WHERE bi.booking_id = %s
    """, (booking_id,))

    results_map = {}
    for it in items:
        results_map[it["item_id"]] = query_db("""
            SELECT tp.param_name, tp.unit, tp.min_range, tp.max_range,
                   tr.measured_value, tr.flag_status, tr.is_abnormal
            FROM test_parameters tp
            JOIN test_results tr ON tp.param_id = tr.param_id AND tr.item_id = %s
            WHERE tp.test_id = %s
            ORDER BY tp.display_order ASC
        """, (it["item_id"], it["test_id"]))

    pdf_bytes = generate_diagnostic_report_pdf(booking, items, results_map)
    filename = f"MedLab-Report-{booking['booking_ref']}.pdf"

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )


@patient_bp.route("/barcode/<barcode_string>/download")
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

