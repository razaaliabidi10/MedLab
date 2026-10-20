from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from db import query_db, execute_db, get_db_connection
from models import role_required
from forms import BookTestForm

patient_bp = Blueprint("patient", __name__, url_prefix="/patient")


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
    return render_template("patient/dashboard.html", bookings=bookings)


@patient_bp.route("/book-test", methods=["GET", "POST"])
@login_required
@role_required(4)
def book_test():
    tests = query_db(
        "SELECT lt.*, tc.category_name FROM lab_tests lt "
        "JOIN test_categories tc ON lt.category_id=tc.category_id WHERE lt.is_active=1"
    )
    form = BookTestForm()
    if form.validate_on_submit():
        selected_ids = request.form.getlist("test_ids")
        if not selected_ids:
            flash("Please select at least one test.", "warning")
            return render_template("patient/book_test.html", tests=tests, form=form)

        selected_tests = query_db(
            f"SELECT * FROM lab_tests WHERE test_id IN ({','.join(['%s']*len(selected_ids))})",
            tuple(selected_ids)
        )
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
            flash(f"Booking confirmed! Reference: {booking_ref}. Invoice: {invoice_num}", "success")
            return redirect(url_for("patient.dashboard"))
        except Exception as e:
            conn.rollback()
            flash(f"Booking failed: {e}", "danger")
        finally:
            cur.close(); conn.close()

    return render_template("patient/book_test.html", tests=tests, form=form)


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
