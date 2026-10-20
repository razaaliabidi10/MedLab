from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from db import query_db, execute_db, get_db_connection
from models import role_required

technician_bp = Blueprint("technician", __name__, url_prefix="/technician")


@technician_bp.route("/dashboard")
@login_required
@role_required(3)
def dashboard():
    worklist = query_db("SELECT * FROM vw_technician_worklist ORDER BY collected_at ASC")
    return render_template("technician/dashboard.html", worklist=worklist)


@technician_bp.route("/sample/<int:item_id>/enter-results", methods=["GET", "POST"])
@login_required
@role_required(3)
def enter_results(item_id):
    sample = query_db(
        "SELECT s.*, bi.booking_id, lt.test_id, lt.test_name, lt.sample_type, "
        "b.booking_ref, u.full_name AS patient_name "
        "FROM samples s JOIN booking_items bi ON s.item_id=bi.item_id "
        "JOIN lab_tests lt ON bi.test_id=lt.test_id "
        "JOIN bookings b ON bi.booking_id=b.booking_id "
        "JOIN users u ON b.patient_id=u.user_id "
        "WHERE s.item_id=%s AND s.sample_status='Collected'",
        (item_id,), one=True
    )
    if not sample:
        flash("Sample not found or already analyzed.", "warning")
        return redirect(url_for("technician.dashboard"))

    params = query_db(
        "SELECT tp.*, tr.measured_value, tr.flag_status, tr.is_abnormal "
        "FROM test_parameters tp "
        "LEFT JOIN test_results tr ON tp.param_id=tr.param_id AND tr.item_id=%s "
        "WHERE tp.test_id=%s ORDER BY tp.display_order",
        (item_id, sample["test_id"])
    )

    if request.method == "POST":
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            for p in params:
                val_str = request.form.get(f"param_{p['param_id']}", "").strip()
                if not val_str:
                    continue
                val = float(val_str)
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

            # Update sample and item status
            cur.execute("UPDATE samples SET sample_status='Analyzed' WHERE item_id=%s", (item_id,))
            cur.execute("UPDATE booking_items SET item_status='Report_Ready' WHERE item_id=%s", (item_id,))

            # Check if ALL items in booking are analyzed → move booking to Pending_Verification for Pathologist
            booking_id = sample["booking_id"]
            not_ready = query_db(
                "SELECT COUNT(*) AS cnt FROM booking_items WHERE booking_id=%s AND item_status != 'Report_Ready'",
                (booking_id,), one=True
            )
            if not_ready and not_ready["cnt"] == 0:
                # First ensure it transitioned to In_Analysis if still in Sample_Collected
                cur.execute(
                    "UPDATE bookings SET booking_status='In_Analysis' WHERE booking_id=%s AND booking_status='Sample_Collected'",
                    (booking_id,)
                )
                cur.execute("UPDATE bookings SET booking_status='Pending_Verification' WHERE booking_id=%s", (booking_id,))

            conn.commit()
            flash("Results saved successfully. Report submitted to Pathologist for verification.", "success")
            return redirect(url_for("technician.dashboard"))
        except Exception as e:
            conn.rollback()
            flash(f"Failed to save results: {e}", "danger")
        finally:
            cur.close(); conn.close()

    return render_template("technician/enter_results.html", sample=sample, params=params)


@technician_bp.route("/report/<int:item_id>")
@login_required
def view_report(item_id):
    # Accessible by patient (owner), technician, admin
    item = query_db(
        "SELECT bi.*, b.booking_ref, b.patient_id, b.appointment_date, b.appointment_slot, "
        "lt.test_name, lt.sample_type, lt.test_code, "
        "u.full_name AS patient_name, u.phone, u.email, "
        "pp.date_of_birth, pp.gender, pp.blood_group, "
        "s.barcode_string, s.collected_at, s.sample_status, "
        "tc.category_name "
        "FROM booking_items bi "
        "JOIN bookings b ON bi.booking_id=b.booking_id "
        "JOIN lab_tests lt ON bi.test_id=lt.test_id "
        "JOIN test_categories tc ON lt.category_id=tc.category_id "
        "JOIN users u ON b.patient_id=u.user_id "
        "LEFT JOIN patient_profiles pp ON u.user_id=pp.patient_id "
        "JOIN samples s ON bi.item_id=s.item_id "
        "WHERE bi.item_id=%s AND bi.item_status='Report_Ready'",
        (item_id,), one=True
    )
    if not item:
        flash("Report not available yet or sample not found.", "warning")
        return redirect(url_for("auth.landing"))

    # IDOR check: patient can only see their own report
    if current_user.role_id == 4 and item["patient_id"] != current_user.id:
        abort(403)

    results = query_db(
        "SELECT tr.*, tp.param_name, tp.unit, tp.min_range, tp.max_range, tp.display_order, "
        "ut.full_name AS tech_name "
        "FROM test_results tr "
        "JOIN test_parameters tp ON tr.param_id=tp.param_id "
        "JOIN users ut ON tr.technician_id=ut.user_id "
        "WHERE tr.item_id=%s ORDER BY tp.display_order",
        (item_id,)
    )
    return render_template("technician/report_print.html", item=item, results=results)
