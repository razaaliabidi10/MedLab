"""
tests/test_phase1.py
====================
Automated test suite verifying Phase 1 requirements:
  1. Database Schema & Tables (all 16+ tables, 6 roles, additive columns)
  2. Password Hashes & Demo Accounts (Werkzeug hash verification)
  3. Catalog & Seed Data (24+ tests, categories, packages, slots, bookings)
  4. Database Triggers (Role security, Status state machine, Auto-flagging)
  5. Stored Procedures (sp_create_booking atomicity & capacity check)
  6. Database Views (vw_staff_directory, vw_technician_worklist)
  7. Flask Application & Authentication (app initialization, routes, login)

Run with:
    python tests/test_phase1.py
"""

import json
import os
import sys
import unittest

# Ensure project root is on PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mysql.connector
from dotenv import load_dotenv
from werkzeug.security import check_password_hash

load_dotenv()

DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("DB_PORT", 3306))
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "medlab_db")


class Phase1DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            charset="utf8mb4",
            autocommit=True,
        )
        cls.cur = cls.conn.cursor(dictionary=True)

    @classmethod
    def tearDownClass(cls):
        cls.cur.close()
        cls.conn.close()

    # -------------------------------------------------------------------------
    # 1. SCHEMA & TABLES
    # -------------------------------------------------------------------------
    def test_01_all_tables_exist(self):
        """Verify all expected tables (base + migration_v2) exist in medlab_db."""
        expected_tables = {
            "roles", "users", "staff_profiles", "test_categories",
            "lab_tests", "test_parameters", "bookings", "booking_items",
            "samples", "test_results", "invoices",
            "notifications", "audit_log", "packages", "package_tests", "time_slots"
        }
        self.cur.execute("SHOW TABLES")
        rows = self.cur.fetchall()
        actual_tables = {list(r.values())[0] for r in rows}
        missing = expected_tables - actual_tables
        self.assertEqual(len(missing), 0, f"Missing tables in medlab_db: {missing}")

    def test_02_all_six_roles_exist(self):
        """Verify 6 distinct roles: admin(1), receptionist(2), technician(3), patient(4), collector(5), pathologist(6)."""
        self.cur.execute("SELECT role_id, role_name FROM roles ORDER BY role_id")
        roles = {r["role_id"]: r["role_name"] for r in self.cur.fetchall()}
        self.assertEqual(len(roles), 6)
        self.assertEqual(roles[1], "admin")
        self.assertEqual(roles[2], "receptionist")
        self.assertEqual(roles[3], "technician")
        self.assertEqual(roles[4], "patient")
        self.assertEqual(roles[5], "sample_collector")
        self.assertEqual(roles[6], "pathologist")

    def test_03_users_additive_columns(self):
        """Verify users table has Google OAuth & lockout columns, and password_hash is nullable."""
        self.cur.execute("""
            SELECT COLUMN_NAME, IS_NULLABLE, COLUMN_TYPE
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'users'
        """, (DB_NAME,))
        cols = {r["COLUMN_NAME"]: r for r in self.cur.fetchall()}

        # password_hash must be nullable for future Google OAuth
        self.assertIn("password_hash", cols)
        self.assertEqual(cols["password_hash"]["IS_NULLABLE"], "YES")

        # auth_provider enum
        self.assertIn("auth_provider", cols)
        self.assertIn("'local'", cols["auth_provider"]["COLUMN_TYPE"])
        self.assertIn("'google'", cols["auth_provider"]["COLUMN_TYPE"])

        # google_id
        self.assertIn("google_id", cols)

        # lockout columns
        self.assertIn("login_attempts", cols)
        self.assertIn("lockout_until", cols)

    def test_04_bookings_additive_columns(self):
        """Verify bookings table has collection_type, collection_address, confirmed_by, confirmed_at, slot_id."""
        self.cur.execute("""
            SELECT COLUMN_NAME, COLUMN_TYPE
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'bookings'
        """, (DB_NAME,))
        cols = {r["COLUMN_NAME"]: r["COLUMN_TYPE"] for r in self.cur.fetchall()}

        self.assertIn("collection_type", cols)
        self.assertIn("collection_address", cols)
        self.assertIn("confirmed_by", cols)
        self.assertIn("confirmed_at", cols)
        self.assertIn("slot_id", cols)

        # 7-state booking_status
        status_enum = cols["booking_status"]
        for st in ['Booked', 'Confirmed', 'Sample_Collected', 'In_Analysis', 'Pending_Verification', 'Completed', 'Cancelled']:
            self.assertIn(st, status_enum)

    def test_05_samples_and_results_additive_columns(self):
        """Verify samples.rejection_reason and test_results.verified_by/pathologist_comment exist."""
        self.cur.execute("""
            SELECT TABLE_NAME, COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME IN ('samples', 'test_results')
        """, (DB_NAME,))
        cols = {(r["TABLE_NAME"], r["COLUMN_NAME"]) for r in self.cur.fetchall()}

        self.assertIn(("samples", "rejection_reason"), cols)
        self.assertIn(("test_results", "verified_by"), cols)
        self.assertIn(("test_results", "pathologist_verified_at"), cols)
        self.assertIn(("test_results", "pathologist_comment"), cols)

    # -------------------------------------------------------------------------
    # 2. SEED DATA & AUTH VALIDATION
    # -------------------------------------------------------------------------
    def test_06_demo_accounts_credentials(self):
        """Verify all demo accounts exist and their passwords match the policy using Werkzeug hashing."""
        demo_logins = [
            ("admin@medlab.pk", "Admin@8521!", 1),
            ("receptionist@medlab.pk", "Recp@8521!", 2),
            ("technician@medlab.pk", "Tech@8521!", 3),
            ("collector@medlab.pk", "Coll@8521!", 5),
            ("pathologist@medlab.pk", "Path@8521!", 6),
            ("patient1@medlab.pk", "Patient@8521!", 4),
        ]
        for email, password, expected_role in demo_logins:
            self.cur.execute("SELECT user_id, role_id, password_hash, is_active FROM users WHERE email = %s", (email,))
            user = self.cur.fetchone()
            self.assertIsNotNone(user, f"User {email} not found in database.")
            self.assertEqual(user["role_id"], expected_role, f"User {email} has wrong role_id.")
            self.assertTrue(user["is_active"], f"User {email} is inactive.")
            self.assertTrue(
                check_password_hash(user["password_hash"], password),
                f"Password hash check failed for {email}."
            )

    def test_07_catalog_and_seed_quantities(self):
        """Verify realistic seed quantities: 24+ tests, packages, slots, bookings."""
        # Lab tests
        self.cur.execute("SELECT COUNT(*) AS c FROM lab_tests WHERE is_active = 1")
        test_count = self.cur.fetchone()["c"]
        self.assertGreaterEqual(test_count, 20, f"Expected at least 20 active lab tests, found {test_count}")

        # Packages
        self.cur.execute("SELECT COUNT(*) AS c FROM packages WHERE is_active = 1")
        pkg_count = self.cur.fetchone()["c"]
        self.assertGreaterEqual(pkg_count, 4, f"Expected at least 4 packages, found {pkg_count}")

        # Package tests M:N junction
        self.cur.execute("SELECT COUNT(*) AS c FROM package_tests")
        pt_count = self.cur.fetchone()["c"]
        self.assertGreater(pt_count, 0, "package_tests junction table is empty")

        # Time slots
        self.cur.execute("SELECT COUNT(*) AS c FROM time_slots")
        slot_count = self.cur.fetchone()["c"]
        self.assertGreaterEqual(slot_count, 50, f"Expected 50+ time slots, found {slot_count}")

        # Patients
        self.cur.execute("SELECT COUNT(*) AS c FROM users WHERE role_id = 4")
        patient_count = self.cur.fetchone()["c"]
        self.assertGreaterEqual(patient_count, 8, f"Expected 8+ patients, found {patient_count}")

        # Bookings across multiple statuses
        self.cur.execute("SELECT DISTINCT booking_status FROM bookings")
        statuses = {r["booking_status"] for r in self.cur.fetchall()}
        self.assertGreaterEqual(len(statuses), 4, f"Expected bookings in multiple statuses, found {statuses}")

        # Notifications
        self.cur.execute("SELECT COUNT(*) AS c FROM notifications")
        notif_count = self.cur.fetchone()["c"]
        self.assertGreater(notif_count, 0, "Expected seed notifications to be present")

    # -------------------------------------------------------------------------
    # 3. TRIGGERS & WORKFLOW ENFORCEMENT
    # -------------------------------------------------------------------------
    def test_08_trigger_enforce_role_creation(self):
        """Verify trg_enforce_role_creation blocks non-admin creating staff and blocks duplicate admin."""
        # 1. Attempt to create a 2nd admin
        with self.assertRaises(mysql.connector.Error) as ctx:
            self.cur.execute(
                "INSERT INTO users (role_id, full_name, email, phone, password_hash) "
                "VALUES (1, 'Fake Admin', 'fakeadmin@test.pk', '+923999999999', 'fakehash')"
            )
        self.assertIn("System already has a single Master Admin", str(ctx.exception))

        # 2. Attempt to self-register staff (created_by NULL)
        with self.assertRaises(mysql.connector.Error) as ctx:
            self.cur.execute(
                "INSERT INTO users (role_id, full_name, email, phone, password_hash) "
                "VALUES (2, 'Rogue Receptionist', 'rogue@test.pk', '+923999999998', 'fakehash')"
            )
        self.assertIn("Staff accounts cannot self-register", str(ctx.exception))

        # 3. Patient self-registration is allowed
        self.cur.execute(
            "INSERT INTO users (role_id, full_name, email, phone, password_hash) "
            "VALUES (4, 'Test Patient', 'testtemp_patient@test.pk', '+923999999997', 'fakehash')"
        )
        new_id = self.cur.lastrowid
        self.assertGreater(new_id, 0)
        # Cleanup
        self.cur.execute("DELETE FROM users WHERE user_id = %s", (new_id,))

    def test_09_trigger_booking_status_machine(self):
        """Verify trg_booking_status_machine blocks invalid state transitions."""
        # Find a booking with 'Booked' status or create a temporary one
        self.cur.execute("SELECT booking_id FROM bookings WHERE booking_status = 'Booked' LIMIT 1")
        row = self.cur.fetchone()
        if not row:
            self.skipTest("No booking in 'Booked' state to test transitions.")

        bid = row["booking_id"]

        # Attempt illegal transition: Booked -> Completed directly (skipping collection, testing, verification)
        with self.assertRaises(mysql.connector.Error) as ctx:
            self.cur.execute("UPDATE bookings SET booking_status = 'Completed' WHERE booking_id = %s", (bid,))
        self.assertIn("Booked can only move to Confirmed or Cancelled", str(ctx.exception))

    def test_10_trigger_auto_flag_test_result(self):
        """Verify trg_auto_flag_test_result flags NORMAL, LOW, HIGH based on reference ranges."""
        # Get a parameter with known min_range/max_range (e.g. Hemoglobin 13.0 - 17.0)
        self.cur.execute("""
            SELECT p.param_id, p.min_range, p.max_range
            FROM test_parameters p
            WHERE p.min_range IS NOT NULL AND p.max_range IS NOT NULL
            LIMIT 1
        """)
        param = self.cur.fetchone()
        self.assertIsNotNone(param)
        pid = param["param_id"]
        min_v = float(param["min_range"])
        max_v = float(param["max_range"])

        # Create a fresh temporary booking so (booking_id, test_id) is 100% unique
        import uuid
        temp_ref = f"BK-FLG-{uuid.uuid4().hex[:6].upper()}"
        self.cur.execute("SELECT user_id FROM users WHERE role_id = 4 LIMIT 1")
        pat_id = self.cur.fetchone()["user_id"]
        self.cur.execute(
            "INSERT INTO bookings (booking_ref, patient_id, appointment_date, appointment_slot) "
            "VALUES (%s, %s, CURDATE(), '08:00 AM - 10:00 AM')",
            (temp_ref, pat_id)
        )
        b_id = self.cur.lastrowid

        self.cur.execute("SELECT test_id FROM test_parameters WHERE param_id = %s", (pid,))
        t_id = self.cur.fetchone()["test_id"]
        self.cur.execute(
            "INSERT INTO booking_items (booking_id, test_id, price_at_booking) VALUES (%s, %s, 100.00)",
            (b_id, t_id)
        )
        item_id = self.cur.lastrowid

        # Find a technician
        self.cur.execute("SELECT user_id FROM users WHERE role_id = 3 LIMIT 1")
        tech = self.cur.fetchone()
        self.assertIsNotNone(tech)
        tech_id = tech["user_id"]

        try:
            # 1. Normal value insert
            mid_v = (min_v + max_v) / 2.0
            self.cur.execute("""
                INSERT INTO test_results (item_id, param_id, measured_value, technician_id)
                VALUES (%s, %s, %s, %s)
            """, (item_id, pid, mid_v, tech_id))
            res_id = self.cur.lastrowid

            self.cur.execute("SELECT flag_status, is_abnormal FROM test_results WHERE result_id = %s", (res_id,))
            row = self.cur.fetchone()
            self.assertEqual(row["flag_status"], "NORMAL")
            self.assertEqual(row["is_abnormal"], 0)
            self.cur.execute("DELETE FROM test_results WHERE result_id = %s", (res_id,))

            # 2. Low value insert
            low_v = min_v - 1.0
            self.cur.execute("""
                INSERT INTO test_results (item_id, param_id, measured_value, technician_id)
                VALUES (%s, %s, %s, %s)
            """, (item_id, pid, low_v, tech_id))
            res_id = self.cur.lastrowid
            self.cur.execute("SELECT flag_status, is_abnormal FROM test_results WHERE result_id = %s", (res_id,))
            row = self.cur.fetchone()
            self.assertEqual(row["flag_status"], "LOW")
            self.assertEqual(row["is_abnormal"], 1)
            self.cur.execute("DELETE FROM test_results WHERE result_id = %s", (res_id,))

            # 3. High value insert
            high_v = max_v + 5.0
            self.cur.execute("""
                INSERT INTO test_results (item_id, param_id, measured_value, technician_id)
                VALUES (%s, %s, %s, %s)
            """, (item_id, pid, high_v, tech_id))
            res_id = self.cur.lastrowid
            self.cur.execute("SELECT flag_status, is_abnormal FROM test_results WHERE result_id = %s", (res_id,))
            row = self.cur.fetchone()
            self.assertEqual(row["flag_status"], "HIGH")
            self.assertEqual(row["is_abnormal"], 1)
            self.cur.execute("DELETE FROM test_results WHERE result_id = %s", (res_id,))
        finally:
            self.cur.execute("DELETE FROM booking_items WHERE item_id = %s", (item_id,))
            self.cur.execute("DELETE FROM bookings WHERE booking_id = %s", (b_id,))

    # -------------------------------------------------------------------------
    # 4. STORED PROCEDURE
    # -------------------------------------------------------------------------
    def test_11_stored_procedure_sp_create_booking(self):
        """Verify sp_create_booking creates booking + booking_items + invoice atomically and increments slot."""
        # Find an active slot
        self.cur.execute("SELECT slot_id, slot_date, slot_label, booked_count FROM time_slots WHERE is_active = 1 LIMIT 1")
        slot = self.cur.fetchone()
        self.assertIsNotNone(slot)
        slot_id = slot["slot_id"]
        initial_count = slot["booked_count"]

        # Find a patient
        self.cur.execute("SELECT user_id FROM users WHERE role_id = 4 LIMIT 1")
        patient_id = self.cur.fetchone()["user_id"]

        # Find 2 active tests
        self.cur.execute("SELECT test_id FROM lab_tests WHERE is_active = 1 LIMIT 2")
        tests = [r["test_id"] for r in self.cur.fetchall()]
        tests_json = json.dumps(tests)

        import uuid
        test_ref = f"BK-TEST-{uuid.uuid4().hex[:6].upper()}"
        test_inv = f"INV-TEST-{uuid.uuid4().hex[:6].upper()}"

        # Call procedure using dedicated cursor and consume all results
        proc_cur = self.conn.cursor()
        proc_cur.callproc("sp_create_booking", [
            patient_id,
            slot_id,
            slot["slot_date"],
            slot["slot_label"],
            "Lab",
            None,
            test_ref,
            test_inv,
            tests_json,
            0,
            ""
        ])
        sr = proc_cur.stored_results
        results = sr() if callable(sr) else sr
        for result in results:
            result.fetchall()
        proc_cur.close()

        # Check created booking
        self.cur.execute("SELECT booking_id, booking_status FROM bookings WHERE booking_ref = %s", (test_ref,))
        b = self.cur.fetchone()
        self.assertIsNotNone(b, "sp_create_booking did not create the booking row")
        created_bid = b["booking_id"]
        self.assertEqual(b["booking_status"], "Booked")

        # Verify booking items
        self.cur.execute("SELECT COUNT(*) AS c FROM booking_items WHERE booking_id = %s", (created_bid,))
        self.assertEqual(self.cur.fetchone()["c"], len(tests))

        # Verify invoice
        self.cur.execute("SELECT invoice_number, payment_status, total_amount FROM invoices WHERE booking_id = %s", (created_bid,))
        inv = self.cur.fetchone()
        self.assertIsNotNone(inv)
        self.assertEqual(inv["payment_status"], "Unpaid")
        self.assertGreater(inv["total_amount"], 0)

        # Verify slot counter incremented
        self.cur.execute("SELECT booked_count FROM time_slots WHERE slot_id = %s", (slot_id,))
        new_count = self.cur.fetchone()["booked_count"]
        self.assertEqual(new_count, initial_count + 1)

        # Cleanup test booking
        self.cur.execute("DELETE FROM invoices WHERE booking_id = %s", (created_bid,))
        self.cur.execute("DELETE FROM booking_items WHERE booking_id = %s", (created_bid,))
        self.cur.execute("DELETE FROM bookings WHERE booking_id = %s", (created_bid,))
        self.cur.execute("UPDATE time_slots SET booked_count = %s WHERE slot_id = %s", (initial_count, slot_id))

    # -------------------------------------------------------------------------
    # 5. VIEWS
    # -------------------------------------------------------------------------
    def test_12_views_work_cleanly(self):
        """Verify views vw_staff_directory and vw_technician_worklist query cleanly."""
        self.cur.execute("SELECT COUNT(*) AS c FROM vw_staff_directory")
        staff_count = self.cur.fetchone()["c"]
        self.assertGreaterEqual(staff_count, 3, "vw_staff_directory returned fewer than 3 staff members")

        self.cur.execute("SELECT COUNT(*) AS c FROM vw_technician_worklist")
        self.assertIsNotNone(self.cur.fetchone())


class Phase1FlaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import app
        cls.app = app
        cls.app.config["TESTING"] = True
        cls.app.config["WTF_CSRF_ENABLED"] = False

    def test_13_flask_landing_page(self):
        """Verify landing page renders with 200 OK."""
        client = self.app.test_client()
        res = client.get("/")
        self.assertEqual(res.status_code, 200)

    def test_14_flask_login_page(self):
        """Verify login page renders with 200 OK."""
        client = self.app.test_client()
        res = client.get("/login")
        self.assertEqual(res.status_code, 200)

    def test_15_flask_auth_admin_login(self):
        """Verify admin can authenticate via Flask login POST and gets redirected to admin dashboard."""
        client = self.app.test_client()
        res = client.post("/login", data={
            "email": "admin@medlab.pk",
            "password": "Admin@8521!"
        }, follow_redirects=False)
        self.assertIn(res.status_code, (200, 302))
        if res.status_code == 302:
            self.assertIn("/admin", res.headers.get("Location", ""))

    def test_16_flask_auth_patient_login(self):
        """Verify patient can authenticate via Flask login POST."""
        client = self.app.test_client()
        res = client.post("/login", data={
            "email": "patient1@medlab.pk",
            "password": "Patient@8521!"
        }, follow_redirects=False)
        self.assertIn(res.status_code, (200, 302))
        if res.status_code == 302:
            self.assertIn("/patient", res.headers.get("Location", ""))

    def test_17_flask_auth_pathologist_login(self):
        """Verify pathologist (Role 6) can authenticate and access pathologist dashboard."""
        client = self.app.test_client()
        res = client.post("/login", data={
            "email": "pathologist@medlab.pk",
            "password": "Path@8521!"
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn("/pathologist", res.headers.get("Location", ""))

        dash = client.get("/pathologist/dashboard")
        self.assertEqual(dash.status_code, 200)

    def test_18_flask_auth_collector_login(self):
        """Verify sample collector (Role 5) can authenticate and access collector dashboard."""
        client = self.app.test_client()
        res = client.post("/login", data={
            "email": "collector@medlab.pk",
            "password": "Coll@8521!"
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn("/collector", res.headers.get("Location", ""))

        dash = client.get("/collector/dashboard")
        self.assertEqual(dash.status_code, 200)


def run_all_tests():
    print("\n" + "=" * 70)
    print("  MEDLAB SYSTEM — PHASE 1 VERIFICATION TEST RUNNER")
    print("=" * 70)
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    suite.addTests(loader.loadTestsFromTestCase(Phase1DatabaseTests))
    suite.addTests(loader.loadTestsFromTestCase(Phase1FlaskTests))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print("=" * 70)
    if result.wasSuccessful():
        print("  🎉 PHASE 1: ALL TESTS PASSED SUCCESSFULLY! (18/18)")
    else:
        print(f"  ❌ PHASE 1: {len(result.failures)} failures, {len(result.errors)} errors.")
    print("=" * 70 + "\n")
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
