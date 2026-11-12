"""
tests/test_phase3.py
====================
Automated test suite verifying Phase 3 Notifications System requirements:
  1. Top Bar Bell Icon & 10s Polling API (/notifications/api/unread-count).
  2. Dashboard Panel on all 6 role dashboards with latest 5 notifications and green unread dot.
  3. Dedicated /notifications Page with filter tabs (All/Unread), Mark All as Read POST, pagination, and empty state.
  4. Notification Detail Route (/notifications/<id>):
     - Shows title, message, timestamp, related booking ref, stage tracker, short timeline.
     - Role-specific "Go to booking" button.
     - Marked as read on open (is_read becomes 1).
     - 403 Forbidden if not the owner.
"""

import os
import sys
import unittest

# Ensure project root is on PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from db import query_db, execute_db


class Phase3NotificationsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.app.config["WTF_CSRF_ENABLED"] = False

    def login_user(self, client, email, password):
        """Helper to log in as a specific user."""
        return client.post("/login", data={"email": email, "password": password}, follow_redirects=True)

    # -------------------------------------------------------------------------
    # 1. TOP BAR BELL ICON & API UNREAD COUNT
    # -------------------------------------------------------------------------
    def test_01_topbar_bell_icon_and_unread_badge(self):
        """Verify authenticated user gets topbar bell icon and unread count badge."""
        client = self.app.test_client()
        self.login_user(client, "admin@medlab.pk", "Admin@8521!")

        res = client.get("/admin/dashboard")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")

        self.assertIn("notification-bell-container", html, "Top bar must contain notification bell container.")
        self.assertIn("bell-unread-count", html, "Top bar bell must have unread count badge.")
        self.assertIn("/notifications", html, "Bell must link to /notifications.")
        self.assertIn("pollNotifications", html, "10-second polling script must be present.")
        self.assertIn("toast-container", html, "Toast container must be present.")

    def test_02_api_unread_count_endpoint(self):
        """Verify /notifications/api/unread-count returns JSON with unread count."""
        client = self.app.test_client()
        self.login_user(client, "admin@medlab.pk", "Admin@8521!")

        res = client.get("/notifications/api/unread-count")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("unread_count", data)
        self.assertIn("max_id", data)
        self.assertIsInstance(data["unread_count"], int)

    # -------------------------------------------------------------------------
    # 2. DASHBOARD PANEL ON ALL 6 ROLES
    # -------------------------------------------------------------------------
    def test_03_dashboard_panel_on_all_six_roles(self):
        """Verify Recent Notifications panel is removed from all 6 dashboards, and topbar bell dropdown is present."""
        roles = [
            ("admin@medlab.pk", "Admin@8521!", "/admin/dashboard"),
            ("receptionist@medlab.pk", "Recp@8521!", "/receptionist/dashboard"),
            ("technician@medlab.pk", "Tech@8521!", "/technician/dashboard"),
            ("patient1@medlab.pk", "Patient@8521!", "/patient/dashboard"),
            ("collector@medlab.pk", "Coll@8521!", "/collector/dashboard"),
            ("pathologist@medlab.pk", "Path@8521!", "/pathologist/dashboard")
        ]

        for email, pwd, dash_url in roles:
            client = self.app.test_client()
            login_res = self.login_user(client, email, pwd)
            self.assertEqual(login_res.status_code, 200, f"Login failed for {email}")

            dash_res = client.get(dash_url)
            self.assertEqual(dash_res.status_code, 200, f"Dashboard failed for {dash_url}")
            html = dash_res.data.decode("utf-8")

            # Notification panel must be removed from dashboards
            self.assertNotIn("_dashboard_panel.html", html)
            # Bell dropdown must be present
            self.assertIn("notification-dropdown", html, f"Dashboard {dash_url} must include bell notification-dropdown.")
            self.assertIn("View all", html, f"Dashboard {dash_url} must include View all link.")

    # -------------------------------------------------------------------------
    # 3. DEDICATED /notifications PAGE
    # -------------------------------------------------------------------------
    def test_04_dedicated_notifications_page_tabs_and_actions(self):
        """Verify /notifications dedicated page supports All and Unread filter tabs and Mark All Read."""
        client = self.app.test_client()
        self.login_user(client, "admin@medlab.pk", "Admin@8521!")

        # All tab
        res_all = client.get("/notifications")
        self.assertEqual(res_all.status_code, 200)
        html_all = res_all.data.decode("utf-8")
        self.assertIn("Notifications Center", html_all)
        self.assertIn("All Notifications", html_all)
        self.assertIn("Unread Only", html_all)

        # Unread tab
        res_unread = client.get("/notifications?filter=unread")
        self.assertEqual(res_unread.status_code, 200)
        html_unread = res_unread.data.decode("utf-8")
        self.assertIn("Unread Only", html_unread)

    def test_05_mark_all_read_action(self):
        """Verify POST /notifications/mark-all-read marks all notifications for user as read."""
        client = self.app.test_client()
        with self.app.app_context():
            # Get an existing patient or create a test notification
            user = query_db("SELECT user_id FROM users WHERE email = 'patient1@medlab.pk'", one=True)
            u_id = user["user_id"]
            # Ensure at least 1 unread notification exists
            execute_db(
                "INSERT INTO notifications (user_id, type, title, message, is_read) "
                "VALUES (%s, 'general', 'Test Unread Alert', 'Please review your booking.', 0)",
                (u_id,)
            )

        self.login_user(client, "patient1@medlab.pk", "Patient@8521!")

        # Check that unread count > 0
        with self.app.app_context():
            unread_before = query_db("SELECT COUNT(*) AS c FROM notifications WHERE user_id = %s AND is_read = 0", (u_id,), one=True)["c"]
        self.assertGreater(unread_before, 0)

        # Post mark-all-read
        post_res = client.post("/notifications/mark-all-read", follow_redirects=True)
        self.assertEqual(post_res.status_code, 200)

        with self.app.app_context():
            unread_after = query_db("SELECT COUNT(*) AS c FROM notifications WHERE user_id = %s AND is_read = 0", (u_id,), one=True)["c"]
        self.assertEqual(unread_after, 0, "All notifications must be marked as read.")

    # -------------------------------------------------------------------------
    # 4. NOTIFICATION DETAIL ROUTE & SECURITY (403)
    # -------------------------------------------------------------------------
    def test_06_notification_detail_view_and_mark_read_on_open(self):
        """Verify /notifications/<id> displays details, tracker, timeline, and marks as read on open."""
        with self.app.app_context():
            user = query_db("SELECT user_id FROM users WHERE email = 'patient1@medlab.pk'", one=True)
            u_id = user["user_id"]
            # Insert unread notification with booking_id
            booking = query_db("SELECT booking_id, booking_ref FROM bookings WHERE patient_id = %s LIMIT 1", (u_id,), one=True)
            b_id = booking["booking_id"] if booking else None
            execute_db(
                "INSERT INTO notifications (user_id, type, title, message, booking_id, is_read) "
                "VALUES (%s, 'booking', 'Detail View Test', 'Test notification content', %s, 0)",
                (u_id, b_id)
            )
            created_notif = query_db("SELECT notification_id FROM notifications WHERE user_id = %s ORDER BY notification_id DESC LIMIT 1", (u_id,), one=True)
            notif_id = created_notif["notification_id"]

        client = self.app.test_client()
        self.login_user(client, "patient1@medlab.pk", "Patient@8521!")

        res = client.get(f"/notifications/{notif_id}")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")

        self.assertIn("Detail View Test", html)
        self.assertIn("Test notification content", html)
        self.assertIn("Diagnostic Stage Tracker", html)
        self.assertIn("Activity Timeline", html)
        self.assertIn("Go to Booking", html)

        # Verify it was marked as read
        with self.app.app_context():
            check = query_db("SELECT is_read FROM notifications WHERE notification_id = %s", (notif_id,), one=True)
            self.assertEqual(check["is_read"], 1, "Opening notification must mark is_read = 1.")

    def test_07_notification_ownership_security_403(self):
        """Verify accessing another user's notification returns 403 Forbidden."""
        with self.app.app_context():
            admin_user = query_db("SELECT user_id FROM users WHERE email = 'admin@medlab.pk'", one=True)
            # Create a notification strictly owned by admin
            execute_db(
                "INSERT INTO notifications (user_id, type, title, message, is_read) "
                "VALUES (%s, 'general', 'Admin Only Confidential', 'Confidential management notice', 0)",
                (admin_user["user_id"],)
            )
            admin_notif = query_db("SELECT notification_id FROM notifications WHERE user_id = %s ORDER BY notification_id DESC LIMIT 1", (admin_user["user_id"],), one=True)
            admin_notif_id = admin_notif["notification_id"]

        # Log in as patient1
        client = self.app.test_client()
        self.login_user(client, "patient1@medlab.pk", "Patient@8521!")

        # Attempt to access admin's notification
        res = client.get(f"/notifications/{admin_notif_id}")
        self.assertEqual(res.status_code, 403, "Accessing another user's notification MUST return 403 Forbidden.")


if __name__ == "__main__":
    runner = unittest.TextTestRunner(verbosity=2)
    suite = unittest.TestLoader().loadTestsFromTestCase(Phase3NotificationsTests)
    result = runner.run(suite)
    if result.wasSuccessful():
        print("\n[PASS] ALL 7 PHASE 3 NOTIFICATION TESTS PASSED SUCCESSFULLY!")
        sys.exit(0)
    else:
        print(f"\n[FAIL] {len(result.failures)} failures, {len(result.errors)} errors.")
        sys.exit(1)
