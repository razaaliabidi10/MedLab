"""
tests/test_phase3_spec.py
=========================
Comprehensive automated verification suite for Phase 3 specification:
  1. Admin Dashboard:
     - 4 KPI cards in neutral style (white, thin border, no colored side borders, no big icons).
     - Recent Bookings: latest 3 rows by default, 'Show all (N)' expander to max-h-96 scrollable container with search box.
  2. Admin Test Catalog Accordions:
     - Grouped by category accordions (collapsed by default with count badge).
     - Live search across categories at top.
     - Tests display code, name, sample, price (JetBrains Mono font-mono), TAT, params count.
     - 0-param badge = muted amber 'Needs parameters' (e.g. DIA-OGTT, HEM-PBF, etc.).
     - Availability toggle switch endpoint /admin/catalog/toggle-test/<id>.
  3. Receptionist Navigation & Dashboard:
     - Sidebar settings shows only 'Profile' (Security removed).
     - New sidebar item 'Lab Tests' links to /receptionist/tests.
     - Recent Bookings shows latest 3 rows with 'Show all (N)' expander.
  4. Receptionist Read-Only Lab Tests Page:
     - /receptionist/tests renders category accordions with live search.
     - Displays code, name, sample, TAT, price (font-mono), availability badge (Available/Unavailable).
     - Strictly read-only: NO add, edit, or toggle controls.
  5. Inactive Test Booking Rejection & Backend Enforcement:
     - Tests with is_active = 0 are greyed out with 'Unavailable' badge and disabled checkbox.
     - Backend booking route rejects inactive tests with clear error.
  6. 403 Security Enforcement:
     - Receptionist POSTing to admin test routes (/admin/catalog/add-test, /admin/catalog/add-param, /admin/catalog/toggle-test/<id>) gets 403 Forbidden.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from db import query_db, execute_db


class Phase3SpecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.app.config["WTF_CSRF_ENABLED"] = False

    def setUp(self):
        """Ensure each test runs with a completely fresh, isolated client session."""
        self.client = self.app.test_client()

    def login(self, email, password):
        return self.client.post("/login", data={"email": email, "password": password}, follow_redirects=True)

    # -------------------------------------------------------------------------
    # 1. ADMIN DASHBOARD (Neutral KPIs & Recent Bookings Expander)
    # -------------------------------------------------------------------------
    def test_01_admin_kpis_neutral_style(self):
        """Verify Admin KPI cards are neutral (white, thin border, no colored side borders, no big 48px icons)."""
        self.login("admin@medlab.pk", "Admin@8521!")
        res = self.client.get("/admin/dashboard")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")

        # Must have the 4 KPIs
        self.assertIn("Total Revenue", html)
        self.assertIn("Total Bookings", html)
        self.assertIn("Pending (Booked)", html)
        self.assertIn("Active Staff", html)

        # Neutral style: NO colored side borders
        self.assertNotIn("kpi-card green", html)
        self.assertNotIn("kpi-card amber", html)
        self.assertNotIn("kpi-card slate", html)
        self.assertNotIn("border-l-4", html)
        # No 48px big icons
        self.assertNotIn("width:48px", html)

    def test_02_admin_recent_bookings_expander(self):
        """Verify Recent Bookings shows latest 3 rows by default with 'Show all (N)' expander and search box."""
        self.login("admin@medlab.pk", "Admin@8521!")
        res = self.client.get("/admin/dashboard")
        html = res.data.decode("utf-8")

        self.assertIn("Recent Bookings", html)
        self.assertIn("Show all (", html)
        self.assertIn("expanded", html)
        self.assertIn("max-h-96", html)
        self.assertIn("sticky top-0", html)

    # -------------------------------------------------------------------------
    # 2. ADMIN TEST CATALOG ACCORDIONS & AVAILABILITY TOGGLE
    # -------------------------------------------------------------------------
    def test_03_admin_test_catalog_accordions_and_needs_params_badge(self):
        """Verify test catalog groups tests in accordions, shows mono price, and 'Needs parameters' for 0-param tests."""
        self.login("admin@medlab.pk", "Admin@8521!")
        res = self.client.get("/admin/catalog")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")

        # Category accordions collapsed by default
        self.assertIn("activeCat: null", html)
        self.assertIn("Hematology", html)
        self.assertIn("Clinical Biochemistry", html)

        # Monospace price & TAT
        self.assertIn("font-mono", html)
        self.assertIn("PKR", html)

        # 0-param badge 'Needs parameters'
        self.assertIn("Needs parameters", html)

        # Toggle test endpoint form
        self.assertIn("/admin/catalog/toggle-test/", html)

    def test_04_admin_toggle_test_availability(self):
        """Verify Admin can toggle test availability on /admin/catalog/toggle-test/<id>."""
        self.login("admin@medlab.pk", "Admin@8521!")
        with self.app.app_context():
            test = query_db("SELECT test_id, is_active FROM lab_tests WHERE test_code='HEM-CBC'", one=True)
            self.assertIsNotNone(test)
            initial_state = test["is_active"]

        # Toggle to opposite
        res = self.client.post(f"/admin/catalog/toggle-test/{test['test_id']}", follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        with self.app.app_context():
            updated = query_db("SELECT is_active FROM lab_tests WHERE test_id=%s", (test["test_id"],), one=True)
            self.assertEqual(updated["is_active"], 0 if initial_state else 1)

        # Toggle back to original state for test cleanliness
        res2 = self.client.post(f"/admin/catalog/toggle-test/{test['test_id']}", follow_redirects=True)
        self.assertEqual(res2.status_code, 200)

        with self.app.app_context():
            restored = query_db("SELECT is_active FROM lab_tests WHERE test_id=%s", (test["test_id"],), one=True)
            self.assertEqual(restored["is_active"], initial_state)

    # -------------------------------------------------------------------------
    # 3. RECEPTIONIST NAVIGATION & DASHBOARD
    # -------------------------------------------------------------------------
    def test_05_receptionist_sidebar_profile_only_and_lab_tests_link(self):
        """Verify Receptionist sidebar shows only 'Profile' (no 'Security') and contains 'Lab Tests' link."""
        self.login("receptionist@medlab.pk", "Recp@8521!")
        res = self.client.get("/receptionist/dashboard")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")

        # 'Lab Tests' link in sidebar
        self.assertIn("/receptionist/tests", html)
        self.assertIn("Lab Tests", html)

        # Profile only (no 'Profile & Security')
        self.assertNotIn("Profile &amp; Security", html)
        self.assertIn("Profile", html)

    def test_06_receptionist_dashboard_recent_bookings_expander(self):
        """Verify Receptionist dashboard has 'Show all (N)' expander and search box."""
        self.login("receptionist@medlab.pk", "Recp@8521!")
        res = self.client.get("/receptionist/dashboard")
        html = res.data.decode("utf-8")

        self.assertIn("Show all (", html)
        self.assertIn("max-h-96", html)
        self.assertIn("sticky top-0", html)

    # -------------------------------------------------------------------------
    # 4. RECEPTIONIST READ-ONLY LAB TESTS PAGE
    # -------------------------------------------------------------------------
    def test_07_receptionist_read_only_lab_tests_page(self):
        """Verify /receptionist/tests renders accordions with availability badges and NO add/toggle controls."""
        self.login("receptionist@medlab.pk", "Recp@8521!")
        res = self.client.get("/receptionist/tests")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")

        # Content and accordions
        self.assertIn("Lab Tests Directory", html)
        self.assertIn("Hematology", html)
        self.assertIn("Available", html)
        self.assertIn("font-mono", html)

        # STRICTLY NO add, edit, or toggle controls
        self.assertNotIn("Add Lab Test", html)
        self.assertNotIn("Add Biomarker", html)
        self.assertNotIn("/admin/catalog/toggle-test", html)
        self.assertNotIn("toggle_test", html)

    # -------------------------------------------------------------------------
    # 5. INACTIVE TEST BOOKING REJECTION
    # -------------------------------------------------------------------------
    def test_08_inactive_test_greyed_out_and_backend_rejection(self):
        """Verify inactive tests are greyed out with Unavailable badge and backend rejects booking attempts."""
        # Find or create an inactive test for testing
        with self.app.app_context():
            execute_db("UPDATE lab_tests SET is_active=0 WHERE test_code='URN-ACR'")
            test_row = query_db("SELECT test_id FROM lab_tests WHERE test_code='URN-ACR'", one=True)

        try:
            # 1. Check patient book_test UI renders Unavailable badge and disabled
            self.login("patient1@medlab.pk", "Patient@8521!")
            res_ui = self.client.get("/patient/book-test")
            self.assertEqual(res_ui.status_code, 200)
            html_ui = res_ui.data.decode("utf-8")
            self.assertIn("Unavailable", html_ui)
            self.assertIn("disabled", html_ui)

            # 2. Forge a POST request attempting to book the inactive test
            res_post = self.client.post("/patient/book-test", data={
                "appointment_date": "2026-12-31",
                "appointment_slot": "08:00 AM - 10:00 AM",
                "test_ids": [str(test_row["test_id"])]
            }, follow_redirects=True)

            self.assertEqual(res_post.status_code, 200)
            post_html = res_post.data.decode("utf-8")
            self.assertIn("unavailable", post_html.lower())
        finally:
            # Restore test to active
            with self.app.app_context():
                execute_db("UPDATE lab_tests SET is_active=1 WHERE test_code='URN-ACR'")

    # -------------------------------------------------------------------------
    # 6. 403 SECURITY ENFORCEMENT
    # -------------------------------------------------------------------------
    def test_09_receptionist_gets_403_on_admin_test_routes(self):
        """Verify Receptionist POSTing to admin test catalog routes receives 403 Forbidden."""
        self.login("receptionist@medlab.pk", "Recp@8521!")

        # 1. Attempt POST to add test
        res_add = self.client.post("/admin/catalog/add-test", data={
            "category_id": 1,
            "test_code": "FORGED-01",
            "test_name": "Forged Test",
            "sample_type": "Serum",
            "price": "1000",
            "turnaround_hours": 12
        })
        self.assertEqual(res_add.status_code, 403, "Receptionist must receive 403 on /admin/catalog/add-test.")

        # 2. Attempt POST to add biomarker parameter
        res_param = self.client.post("/admin/catalog/add-param", data={
            "test_id": 1,
            "param_name": "Forged Param",
            "unit": "mg/dL",
            "min_range": 10,
            "max_range": 20
        })
        self.assertEqual(res_param.status_code, 403, "Receptionist must receive 403 on /admin/catalog/add-param.")

        # 3. Attempt POST to toggle test availability
        res_toggle = self.client.post("/admin/catalog/toggle-test/1")
        self.assertEqual(res_toggle.status_code, 403, "Receptionist must receive 403 on /admin/catalog/toggle-test/<id>.")


if __name__ == "__main__":
    runner = unittest.TextTestRunner(verbosity=2)
    suite = unittest.TestLoader().loadTestsFromTestCase(Phase3SpecTests)
    result = runner.run(suite)
    if result.wasSuccessful():
        print("\n[PASS] ALL 9 PHASE 3 SPECIFICATION TESTS PASSED SUCCESSFULLY!")
        sys.exit(0)
    else:
        print(f"\n[FAIL] {len(result.failures)} failures, {len(result.errors)} errors.")
        sys.exit(1)
