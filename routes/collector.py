"""
routes/collector.py
===================
Blueprint for Sample Collector / Phlebotomist (Role 5):
  - Dashboard: Assigned collections (Lab visits & Home collections with address)
  - Mark Collected: Generates barcode string, inserts into samples, sets booking status to 'Sample_Collected'
  - Reject Sample: Marks sample rejected with reason (insufficient volume, hemolysis, etc.)
"""

from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from db import query_db, get_db_connection
from models import role_required

collector_bp = Blueprint("collector", __name__, url_prefix="/collector")


@collector_bp.route("/dashboard")
@login_required
@role_required(5)
def dashboard():
    """Sample Collector task queue: Confirmed bookings ready for phlebotomy."""
    # Awaiting collection: Confirmed bookings
    collection_queue = query_db("""
        SELECT b.booking_id, b.booking_ref, b.appointment_date, b.appointment_slot,
               b.collection_type, b.collection_address, b.booking_status, b.created_at,
               u.full_name AS patient_name, u.phone AS patient_phone, u.email AS patient_email,
               COUNT(bi.item_id) AS total_tests,
               GROUP_CONCAT(lt.test_name SEPARATOR ', ') AS test_names
        FROM bookings b
        JOIN users u ON b.patient_id = u.user_id
        JOIN booking_items bi ON b.booking_id = bi.booking_id
        JOIN lab_tests lt ON bi.test_id = lt.test_id
        WHERE b.booking_status = 'Confirmed'
        GROUP BY b.booking_id, b.booking_ref, b.appointment_date, b.appointment_slot,
                 b.collection_type, b.collection_address, b.booking_status, b.created_at,
                 u.full_name, u.phone, u.email
        ORDER BY b.appointment_date ASC, b.collection_type DESC
    """)

    # Recently collected samples by this collector
    recent_collected = query_db("""
        SELECT s.sample_id, s.barcode_string, s.collected_at, s.sample_status, s.rejection_reason,
               bi.booking_id, b.booking_ref, lt.test_name, lt.sample_type,
               u.full_name AS patient_name
        FROM samples s
        JOIN booking_items bi ON s.item_id = bi.item_id
        JOIN bookings b ON bi.booking_id = b.booking_id
        JOIN lab_tests lt ON bi.test_id = lt.test_id
        JOIN users u ON b.patient_id = u.user_id
        WHERE s.collected_by = %s
        ORDER BY s.collected_at DESC
        LIMIT 10
    """, (current_user.id,))

    stats = {
        "pending_collections": len(collection_queue) if collection_queue else 0,
        "collected_today": query_db("""
            SELECT COUNT(*) AS c
            FROM samples
            WHERE collected_by = %s AND DATE(collected_at) = CURDATE()
        """, (current_user.id,), one=True)["c"] or 0
    }

    return render_template(
        "collector/dashboard.html",
        collection_queue=collection_queue,
        recent_collected=recent_collected,
        stats=stats
    )


@collector_bp.route("/collect/<int:booking_id>", methods=["POST"])
@login_required
@role_required(5)
def collect(booking_id):
    """Mark all items in this booking as collected, generate barcodes, and update status."""
    booking = query_db("SELECT * FROM bookings WHERE booking_id = %s", (booking_id,), one=True)
    if not booking:
        flash("Booking not found.", "danger")
        return redirect(url_for("collector.dashboard"))

    if booking["booking_status"] != "Confirmed":
        flash(f"Cannot collect: booking status is {booking['booking_status']}, expected Confirmed.", "warning")
        return redirect(url_for("collector.dashboard"))

    items = query_db("SELECT item_id FROM booking_items WHERE booking_id = %s", (booking_id,))
    if not items:
        flash("No tests associated with this booking.", "warning")
        return redirect(url_for("collector.dashboard"))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        now_dt = datetime.now()
        for it in items:
            item_id = it["item_id"]
            barcode = f"SMP-{item_id:06d}"
            # Insert or update sample record
            cur.execute("""
                INSERT INTO samples (item_id, barcode_string, collected_by, collected_at, sample_status)
                VALUES (%s, %s, %s, %s, 'Collected')
                ON DUPLICATE KEY UPDATE
                    barcode_string = VALUES(barcode_string),
                    collected_by   = VALUES(collected_by),
                    collected_at   = VALUES(collected_at),
                    sample_status  = 'Collected'
            """, (item_id, barcode, current_user.id, now_dt))

            cur.execute("UPDATE booking_items SET item_status = 'Sample_Collected' WHERE item_id = %s", (item_id,))

        # Update booking status: Confirmed -> Sample_Collected
        cur.execute("UPDATE bookings SET booking_status = 'Sample_Collected' WHERE booking_id = %s", (booking_id,))

        # Insert notification for patient
        cur.execute("""
            INSERT INTO notifications (user_id, type, title, message, booking_id)
            VALUES (%s, 'sample', 'Sample Collected', %s, %s)
        """, (
            booking["patient_id"],
            f"Your sample for booking {booking['booking_ref']} has been successfully collected and sent to the laboratory.",
            booking_id
        ))

        conn.commit()
        flash(f"Sample(s) for booking {booking['booking_ref']} marked as collected.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Failed to record sample collection: {e}", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("collector.dashboard"))


@collector_bp.route("/reject/<int:booking_id>", methods=["POST"])
@login_required
@role_required(5)
def reject(booking_id):
    """Mark sample as rejected with a reason (e.g. Hemolysis, Insufficient Volume)."""
    reason = request.form.get("rejection_reason", "").strip()
    if not reason:
        flash("Rejection reason is required.", "warning")
        return redirect(url_for("collector.dashboard"))

    booking = query_db("SELECT * FROM bookings WHERE booking_id = %s", (booking_id,), one=True)
    if not booking:
        flash("Booking not found.", "danger")
        return redirect(url_for("collector.dashboard"))

    items = query_db("SELECT item_id FROM booking_items WHERE booking_id = %s", (booking_id,))
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        now_dt = datetime.now()
        for it in items:
            item_id = it["item_id"]
            barcode = f"SMP-{item_id:06d}"
            cur.execute("""
                INSERT INTO samples (item_id, barcode_string, collected_by, collected_at, sample_status, rejection_reason)
                VALUES (%s, %s, %s, %s, 'Rejected', %s)
                ON DUPLICATE KEY UPDATE
                    sample_status    = 'Rejected',
                    rejection_reason = VALUES(rejection_reason)
            """, (item_id, barcode, current_user.id, now_dt, reason))

        # Notify patient
        cur.execute("""
            INSERT INTO notifications (user_id, type, title, message, booking_id)
            VALUES (%s, 'sample', 'Sample Collection Issue', %s, %s)
        """, (
            booking["patient_id"],
            f"Sample collection for booking {booking['booking_ref']} was rejected: {reason}. Our team will contact you to reschedule.",
            booking_id
        ))

        conn.commit()
        flash(f"Sample marked as rejected: {reason}", "warning")
    except Exception as e:
        conn.rollback()
        flash(f"Failed to record rejection: {e}", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("collector.dashboard"))
