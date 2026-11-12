"""
tests/test_phase4_spec.py
=========================
Specification tests for Phase 4:
  1. DB Schema: bookings & test_results have released_at, released_by, patient_viewed_at, verification_comment
  2. Technician workflow: enter results, validate missing params, submit for verification moves to Pending_Verification
  3. Technician cannot approve or release or set Completed
  4. Pathologist send back requires comment, moves to In_Analysis, records comment
  5. Pathologist approve sets released_at/released_by, moves to Completed, creates REPORT_READY notification
  6. Patient reports page (/patient/reports) lists released reports
  7. IDOR protection: patient cannot view another patient's report (403)
  8. Unreleased report protection: patient cannot view report before Completed / released_at (403)
  9. Viewing report sets patient_viewed_at and dismisses dashboard ready alert
"""

import unittest
import sys
import os
from datetime import datetime
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
import db


class Phase4ReportFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.app.config["WTF_CSRF_ENABLED"] = False

    def setUp(self):
        # Create fresh test client per test method to prevent cookie leakage
        self.client = self.app.test_client()

    def _login(self, email, password):
        self.client.get("/logout", follow_redirects=True)
        return self.client.post("/login", data={"email": email, "password": password}, follow_redirects=True)

    def test_01_schema_has_phase4_columns(self):
        """Verify bookings and test_results have all required Phase 4 tracking columns."""
        with self.app.app_context():
            conn = db.get_db_connection()
            cur = conn.cursor(dictionary=True)
            cur.execute("DESCRIBE bookings")
            booking_cols = {r["Field"] for r in cur.fetchall()}
            self.assertIn("released_at", booking_cols)
            self.assertIn("released_by", booking_cols)
            self.assertIn("patient_viewed_at", booking_cols)
            self.assertIn("verification_comment", booking_cols)

            cur.execute("DESCRIBE test_results")
            tr_cols = {r["Field"] for r in cur.fetchall()}
            self.assertIn("released_at", tr_cols)
            self.assertIn("released_by", tr_cols)
            self.assertIn("verification_comment", tr_cols)
            conn.close()

    def test_02_technician_cannot_access_pathologist_approval(self):
        """Technician (role 3) must receive 403 Forbidden when trying to access pathologist approve."""
        self._login("technician@medlab.pk", "Tech@8521!")
        res = self.client.post("/pathologist/approve/1", follow_redirects=False)
        self.assertEqual(res.status_code, 403)

    def test_03_patient_idor_protection(self):
        """Patient 2 (user 7) cannot access Patient 1's (user 6) report (booking 1). Must return 403."""
        # Patient 2 is patient2@medlab.pk (booking 2 is theirs, booking 1 belongs to patient 1)
        self._login("patient2@medlab.pk", "Patient@8521!")
        res = self.client.get("/patient/reports/1", follow_redirects=False)
        self.assertEqual(res.status_code, 403)

    def test_04_patient_cannot_view_unreleased_report(self):
        """Patient cannot view report for booking that is not Completed / released (returns 403)."""
        # Booking 9 is Confirmed (not Completed) and belongs to patient 1 (user 6)
        self._login("patient1@medlab.pk", "Patient@8521!")
        res = self.client.get("/patient/reports/9", follow_redirects=False)
        self.assertEqual(res.status_code, 403)

    def test_05_patient_reports_page_accessible(self):
        """Patient can access /patient/reports and see their completed reports."""
        self._login("patient1@medlab.pk", "Patient@8521!")
        res = self.client.get("/patient/reports")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"BK-SEED-0001", res.data)
        self.assertIn(b"View &amp; Print", res.data)

    def test_06_patient_view_report_sets_viewed_at(self):
        """Viewing report sets patient_viewed_at on booking."""
        with self.app.app_context():
            # Reset patient_viewed_at for booking 1
            db.execute_db("UPDATE bookings SET patient_viewed_at = NULL WHERE booking_id = 1")

        self._login("patient1@medlab.pk", "Patient@8521!")
        res = self.client.get("/patient/reports/1")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"MedLab Diagnostics", res.data)
        self.assertIn(b"Verified &amp; Released", res.data)

        # Check that patient_viewed_at was set
        with self.app.app_context():
            b = db.query_db("SELECT patient_viewed_at FROM bookings WHERE booking_id = 1", one=True)
            self.assertIsNotNone(b["patient_viewed_at"])

    def test_07_end_to_end_report_lifecycle(self):
        """
        Complete lifecycle test:
        1. Book test as patient 1
        2. Mark confirmed by receptionist / cash paid
        3. Collect sample by collector -> Sample_Collected
        4. Technician enters results & submits for verification -> Pending_Verification
        5. Pathologist sends back with comment -> In_Analysis
        6. Technician resubmits -> Pending_Verification
        7. Pathologist approves -> Completed, notification REPORT_READY sent
        8. Patient views report -> patient_viewed_at recorded
        """
        # Step 1: Create a fresh booking for patient 1
        with self.app.app_context():
            booking_ref = f"BK-TEST-{int(datetime.now().timestamp())}"
            b_id = db.execute_db(
                "INSERT INTO bookings (booking_ref, patient_id, appointment_date, appointment_slot, booking_status) "
                "VALUES (%s, 6, CURDATE(), '08:00 AM - 10:00 AM', 'Confirmed')",
                (booking_ref,)
            )
            item_id = db.execute_db(
                "INSERT INTO booking_items (booking_id, test_id, price_at_booking, item_status) "
                "VALUES (%s, 1, 1200.00, 'Pending_Sample')",
                (b_id,)
            )

        # Step 2: Collector marks collected
        self._login("collector@medlab.pk", "Coll@8521!")
        res = self.client.post(f"/collector/collect/{b_id}", follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        with self.app.app_context():
            b = db.query_db("SELECT booking_status FROM bookings WHERE booking_id = %s", (b_id,), one=True)
            self.assertEqual(b["booking_status"], "Sample_Collected")

        # Step 3: Technician opens and submits for verification
        self._login("technician@medlab.pk", "Tech@8521!")
        # First test validation failure if params missing
        res_fail = self.client.post(
            f"/technician/sample/{item_id}/enter-results",
            data={"action": "submit_verification"},
            follow_redirects=True
        )
        self.assertIn(b"Cannot submit for verification", res_fail.data)

        # Submit with all 5 CBC parameters (param_id 1 to 5)
        res_tech = self.client.post(
            f"/technician/sample/{item_id}/enter-results",
            data={
                "action": "submit_verification",
                "param_1": "14.5",
                "param_2": "7.5",
                "param_3": "250",
                "param_4": "5.0",
                "param_5": "45.0"
            },
            follow_redirects=True
        )
        self.assertEqual(res_tech.status_code, 200)

        with self.app.app_context():
            b = db.query_db("SELECT booking_status FROM bookings WHERE booking_id = %s", (b_id,), one=True)
            self.assertEqual(b["booking_status"], "Pending_Verification")

        # Step 4: Pathologist sends back with comment
        self._login("pathologist@medlab.pk", "Path@8521!")
        # Send back without comment should fail
        res_empty = self.client.post(f"/pathologist/send-back/{b_id}", data={"pathologist_comment": ""}, follow_redirects=True)
        self.assertIn(b"Please provide a reason", res_empty.data)

        # Send back with comment
        res_sendback = self.client.post(
            f"/pathologist/send-back/{b_id}",
            data={"pathologist_comment": "Please re-check Platelet count, sample shows possible clumping."},
            follow_redirects=True
        )
        self.assertEqual(res_sendback.status_code, 200)

        with self.app.app_context():
            b = db.query_db("SELECT booking_status, verification_comment FROM bookings WHERE booking_id = %s", (b_id,), one=True)
            self.assertEqual(b["booking_status"], "In_Analysis")
            self.assertIn("clumping", b["verification_comment"])

        # Step 5: Technician sees revision request and re-submits
        self._login("technician@medlab.pk", "Tech@8521!")
        res_view = self.client.get(f"/technician/sample/{item_id}/enter-results")
        self.assertIn(b"Pathologist Revision Note", res_view.data)

        res_resubmit = self.client.post(
            f"/technician/sample/{item_id}/enter-results",
            data={
                "action": "submit_verification",
                "param_1": "14.5",
                "param_2": "7.5",
                "param_3": "265",
                "param_4": "5.0",
                "param_5": "45.0"
            },
            follow_redirects=True
        )
        self.assertEqual(res_resubmit.status_code, 200)

        with self.app.app_context():
            b = db.query_db("SELECT booking_status FROM bookings WHERE booking_id = %s", (b_id,), one=True)
            self.assertEqual(b["booking_status"], "Pending_Verification")

        # Step 6: Pathologist approves and releases report
        self._login("pathologist@medlab.pk", "Path@8521!")
        res_approve = self.client.post(f"/pathologist/approve/{b_id}", follow_redirects=True)
        self.assertEqual(res_approve.status_code, 200)

        with self.app.app_context():
            b = db.query_db("SELECT booking_status, released_at, released_by FROM bookings WHERE booking_id = %s", (b_id,), one=True)
            self.assertEqual(b["booking_status"], "Completed")
            self.assertIsNotNone(b["released_at"])
            self.assertIsNotNone(b["released_by"])

            # Check REPORT_READY notification was created for patient 6
            n = db.query_db(
                "SELECT * FROM notifications WHERE user_id = 6 AND booking_id = %s AND type = 'REPORT_READY'",
                (b_id,), one=True
            )
            self.assertIsNotNone(n)

        # Step 7: Patient views report
        self._login("patient1@medlab.pk", "Patient@8521!")
        res_rep = self.client.get(f"/patient/reports/{b_id}")
        self.assertEqual(res_rep.status_code, 200)
        self.assertIn(b"MedLab Diagnostics", res_rep.data)
        self.assertIn(b"265", res_rep.data)  # updated platelet count

        with self.app.app_context():
            b = db.query_db("SELECT patient_viewed_at FROM bookings WHERE booking_id = %s", (b_id,), one=True)
            self.assertIsNotNone(b["patient_viewed_at"])


if __name__ == "__main__":
    unittest.main()
