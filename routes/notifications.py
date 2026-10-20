"""
routes/notifications.py
=======================
Notifications system for MedLab:
  - GET /notifications            -> Dedicated notifications page with filter tabs (All/Unread), pagination, empty state.
  - GET /notifications/<id>       -> Detail view with booking ref, stage tracker, short timeline, role-specific "Go to booking" button.
                                     Marked as read on open. 403 if not owner.
  - POST /notifications/mark-all-read -> Mark all notifications read for current user.
  - GET /notifications/api/unread-count -> JSON endpoint for top-bar bell 10s polling.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import login_required, current_user
from db import query_db, execute_db

notifications_bp = Blueprint("notifications", __name__, url_prefix="/notifications")


def create_notification(user_id, notif_type, title, message, booking_id=None):
    """System helper to insert an in-app notification."""
    return execute_db("""
        INSERT INTO notifications (user_id, type, title, message, booking_id, is_read)
        VALUES (%s, %s, %s, %s, %s, 0)
    """, (user_id, notif_type, title, message, booking_id))


@notifications_bp.route("", strict_slashes=False)
@notifications_bp.route("/", strict_slashes=False)
@login_required
def index():
    """Dedicated notifications list with filter tabs (All/Unread), pagination, and empty state."""
    filter_mode = request.args.get("filter", "all").lower()
    page = request.args.get("page", 1, type=int)
    per_page = 10
    offset = max(0, (page - 1) * per_page)

    where_clause = "WHERE user_id = %s"
    params = [current_user.id]

    if filter_mode == "unread":
        where_clause += " AND is_read = 0"

    total_count_row = query_db(
        f"SELECT COUNT(*) AS c FROM notifications {where_clause}",
        params, one=True
    )
    total_count = total_count_row["c"] if total_count_row else 0
    total_pages = max(1, (total_count + per_page - 1) // per_page)

    if page > total_pages:
        page = total_pages
        offset = max(0, (page - 1) * per_page)

    notifications = query_db(
        f"SELECT * FROM notifications {where_clause} ORDER BY created_at DESC LIMIT %s OFFSET %s",
        params + [per_page, offset]
    )

    unread_row = query_db(
        "SELECT COUNT(*) AS c FROM notifications WHERE user_id = %s AND is_read = 0",
        (current_user.id,), one=True
    )
    unread_total = unread_row["c"] if unread_row else 0

    all_row = query_db(
        "SELECT COUNT(*) AS c FROM notifications WHERE user_id = %s",
        (current_user.id,), one=True
    )
    all_total = all_row["c"] if all_row else 0

    return render_template(
        "notifications/index.html",
        notifications=notifications,
        filter_mode=filter_mode,
        page=page,
        total_pages=total_pages,
        total_count=total_count,
        unread_total=unread_total,
        all_total=all_total
    )


@notifications_bp.route("/<int:notification_id>")
@login_required
def detail(notification_id):
    """
    Notification detail route:
      - Title, message, timestamp
      - Related booking ref (if booking_id present)
      - Stage tracker & short timeline
      - Role-specific "Go to booking" button
      - Marked as read on open
      - 403 Forbidden if not the owner
    """
    notif = query_db(
        "SELECT * FROM notifications WHERE notification_id = %s",
        (notification_id,), one=True
    )
    if not notif:
        abort(404)

    # 403 Forbidden if the notification does not belong to current user
    if notif["user_id"] != current_user.id:
        abort(403)

    # Mark as read on open
    if not notif["is_read"]:
        execute_db(
            "UPDATE notifications SET is_read = 1 WHERE notification_id = %s",
            (notification_id,)
        )
        notif["is_read"] = 1

    booking = None
    timeline = []
    role_booking_url = None

    if notif["booking_id"]:
        booking = query_db("""
            SELECT b.*, u.full_name AS patient_name, u.phone AS patient_phone,
                   i.invoice_number, i.total_amount, i.payment_status
            FROM bookings b
            JOIN users u ON b.patient_id = u.user_id
            LEFT JOIN invoices i ON b.booking_id = i.booking_id
            WHERE b.booking_id = %s
        """, (notif["booking_id"],), one=True)

        if booking:
            # 1. Booking Created
            timeline.append({
                "stage": "Booking Registered",
                "time": booking["created_at"],
                "status": "done",
                "desc": f"Appointment booked for {booking['appointment_date']} ({booking['appointment_slot']})"
            })

            # 2. Sample Collection
            sample = query_db("""
                SELECT s.* FROM samples s
                JOIN booking_items bi ON s.item_id = bi.item_id
                WHERE bi.booking_id = %s
                ORDER BY s.sample_id ASC LIMIT 1
            """, (booking["booking_id"],), one=True)
            if sample and sample["collected_at"]:
                timeline.append({
                    "stage": "Sample Collected",
                    "time": sample["collected_at"],
                    "status": "done",
                    "desc": f"Sample barcoded: {sample['barcode_string']}"
                })
            elif booking["booking_status"] in ["Sample_Collected", "In_Analysis", "Completed"]:
                timeline.append({
                    "stage": "Sample Collected",
                    "time": booking["appointment_date"],
                    "status": "done",
                    "desc": "Specimen collected and received at lab"
                })
            else:
                timeline.append({
                    "stage": "Sample Collection",
                    "time": None,
                    "status": "pending",
                    "desc": "Pending patient arrival or phlebotomist visit"
                })

            # 3. Laboratory Analysis
            if booking["booking_status"] in ["In_Analysis", "Completed"]:
                timeline.append({
                    "stage": "Laboratory Analysis",
                    "time": None,
                    "status": "done",
                    "desc": "Analyzers completed testing and reference verification"
                })
            else:
                timeline.append({
                    "stage": "Laboratory Analysis",
                    "time": None,
                    "status": "pending",
                    "desc": "Awaiting specimen arrival and analyzer processing"
                })

            # 4. Pathologist Verification
            if booking["booking_status"] == "Completed":
                timeline.append({
                    "stage": "Pathologist Verified",
                    "time": None,
                    "status": "done",
                    "desc": "Senior pathologist reviewed and released official digital report"
                })
            else:
                timeline.append({
                    "stage": "Pathologist Verification",
                    "time": None,
                    "status": "pending",
                    "desc": "Awaiting senior pathologist medical review and sign-off"
                })

            # Role-specific "Go to booking" target
            role_map = {
                1: url_for("admin.dashboard"),
                2: url_for("receptionist.booking_detail", booking_id=booking["booking_id"]),
                3: url_for("technician.dashboard"),
                4: url_for("patient.booking_detail", booking_id=booking["booking_id"]),
                5: url_for("collector.dashboard"),
                6: url_for("pathologist.dashboard"),
            }
            role_booking_url = role_map.get(current_user.role_id, url_for("patient.dashboard"))

    return render_template(
        "notifications/detail.html",
        notif=notif,
        booking=booking,
        timeline=timeline,
        role_booking_url=role_booking_url
    )


@notifications_bp.route("/mark-all-read", methods=["POST"])
@login_required
def mark_all_read():
    """Mark all unread notifications for current user as read."""
    execute_db(
        "UPDATE notifications SET is_read = 1 WHERE user_id = %s",
        (current_user.id,)
    )
    flash("All notifications have been marked as read.", "success")
    return redirect(request.referrer or url_for("notifications.index"))


@notifications_bp.route("/api/unread-count")
@login_required
def api_unread_count():
    """JSON API polled every 10 seconds for real-time notification badge and toast triggers."""
    row = query_db(
        "SELECT COUNT(*) AS c, COALESCE(MAX(notification_id), 0) AS max_id FROM notifications WHERE user_id = %s AND is_read = 0",
        (current_user.id,), one=True
    )
    return jsonify({
        "unread_count": row["c"] if row else 0,
        "max_id": row["max_id"] if row else 0
    })
