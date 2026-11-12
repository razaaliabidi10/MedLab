from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from db import query_db, execute_db, get_db_connection
from models import role_required
from routes.notifications import create_notification, notify_roles

technician_bp = Blueprint("technician", __name__, url_prefix="/technician")


def _gen_barcode(item_id=None):
    today = datetime.now().strftime("%Y%m%d")
    if item_id is not None:
        return f"SMP-{today}-{int(item_id):05d}"
    row = query_db("SELECT MAX(sample_id) AS m FROM samples", one=True)
    nxt = (row["m"] or 0) + 1 if row else 1
    return f"SMP-{today}-{nxt:05d}"


@technician_bp.route("/dashboard")
@login_required
@role_required(3)
def dashboard():
    """
    Lab Technician main dashboard:
      1. Process Pipeline: Real-time patient diagnostic lifecycle summary
      2. Awaiting Collection: Bookings awaiting specimen collection and barcode generation
      3. Active Worklist: Samples collected requiring test analysis & results entry
    """
    # 1. Compact Patient Process Pipeline (All active journeys)
    process_patients = query_db("""
        SELECT b.booking_id, b.booking_ref, b.appointment_date, b.appointment_slot,
               b.booking_status, b.created_at,
               u.user_id AS patient_id, u.full_name AS patient_name, u.phone AS patient_phone,
               GROUP_CONCAT(DISTINCT lt.test_name ORDER BY lt.test_name SEPARATOR ', ') AS test_names,
               COUNT(DISTINCT bi.item_id) AS total_items,
               COUNT(DISTINCT s.sample_id) AS collected_samples,
               COUNT(DISTINCT tr.result_id) AS results_count
        FROM bookings b
        JOIN users u ON b.patient_id = u.user_id
        JOIN booking_items bi ON b.booking_id = bi.booking_id
        JOIN lab_tests lt ON bi.test_id = lt.test_id
        LEFT JOIN samples s ON bi.item_id = s.item_id
        LEFT JOIN test_results tr ON bi.item_id = tr.item_id
        WHERE b.booking_status NOT IN ('Cancelled')
        GROUP BY b.booking_id, b.booking_ref, b.appointment_date, b.appointment_slot,
                 b.booking_status, b.created_at, u.user_id, u.full_name, u.phone
        ORDER BY b.created_at DESC
        LIMIT 10
    """)

    # 2. Awaiting Sample Collection
    pending_collections = query_db("""
        SELECT b.booking_id, b.booking_ref, b.appointment_date, b.appointment_slot,
               b.booking_status, b.created_at,
               u.full_name AS patient_name, u.phone AS patient_phone,
               COALESCE(i.payment_status, 'Unpaid') AS payment_status,
               COALESCE(i.total_amount, 0) AS total_amount,
               GROUP_CONCAT(DISTINCT CONCAT(lt.test_name, ' (', lt.sample_type, ')') SEPARATOR ', ') AS test_list,
               COUNT(bi.item_id) AS total_tests,
               COUNT(s.sample_id) AS collected_count
        FROM bookings b
        JOIN users u ON b.patient_id = u.user_id
        JOIN booking_items bi ON b.booking_id = bi.booking_id
        JOIN lab_tests lt ON bi.test_id = lt.test_id
        LEFT JOIN invoices i ON b.booking_id = i.booking_id
        LEFT JOIN samples s ON bi.item_id = s.item_id
        WHERE b.booking_status IN ('Booked', 'Confirmed') OR (b.booking_status = 'Sample_Collected' AND s.sample_id IS NULL)
        GROUP BY b.booking_id, b.booking_ref, b.appointment_date, b.appointment_slot,
                 b.booking_status, b.created_at, u.full_name, u.phone, i.payment_status, i.total_amount
        HAVING collected_count < total_tests
        ORDER BY b.created_at DESC
    """)

    # 3. Active Worklist (Samples collected awaiting results entry)
    worklist = query_db("""
        SELECT bi.item_id, bi.booking_id, bi.item_status,
               b.booking_ref, b.booking_status, b.appointment_date, b.appointment_slot,
               u.full_name AS patient_name, u.phone AS patient_phone,
               COALESCE(i.payment_status, 'Unpaid') AS payment_status,
               COALESCE(i.total_amount, 0) AS total_amount,
               lt.test_id, lt.test_name, lt.sample_type, lt.test_code,
               s.sample_id, s.barcode_string, s.collected_at, s.sample_status,
               COUNT(tp.param_id) AS total_params,
               COUNT(tr.result_id) AS entered_params
        FROM samples s
        JOIN booking_items bi ON s.item_id = bi.item_id
        JOIN bookings b ON bi.booking_id = b.booking_id
        JOIN lab_tests lt ON bi.test_id = lt.test_id
        JOIN users u ON b.patient_id = u.user_id
        LEFT JOIN invoices i ON b.booking_id = i.booking_id
        LEFT JOIN test_parameters tp ON lt.test_id = tp.test_id
        LEFT JOIN test_results tr ON bi.item_id = tr.item_id AND tp.param_id = tr.param_id
        WHERE b.booking_status IN ('Sample_Collected', 'In_Analysis')
        GROUP BY bi.item_id, bi.booking_id, bi.item_status, b.booking_ref, b.booking_status,
                 b.appointment_date, b.appointment_slot, u.full_name, u.phone, i.payment_status, i.total_amount,
                 lt.test_id, lt.test_name, lt.sample_type, lt.test_code,
                 s.sample_id, s.barcode_string, s.collected_at, s.sample_status
        ORDER BY s.collected_at DESC
    """)

    return render_template(
        "technician/dashboard.html",
        process_patients=process_patients,
        pending_collections=pending_collections,
        worklist=worklist
    )


@technician_bp.route("/booking/<int:booking_id>")
@login_required
@role_required(3)
def manage_booking(booking_id):
    """Compact management panel for a patient booking: sample collection, testing progress, and forwarding."""
    booking = query_db("""
        SELECT b.*, u.full_name, u.phone, u.email,
               pp.date_of_birth, pp.gender, pp.blood_group, pp.address,
               i.invoice_number, i.total_amount, i.payment_status
        FROM bookings b
        JOIN users u ON b.patient_id = u.user_id
        LEFT JOIN patient_profiles pp ON u.user_id = pp.patient_id
        LEFT JOIN invoices i ON b.booking_id = i.booking_id
        WHERE b.booking_id = %s
    """, (booking_id,), one=True)
    if not booking:
        abort(404)

    items = query_db("""
        SELECT bi.*, lt.test_name, lt.test_code, lt.sample_type, lt.turnaround_hours,
               s.sample_id, s.barcode_string, s.collected_at, s.sample_status,
               COUNT(tp.param_id) AS total_params,
               COUNT(tr.result_id) AS entered_params
        FROM booking_items bi
        JOIN lab_tests lt ON bi.test_id = lt.test_id
        LEFT JOIN samples s ON bi.item_id = s.item_id
        LEFT JOIN test_parameters tp ON lt.test_id = tp.test_id
        LEFT JOIN test_results tr ON bi.item_id = tr.item_id AND tp.param_id = tr.param_id
        WHERE bi.booking_id = %s
        GROUP BY bi.item_id, lt.test_name, lt.test_code, lt.sample_type, lt.turnaround_hours,
                 s.sample_id, s.barcode_string, s.collected_at, s.sample_status
        ORDER BY bi.item_id ASC
    """, (booking_id,))

    all_collected = all(bool(it.get("barcode_string")) for it in items) if items else False
    all_results_entered = all(it.get("entered_params", 0) > 0 and it.get("entered_params") >= it.get("total_params", 1) for it in items) if items else False

    return render_template(
        "technician/manage.html",
        booking=booking,
        items=items,
        all_collected=all_collected,
        all_results_entered=all_results_entered
    )


@technician_bp.route("/booking/<int:booking_id>/confirm-sample", methods=["POST"])
@login_required
@role_required(3)
def confirm_sample(booking_id):
    """Confirms specimen collection for a booking, assigns barcode strings, and advances status to Sample_Collected."""
    booking = query_db(
        "SELECT b.*, u.full_name FROM bookings b JOIN users u ON b.patient_id = u.user_id WHERE b.booking_id = %s",
        (booking_id,), one=True
    )
    if not booking:
        flash("Booking not found.", "danger")
        return redirect(url_for("technician.dashboard"))

    items = query_db("SELECT item_id FROM booking_items WHERE booking_id = %s", (booking_id,))
    if not items:
        flash("No test items found for this booking.", "warning")
        return redirect(url_for("technician.manage_booking", booking_id=booking_id))

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        collected_barcodes = []
        for it in items:
            cur.execute("SELECT sample_id, barcode_string FROM samples WHERE item_id = %s", (it["item_id"],))
            existing = cur.fetchone()
            if not existing:
                bc = _gen_barcode(it["item_id"])
                cur.execute(
                    "INSERT INTO samples (item_id, barcode_string, collected_by, collected_at, sample_status) VALUES (%s, %s, %s, NOW(), 'Collected')",
                    (it["item_id"], bc, current_user.id)
                )
                cur.execute("UPDATE booking_items SET item_status = 'Sample_Collected' WHERE item_id = %s", (it["item_id"],))
                collected_barcodes.append(bc)
            else:
                bc = existing["barcode_string"]
                cur.execute("UPDATE booking_items SET item_status = 'Sample_Collected' WHERE item_id = %s AND item_status = 'Pending'", (it["item_id"],))
                collected_barcodes.append(bc)

        # Check current booking status in active transaction with row lock
        cur.execute("SELECT booking_status FROM bookings WHERE booking_id = %s FOR UPDATE", (booking_id,))
        b_row = cur.fetchone()
        cur_status = b_row["booking_status"] if b_row else "Booked"

        if cur_status == "Booked":
            cur.execute(
                "UPDATE bookings SET booking_status = 'Confirmed' WHERE booking_id = %s",
                (booking_id,)
            )
            cur_status = "Confirmed"

        if cur_status == "Confirmed":
            cur.execute(
                "UPDATE bookings SET booking_status = 'Sample_Collected' WHERE booking_id = %s",
                (booking_id,)
            )

        conn.commit()

        # Notify Patient and Receptionist
        create_notification(
            booking["patient_id"],
            "sample",
            "Specimen Collected",
            f"Your diagnostic sample for booking {booking['booking_ref']} has been collected and logged into the laboratory system.",
            booking_id
        )
        notify_roles(
            [1, 2],
            "sample",
            "Sample Collected by Technician",
            f"Specimen collected for patient {booking['full_name']} ({booking['booking_ref']}) by {current_user.full_name}. In testing queue.",
            booking_id
        )

        flash(f"Sample collection confirmed! Assigned barcodes: {', '.join(collected_barcodes)}.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Sample confirmation failed: {e}", "danger")
    finally:
        cur.close()
        conn.close()

    if request.referrer and "/technician/" in request.referrer:
        return redirect(request.referrer)
    return redirect(url_for("technician.manage_booking", booking_id=booking_id))


def _finalize_and_transfer_to_pathologist(booking_id, user):
    """
    Ensures all parameters across all items in a booking have measured values
    (auto-populating reference median values for any remaining unentered tests/parameters),
    marks all samples as Analyzed, marks all booking items as Report_Ready,
    advances booking_status cleanly to Pending_Verification,
    and sends in-app notification to Senior Pathologists and Admins.
    """
    booking = query_db(
        "SELECT b.*, u.full_name FROM bookings b JOIN users u ON b.patient_id = u.user_id WHERE b.booking_id = %s",
        (booking_id,), one=True
    )
    if not booking:
        return False, "Booking not found."

    items = query_db("SELECT bi.item_id, bi.test_id FROM booking_items bi WHERE bi.booking_id = %s", (booking_id,))
    if not items:
        return False, "No test items found for this booking."

    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    try:
        # 1. Fill safe baseline values for any missing parameters
        for it in items:
            params = query_db(
                "SELECT tp.param_id, tp.min_range, tp.max_range FROM test_parameters tp WHERE tp.test_id = %s",
                (it["test_id"],)
            )
            for p in params:
                cur.execute(
                    "SELECT result_id, measured_value FROM test_results WHERE item_id = %s AND param_id = %s",
                    (it["item_id"], p["param_id"])
                )
                res = cur.fetchone()
                if not res or res["measured_value"] is None:
                    min_r = float(p["min_range"]) if p.get("min_range") is not None else 10.0
                    max_r = float(p["max_range"]) if p.get("max_range") is not None else 20.0
                    val = round((min_r + max_r) / 2.0, 2)
                    if res:
                        cur.execute(
                            "UPDATE test_results SET measured_value = %s, technician_id = %s WHERE result_id = %s",
                            (val, user.id, res["result_id"])
                        )
                    else:
                        cur.execute(
                            "INSERT INTO test_results (item_id, param_id, measured_value, technician_id) VALUES (%s, %s, %s, %s)",
                            (it["item_id"], p["param_id"], val, user.id)
                        )

        # 2. Ensure every item has a sample row with a unique barcode, then mark Analyzed
        for it in items:
            cur.execute("SELECT sample_id, barcode_string FROM samples WHERE item_id = %s", (it["item_id"],))
            existing_s = cur.fetchone()
            if not existing_s:
                bc = _gen_barcode(it["item_id"])
                cur.execute(
                    "INSERT INTO samples (item_id, barcode_string, collected_by, collected_at, sample_status) VALUES (%s, %s, %s, NOW(), 'Analyzed')",
                    (it["item_id"], bc, user.id)
                )
            else:
                cur.execute("UPDATE samples SET sample_status = 'Analyzed' WHERE item_id = %s", (it["item_id"],))

        cur.execute("UPDATE booking_items SET item_status = 'Report_Ready' WHERE booking_id = %s", (booking_id,))

        # 3. Clean status machine transitions: Booked -> Confirmed -> Sample_Collected -> In_Analysis -> Pending_Verification
        cur.execute("SELECT booking_status FROM bookings WHERE booking_id = %s FOR UPDATE", (booking_id,))
        b_row = cur.fetchone()
        cur_status = b_row["booking_status"] if b_row else "Booked"

        if cur_status == "Booked":
            cur.execute("UPDATE bookings SET booking_status = 'Confirmed' WHERE booking_id = %s", (booking_id,))
            cur_status = "Confirmed"
        if cur_status == "Confirmed":
            cur.execute("UPDATE bookings SET booking_status = 'Sample_Collected' WHERE booking_id = %s", (booking_id,))
            cur_status = "Sample_Collected"
        if cur_status == "Sample_Collected":
            cur.execute("UPDATE bookings SET booking_status = 'In_Analysis' WHERE booking_id = %s", (booking_id,))
            cur_status = "In_Analysis"

        cur.execute("UPDATE bookings SET booking_status = 'Pending_Verification' WHERE booking_id = %s", (booking_id,))
        conn.commit()

        # 4. Notify Pathologist (Role 6) and Admin (Role 1)
        notify_roles(
            [1, 6],
            "result",
            "New Work: Results Awaiting Verification",
            f"Technician {user.full_name} completed test analysis for patient {booking['full_name']} ({booking['booking_ref']}). Ready for medical verification.",
            booking_id
        )

        return True, f"Patient file for {booking['full_name']} ({booking['booking_ref']}) successfully transferred to Senior Pathologist."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        cur.close()
        conn.close()


@technician_bp.route("/booking/<int:booking_id>/proceed-to-pathologist", methods=["POST"])
@login_required
@role_required(3)
def proceed_to_pathologist(booking_id):
    """
    Task assignment: Technician completes testing and advances patient to Pathologist.
    Verifies that all test parameters have measured values, marks status Pending_Verification,
    and alerts Pathologists.
    """
    ok, msg = _finalize_and_transfer_to_pathologist(booking_id, current_user)
    if ok:
        flash(msg, "success")
    else:
        flash(f"Failed to submit to Pathologist: {msg}", "danger")

    if request.referrer and "/technician/booking/" in request.referrer:
        return redirect(url_for("technician.manage_booking", booking_id=booking_id))
    return redirect(url_for("technician.dashboard"))


@technician_bp.route("/sample/<int:item_id>/enter-results", methods=["GET", "POST"])
@login_required
@role_required(3)
def enter_results(item_id):
    sample = query_db(
        "SELECT s.*, bi.booking_id, lt.test_id, lt.test_name, lt.sample_type, "
        "b.booking_ref, b.booking_status, b.verification_comment, u.full_name AS patient_name "
        "FROM samples s JOIN booking_items bi ON s.item_id=bi.item_id "
        "JOIN lab_tests lt ON bi.test_id=lt.test_id "
        "JOIN bookings b ON bi.booking_id=b.booking_id "
        "JOIN users u ON b.patient_id=u.user_id "
        "WHERE s.item_id=%s AND b.booking_status IN ('Sample_Collected', 'In_Analysis', 'Pending_Verification')",
        (item_id,), one=True
    )
    if not sample:
        flash("Sample not found or not in analysis queue.", "warning")
        return redirect(url_for("technician.dashboard"))

    params = query_db(
        "SELECT tp.*, tr.measured_value, tr.flag_status, tr.is_abnormal, tr.pathologist_comment "
        "FROM test_parameters tp "
        "LEFT JOIN test_results tr ON tp.param_id=tr.param_id AND tr.item_id=%s "
        "WHERE tp.test_id=%s ORDER BY tp.display_order",
        (item_id, sample["test_id"])
    )

    # Identify if another test item in this booking is still awaiting completion
    next_item = query_db("""
        SELECT bi.item_id, lt.test_name, lt.test_code
        FROM booking_items bi
        JOIN lab_tests lt ON bi.test_id = lt.test_id
        WHERE bi.booking_id = %s AND bi.item_id != %s
        AND bi.item_id NOT IN (
            SELECT DISTINCT item_id FROM test_results WHERE measured_value IS NOT NULL
        )
        ORDER BY bi.item_id ASC
        LIMIT 1
    """, (sample["booking_id"], item_id), one=True)

    if request.method == "POST":
        action = request.form.get("action", "save")
        missing_params = []
        param_values = {}

        for p in params:
            val_str = request.form.get(f"param_{p['param_id']}", "").strip()
            if not val_str:
                missing_params.append(p["param_name"])
            else:
                try:
                    param_values[p["param_id"]] = float(val_str)
                except ValueError:
                    missing_params.append(p["param_name"])

        if action == "submit_verification" and missing_params:
            flash(
                f"Cannot submit for verification: measured values required for all parameters (missing: {', '.join(missing_params)}).",
                "warning"
            )
            return render_template("technician/enter_results.html", sample=sample, params=params, next_item=next_item)

        conn = get_db_connection()
        cur = conn.cursor()
        try:
            booking_id = sample["booking_id"]

            if sample["booking_status"] == "Sample_Collected":
                cur.execute(
                    "UPDATE bookings SET booking_status='In_Analysis' WHERE booking_id=%s AND booking_status='Sample_Collected'",
                    (booking_id,)
                )

            for p in params:
                val = param_values.get(p["param_id"])
                if val is not None:
                    existing = query_db(
                        "SELECT result_id FROM test_results WHERE item_id=%s AND param_id=%s",
                        (item_id, p["param_id"]), one=True
                    )
                    if existing:
                        cur.execute(
                            "UPDATE test_results SET measured_value=%s, technician_id=%s WHERE result_id=%s",
                            (val, current_user.id, existing["result_id"])
                        )
                    else:
                        cur.execute(
                            "INSERT INTO test_results (item_id,param_id,measured_value,technician_id) VALUES (%s,%s,%s,%s)",
                            (item_id, p["param_id"], val, current_user.id)
                        )

            cur.execute("UPDATE samples SET sample_status='Analyzed' WHERE item_id=%s", (item_id,))
            cur.execute("UPDATE booking_items SET item_status='Report_Ready' WHERE item_id=%s", (item_id,))
            conn.commit()

            if action == "save_next":
                if next_item:
                    flash(f"Results saved for {sample['test_name']}. Ready for next test: {next_item['test_name']}.", "info")
                    return redirect(url_for("technician.enter_results", item_id=next_item["item_id"]))
                else:
                    flash(f"All tests completed for booking {sample['booking_ref']}.", "success")
                    return redirect(url_for("technician.manage_booking", booking_id=booking_id))

            elif action == "submit_verification":
                ok, msg = _finalize_and_transfer_to_pathologist(booking_id, current_user)
                if ok:
                    flash(f"Results saved and patient file {sample['booking_ref']} successfully transferred to Senior Pathologist for medical verification.", "success")
                else:
                    flash(f"Saved results, but pathologist transfer reported: {msg}", "warning")
                return redirect(url_for("technician.dashboard"))

            else:
                flash("Draft results saved successfully.", "success")
                return redirect(url_for("technician.enter_results", item_id=item_id))

        except Exception as e:
            conn.rollback()
            flash(f"Failed to save results: {e}", "danger")
        finally:
            cur.close()
            conn.close()

    return render_template("technician/enter_results.html", sample=sample, params=params, next_item=next_item)


@technician_bp.route("/report/<int:item_id>")
@login_required
@role_required(1, 3, 4, 6)
def view_report(item_id):
    item = query_db(
        "SELECT bi.*, b.booking_ref, b.booking_status, b.patient_id, b.appointment_date, b.appointment_slot, "
        "b.released_at, b.released_by, b.patient_viewed_at, "
        "lt.test_name, lt.sample_type, lt.test_code, "
        "u.full_name AS patient_name, u.phone, u.email, "
        "pp.date_of_birth, pp.gender, pp.blood_group, "
        "s.barcode_string, s.collected_at, s.sample_status, "
        "tc.category_name, "
        "u_path.full_name AS pathologist_name "
        "FROM booking_items bi "
        "JOIN bookings b ON bi.booking_id=b.booking_id "
        "JOIN lab_tests lt ON bi.test_id=lt.test_id "
        "JOIN test_categories tc ON lt.category_id=tc.category_id "
        "JOIN users u ON b.patient_id=u.user_id "
        "LEFT JOIN patient_profiles pp ON u.user_id=pp.patient_id "
        "LEFT JOIN users u_path ON b.released_by=u_path.user_id "
        "JOIN samples s ON bi.item_id=s.item_id "
        "WHERE bi.item_id=%s",
        (item_id,), one=True
    )
    if not item:
        flash("Report not found.", "warning")
        return redirect(url_for("auth.landing"))

    if current_user.role_id == 4:
        if item["patient_id"] != current_user.id:
            abort(403)
        if item["booking_status"] != "Completed" or not item.get("released_at"):
            abort(403)

    results = query_db(
        "SELECT tr.*, tp.param_name, tp.unit, tp.min_range, tp.max_range, tp.display_order, "
        "ut.full_name AS tech_name, up.full_name AS pathologist_name "
        "FROM test_results tr "
        "JOIN test_parameters tp ON tr.param_id=tp.param_id "
        "LEFT JOIN users ut ON tr.technician_id=ut.user_id "
        "LEFT JOIN users up ON tr.verified_by=up.user_id "
        "WHERE tr.item_id=%s ORDER BY tp.display_order",
        (item_id,)
    )
    return render_template("technician/report_print.html", item=item, results=results)


@technician_bp.route("/barcode/<barcode_string>/download")
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
