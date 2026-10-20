"""
routes/pathologist.py
======================
Blueprint for Pathologist (Role 6):
  - Verification Queue: displays bookings in 'Pending_Verification' status
  - Review Results: detailed view of all test parameters with abnormal values highlighted
  - Approve Report: signs off (verified_by, verified_at), transitions booking to 'Completed'
  - Send Back: rejects results with comments, transitions booking back to 'In_Analysis'
"""

from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from db import query_db, get_db_connection
from models import role_required

pathologist_bp = Blueprint("pathologist", __name__, url_prefix="/pathologist")


@pathologist_bp.route("/dashboard")
@login_required
@role_required(6)
def dashboard():
    """Pathologist main worklist: bookings awaiting verification."""
    # Active queue: bookings in Pending_Verification
    pending_queue = query_db("""
        SELECT b.booking_id, b.booking_ref, b.appointment_date, b.appointment_slot,
               b.collection_type, b.booking_status, b.created_at,
               u.full_name AS patient_name, u.phone AS patient_phone, u.email AS patient_email,
               COUNT(bi.item_id) AS total_tests,
               SUM(CASE WHEN tr.is_abnormal = 1 THEN 1 ELSE 0 END) AS abnormal_count
        FROM bookings b
        JOIN users u ON b.patient_id = u.user_id
        JOIN booking_items bi ON b.booking_id = bi.booking_id
        LEFT JOIN test_results tr ON bi.item_id = tr.item_id
        WHERE b.booking_status = 'Pending_Verification'
        GROUP BY b.booking_id, b.booking_ref, b.appointment_date, b.appointment_slot,
                 b.collection_type, b.booking_status, b.created_at,
                 u.full_name, u.phone, u.email
        ORDER BY b.appointment_date ASC, b.created_at ASC
    """)

    # Recently verified (for history/reference)
    recent_verified = query_db("""
        SELECT b.booking_id, b.booking_ref, b.appointment_date, b.booking_status,
               u.full_name AS patient_name,
               MAX(tr.pathologist_verified_at) AS verified_at,
               COUNT(DISTINCT bi.item_id) AS total_tests
        FROM bookings b
        JOIN users u ON b.patient_id = u.user_id
        JOIN booking_items bi ON b.booking_id = bi.booking_id
        JOIN test_results tr ON bi.item_id = tr.item_id
        WHERE b.booking_status = 'Completed' AND tr.verified_by = %s
        GROUP BY b.booking_id, b.booking_ref, b.appointment_date, b.booking_status, u.full_name
        ORDER BY verified_at DESC
        LIMIT 10
    """, (current_user.id,))

    # Metric counters
    stats = {
        "pending_count": len(pending_queue) if pending_queue else 0,
        "verified_today": query_db("""
            SELECT COUNT(DISTINCT bi.booking_id) AS c
            FROM test_results tr
            JOIN booking_items bi ON tr.item_id = bi.item_id
            WHERE tr.verified_by = %s AND DATE(tr.pathologist_verified_at) = CURDATE()
        """, (current_user.id,), one=True)["c"] or 0,
        "total_completed": len(recent_verified) if recent_verified else 0
    }

    return render_template(
        "pathologist/dashboard.html",
        pending_queue=pending_queue,
        recent_verified=recent_verified,
        stats=stats
    )


@pathologist_bp.route("/review/<int:booking_id>")
@login_required
@role_required(6)
def review(booking_id):
    """Detailed result review page with flags, ranges, and sign-off actions."""
    booking = query_db("""
        SELECT b.*, u.full_name AS patient_name, u.phone AS patient_phone, u.email AS patient_email,
               pp.date_of_birth, pp.gender, pp.blood_group
        FROM bookings b
        JOIN users u ON b.patient_id = u.user_id
        LEFT JOIN patient_profiles pp ON u.user_id = pp.patient_id
        WHERE b.booking_id = %s
    """, (booking_id,), one=True)

    if not booking:
        flash("Booking not found.", "warning")
        return redirect(url_for("pathologist.dashboard"))

    # Fetch test items for this booking
    items = query_db("""
        SELECT bi.item_id, bi.test_id, bi.price_at_booking, bi.item_status,
               lt.test_code, lt.test_name, lt.sample_type, tc.category_name,
               s.barcode_string, s.collected_at, s.sample_status,
               u_coll.full_name AS collector_name
        FROM booking_items bi
        JOIN lab_tests lt ON bi.test_id = lt.test_id
        JOIN test_categories tc ON lt.category_id = tc.category_id
        LEFT JOIN samples s ON bi.item_id = s.item_id
        LEFT JOIN users u_coll ON s.collected_by = u_coll.user_id
        WHERE bi.booking_id = %s
    """, (booking_id,))

    # Group parameters & measured values under each item
    for it in items:
        results = query_db("""
            SELECT tp.param_id, tp.param_name, tp.unit, tp.min_range, tp.max_range, tp.display_order,
                   tr.result_id, tr.measured_value, tr.flag_status, tr.is_abnormal,
                   tr.technician_id, tr.verified_by, tr.pathologist_verified_at, tr.pathologist_comment,
                   u_tech.full_name AS technician_name
            FROM test_parameters tp
            LEFT JOIN test_results tr ON tp.param_id = tr.param_id AND tr.item_id = %s
            LEFT JOIN users u_tech ON tr.technician_id = u_tech.user_id
            WHERE tp.test_id = %s
            ORDER BY tp.display_order ASC
        """, (it["item_id"], it["test_id"]))
        it["results"] = results

    return render_template("pathologist/review.html", booking=booking, items=items)


@pathologist_bp.route("/approve/<int:booking_id>", methods=["POST"])
@login_required
@role_required(6)
def approve(booking_id):
    """Approve booking results, set verified_by/at, and mark booking Completed."""
    booking = query_db("SELECT * FROM bookings WHERE booking_id = %s", (booking_id,), one=True)
    if not booking:
        flash("Booking not found.", "danger")
        return redirect(url_for("pathologist.dashboard"))

    if booking["booking_status"] != "Pending_Verification":
        flash(f"Cannot approve: booking status is {booking['booking_status']}, expected Pending_Verification.", "warning")
        return redirect(url_for("pathologist.review", booking_id=booking_id))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        now_dt = datetime.now()

        # Update test_results for all items in this booking
        cur.execute("""
            UPDATE test_results tr
            JOIN booking_items bi ON tr.item_id = bi.item_id
            SET tr.verified_by = %s,
                tr.pathologist_verified_at = %s,
                tr.pathologist_comment = NULL
            WHERE bi.booking_id = %s
        """, (current_user.id, now_dt, booking_id))

        # Update booking_items to Report_Ready
        cur.execute("""
            UPDATE booking_items
            SET item_status = 'Report_Ready'
            WHERE booking_id = %s
        """, (booking_id,))

        # Update booking status: Pending_Verification -> Completed
        cur.execute("""
            UPDATE bookings
            SET booking_status = 'Completed'
            WHERE booking_id = %s
        """, (booking_id,))

        # Insert notification for patient
        cur.execute("""
            INSERT INTO notifications (user_id, type, title, message, booking_id)
            VALUES (%s, 'result', 'Diagnostic Report Ready', %s, %s)
        """, (
            booking["patient_id"],
            f"Your diagnostic report for booking {booking['booking_ref']} has been verified and approved by Dr. {current_user.full_name}.",
            booking_id
        ))

        conn.commit()
        flash(f"Booking {booking['booking_ref']} successfully verified and approved. Report is now available for patient.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Failed to approve booking: {e}", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("pathologist.dashboard"))


@pathologist_bp.route("/send-back/<int:booking_id>", methods=["POST"])
@login_required
@role_required(6)
def send_back(booking_id):
    """Send results back to technician for re-testing or correction with comments."""
    booking = query_db("SELECT * FROM bookings WHERE booking_id = %s", (booking_id,), one=True)
    if not booking:
        flash("Booking not found.", "danger")
        return redirect(url_for("pathologist.dashboard"))

    comment = request.form.get("pathologist_comment", "").strip()
    if not comment:
        flash("Please provide a reason or correction instructions when sending back results.", "warning")
        return redirect(url_for("pathologist.review", booking_id=booking_id))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Save comment on results
        cur.execute("""
            UPDATE test_results tr
            JOIN booking_items bi ON tr.item_id = bi.item_id
            SET tr.pathologist_comment = %s
            WHERE bi.booking_id = %s
        """, (comment, booking_id))

        # Revert status: Pending_Verification -> In_Analysis (allowed by state machine)
        cur.execute("""
            UPDATE bookings
            SET booking_status = 'In_Analysis'
            WHERE booking_id = %s
        """, (booking_id,))

        # Notify technician
        cur.execute("""
            INSERT INTO notifications (user_id, type, title, message, booking_id)
            SELECT DISTINCT tr.technician_id, 'result', 'Report Sent Back for Review', %s, %s
            FROM test_results tr
            JOIN booking_items bi ON tr.item_id = bi.item_id
            WHERE bi.booking_id = %s AND tr.technician_id IS NOT NULL
        """, (
            f"Pathologist sent back booking {booking['booking_ref']}: {comment}",
            booking_id,
            booking_id
        ))

        conn.commit()
        flash(f"Booking {booking['booking_ref']} sent back to technician with instructions.", "info")
    except Exception as e:
        conn.rollback()
        flash(f"Failed to send back: {e}", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("pathologist.dashboard"))
