from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from db import query_db, execute_db, get_db_connection
from models import role_required
from forms import PaymentForm

receptionist_bp = Blueprint("receptionist", __name__, url_prefix="/receptionist")


def _gen_barcode():
    today = datetime.now().strftime("%Y%m%d")
    existing = query_db("SELECT barcode_string FROM samples WHERE barcode_string LIKE %s", (f"SMP-{today}-%",))
    nxt = len(existing) + 1
    return f"SMP-{today}-{nxt:04d}"


@receptionist_bp.route("/dashboard")
@login_required
@role_required(2)
def dashboard():
    q = request.args.get("q", "").strip()
    if q:
        bookings = query_db(
            "SELECT b.*, u.full_name, u.phone, i.invoice_number, i.total_amount, i.payment_status "
            "FROM bookings b JOIN users u ON b.patient_id=u.user_id "
            "LEFT JOIN invoices i ON b.booking_id=i.booking_id "
            "WHERE b.booking_ref LIKE %s OR u.full_name LIKE %s OR u.phone LIKE %s "
            "ORDER BY b.created_at DESC",
            (f"%{q}%", f"%{q}%", f"%{q}%")
        )
    else:
        bookings = query_db(
            "SELECT b.*, u.full_name, u.phone, i.invoice_number, i.total_amount, i.payment_status "
            "FROM bookings b JOIN users u ON b.patient_id=u.user_id "
            "LEFT JOIN invoices i ON b.booking_id=i.booking_id "
            "ORDER BY b.created_at DESC LIMIT 30"
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


@receptionist_bp.route("/booking-item/<int:item_id>/collect-sample", methods=["POST"])
@login_required
@role_required(2)
def collect_sample(item_id):
    item = query_db("SELECT bi.*, b.booking_id FROM booking_items bi JOIN bookings b ON bi.booking_id=b.booking_id WHERE bi.item_id=%s", (item_id,), one=True)
    if not item:
        flash("Booking item not found.", "danger")
        return redirect(url_for("receptionist.dashboard"))
    existing = query_db("SELECT 1 FROM samples WHERE item_id=%s", (item_id,), one=True)
    if existing:
        flash("Sample already collected for this item.", "warning")
        return redirect(url_for("receptionist.booking_detail", booking_id=item["booking_id"]))
    barcode = _gen_barcode()
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO samples (item_id, barcode_string, collected_by) VALUES (%s,%s,%s)",
            (item_id, barcode, current_user.id)
        )
        cur.execute("UPDATE booking_items SET item_status='Sample_Collected' WHERE item_id=%s", (item_id,))
        cur.execute(
            "UPDATE bookings SET booking_status='Sample_Collected' WHERE booking_id=%s "
            "AND booking_status='Booked'",
            (item["booking_id"],)
        )
        conn.commit()
        flash(f"Sample collected! Barcode: {barcode}", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Sample collection failed: {e}", "danger")
    finally:
        cur.close(); conn.close()
    return redirect(url_for("receptionist.booking_detail", booking_id=item["booking_id"]))


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
