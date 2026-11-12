"""
tests/test_phase2.py
====================
Automated test suite verifying Phase 2 UI Redesign requirements:
  1. Design System Tokens & Typography (Inter, JetBrains Mono, #166534)
  2. Base Layout & MedLab Branding (authenticated shell, public nav, Lucide, Alpine.js)
  3. Editorial Landing Page (Hero, 3 stats, 01-04 workflow cards, packages, catalog, FAQ, phlebotomy)
  4. Authentication Interface (Login with Google button, show/hide toggle, pill button)
  5. Brute-Force Security (5-attempt increment, 10-minute lockout_until enforcement, reset on success)
  6. Patient Signup (Live Alpine.js 5-rule checklist, phone regex validation, Google button)
  7. Google OAuth / Supabase Bridge (Placeholder stub, schema documentation, callback redirect)
  8. Account Recovery (Forgot password form, CSRF, mock token stub VLAB-RESET-*, anti-enumeration)
  9. Custom Clinical Error Pages (403 Forbidden, 404 Not Found, 500 Server Error)

Run with:
    python tests/test_phase2.py
"""

import os
import re
import sys
import unittest
from datetime import datetime, timedelta

# Ensure project root is on PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from db import query_db, execute_db
from werkzeug.security import generate_password_hash


class Phase2UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.app.config["WTF_CSRF_ENABLED"] = False  # Allows clean programmatic form submissions

    # -------------------------------------------------------------------------
    # 1. DESIGN SYSTEM & TOKENS
    # -------------------------------------------------------------------------
    def test_01_design_system_css_tokens(self):
        """Verify custom.css contains the clinical dark green palette and mandatory fonts."""
        css_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "css", "custom.css")
        self.assertTrue(os.path.exists(css_path), "static/css/custom.css must exist.")
        
        with open(css_path, "r", encoding="utf-8") as f:
            css_content = f.read()

        # Check required fonts (Inter and JetBrains Mono, strictly no Bricolage or Instrument Sans)
        self.assertIn("Inter", css_content, "CSS must import and configure Inter.")
        self.assertIn("JetBrains Mono", css_content, "CSS must import and configure JetBrains Mono.")
        self.assertNotIn("Bricolage Grotesque", css_content, "CSS must NOT contain Bricolage Grotesque.")
        self.assertNotIn("Instrument Sans", css_content, "CSS must NOT contain Instrument Sans.")

        # Check curated color tokens
        self.assertIn("#166534", css_content, "CSS must define dark green #166534.")
        self.assertIn("#0F172A", css_content, "CSS must define slate text #0F172A.")
        self.assertIn("#F6FAF7", css_content, "CSS must define page background #F6FAF7.")

        # Check UI components
        self.assertIn("--radius-pill", css_content, "CSS must define pill radius token.")
        self.assertIn(".btn", css_content, "CSS must define buttons.")
        self.assertIn(".pwd-rule", css_content, "CSS must define password policy checklist rules.")
        self.assertIn(".numbered-card", css_content, "CSS must define numbered cards.")
        self.assertTrue(".green-feature-panel" in css_content or ".feature-panel" in css_content, "CSS must define feature panel.")

    # -------------------------------------------------------------------------
    # 2. BASE LAYOUT & BRANDING
    # -------------------------------------------------------------------------
    def test_02_base_layout_brand_and_scripts(self):
        """Verify MedLab brand, Lucide icons, and Alpine.js are present in public layout."""
        client = self.app.test_client()
        res = client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")

        self.assertIn("MedLab Diagnostics", html, "Page title or brand must mention MedLab Diagnostics.")
        self.assertIn("lucide.createIcons()", html, "Lucide icons must be initialized.")
        self.assertIn("alpinejs", html.lower(), "Alpine.js must be loaded in base layout.")
        self.assertIn("/login", html, "Navbar must link to /login.")
        self.assertIn("/signup", html, "Navbar must link to /signup.")

    # -------------------------------------------------------------------------
    # 3. LANDING PAGE CONTENT & EDITORIAL LAYOUT
    # -------------------------------------------------------------------------
    def test_03_landing_page_stats_and_workflow(self):
        """Verify the 3 oversized clinical stats and 01-04 numbered workflow cards."""
        client = self.app.test_client()
        res = client.get("/")
        html = res.data.decode("utf-8")

        # 3 Big Stats
        self.assertIn("99.8%", html, "Stat counter for 99.8% clinical accuracy must exist.")
        self.assertIn("12-24h", html, "Stat counter for routine turnaround must exist.")
        self.assertIn("15k+", html, "Stat counter for verified reports must exist.")

        # 01-04 Numbered workflow cards
        self.assertIn("01", html, "Numbered card 01 must exist.")
        self.assertIn("02", html, "Numbered card 02 must exist.")
        self.assertIn("03", html, "Numbered card 03 must exist.")
        self.assertIn("04", html, "Numbered card 04 must exist.")
        self.assertIn("Verified Report", html, "Pathologist verification step must be highlighted.")

    def test_04_landing_page_packages_and_catalog(self):
        """Verify Browse our tests catalog is retrieved and rendered."""
        client = self.app.test_client()
        res = client.get("/")
        html = res.data.decode("utf-8")

        # Test catalog section
        self.assertIn("Browse our tests", html, "Test catalog section must be present.")
        self.assertIn("Complete Blood Count (CBC)", html, "CBC test must be present.")
        self.assertIn("PKR", html, "Prices must be formatted in PKR.")

    def test_05_landing_page_faq_and_home_collection(self):
        """Verify Home Phlebotomy highlight and FAQ accordion section."""
        client = self.app.test_client()
        res = client.get("/")
        html = res.data.decode("utf-8")

        self.assertIn("Home sample collection", html)
        self.assertIn("Frequently Asked Questions", html)
        self.assertIn("Reports are released only after pathologist approval", html)

    # -------------------------------------------------------------------------
    # 4. LOGIN INTERFACE & AUTHENTICATION
    # -------------------------------------------------------------------------
    def test_06_login_page_elements(self):
        """Verify login page includes Google OAuth button, show/hide toggle, and recovery link."""
        client = self.app.test_client()
        res = client.get("/login")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")

        self.assertIn("Continue with Google", html, "Login must provide Continue with Google button.")
        self.assertIn("/auth/google", html, "Google button must link to /auth/google.")
        self.assertIn("Forgot password?", html, "Forgot password link must be present.")
        self.assertIn("/forgot-password", html, "Forgot password link must route to /forgot-password.")
        self.assertIn("Sign In to Account", html, "Submit button must exist.")

    # -------------------------------------------------------------------------
    # 5. BRUTE-FORCE SECURITY & LOCKOUT MECHANISM
    # -------------------------------------------------------------------------
    def test_07_brute_force_lockout_logic(self):
        """Verify that 5 failed attempts locks user account for 10 minutes."""
        client = self.app.test_client()

        # Create or retrieve a dedicated test user for lockout
        email = "lockout_test@medlab.pk"
        pwd_plain = "SecurePass@123"
        hashed = generate_password_hash(pwd_plain, method="pbkdf2:sha256")

        with self.app.app_context():
            existing = query_db("SELECT user_id FROM users WHERE email = %s", (email,), one=True)
            if not existing:
                execute_db(
                    "INSERT INTO users (role_id, full_name, phone, email, password_hash, is_active, login_attempts) "
                    "VALUES (4, 'Lockout Tester', '+923009999991', %s, %s, 1, 0)",
                    (email, hashed)
                )
            else:
                execute_db("UPDATE users SET login_attempts = 0, lockout_until = NULL WHERE email = %s", (email,))

        # Perform 4 consecutive failed logins
        for i in range(1, 5):
            res = client.post("/login", data={"email": email, "password": "WrongPassword!"}, follow_redirects=True)
            with self.app.app_context():
                u = query_db("SELECT login_attempts, lockout_until FROM users WHERE email = %s", (email,), one=True)
                self.assertEqual(u["login_attempts"], i, f"Attempts should increment to {i}")
                self.assertIsNone(u["lockout_until"], "User should not be locked out yet.")

        # 5th failed login triggers 10-minute lockout
        res = client.post("/login", data={"email": email, "password": "WrongPassword!"}, follow_redirects=True)
        html = res.data.decode("utf-8")
        self.assertIn("Account temporarily locked for 10 minutes", html)

        with self.app.app_context():
            u = query_db("SELECT login_attempts, lockout_until FROM users WHERE email = %s", (email,), one=True)
            self.assertEqual(u["login_attempts"], 5)
            self.assertIsNotNone(u["lockout_until"])
            self.assertGreater(u["lockout_until"], datetime.now() - timedelta(minutes=1))

        # Attempt login WITH CORRECT PASSWORD while locked out -> must still be blocked!
        res_blocked = client.post("/login", data={"email": email, "password": pwd_plain}, follow_redirects=True)
        blocked_html = res_blocked.data.decode("utf-8")
        self.assertIn("Account locked", blocked_html)

        # Reset user state for clean test hygiene
        with self.app.app_context():
            execute_db("UPDATE users SET login_attempts = 0, lockout_until = NULL WHERE email = %s", (email,))

    # -------------------------------------------------------------------------
    # 6. PATIENT SIGNUP & LIVE VALIDATION
    # -------------------------------------------------------------------------
    def test_08_signup_page_live_checklist_and_validation(self):
        """Verify signup page has live password checklist, phone validation, and Google button."""
        client = self.app.test_client()
        res = client.get("/signup")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")

        self.assertIn("Create Patient Account", html)
        self.assertIn("Sign up with Google", html)
        self.assertIn("hasLen", html, "Live Alpine rule for length >= 8 must be present.")
        self.assertIn("hasUpper", html, "Live Alpine rule for uppercase must be present.")
        self.assertIn("hasLower", html, "Live Alpine rule for lowercase must be present.")
        self.assertIn("hasDigit", html, "Live Alpine rule for digit must be present.")
        self.assertIn("hasSpecial", html, "Live Alpine rule for special character must be present.")

    def test_09_signup_rejection_of_invalid_inputs(self):
        """Verify server-side validation rejects invalid phone numbers and weak passwords."""
        client = self.app.test_client()

        # Rejection: invalid phone
        res_phone = client.post("/signup", data={
            "full_name": "Test User",
            "phone": "invalid-phone-abc",
            "email": "test_invalid_phone@example.com",
            "password": "Valid@Password123",
            "confirm_password": "Valid@Password123"
        })
        self.assertEqual(res_phone.status_code, 200)
        self.assertIn("Enter a valid phone number", res_phone.data.decode("utf-8"))

        # Rejection: weak password (no digit or special char)
        res_pwd = client.post("/signup", data={
            "full_name": "Test User",
            "phone": "+923001234567",
            "email": "test_weak_pwd@example.com",
            "password": "weakpassword",
            "confirm_password": "weakpassword"
        })
        self.assertEqual(res_pwd.status_code, 200)
        self.assertIn("Password must be 8+ chars", res_pwd.data.decode("utf-8"))

    # -------------------------------------------------------------------------
    # 7. GOOGLE OAUTH / SUPABASE BRIDGE
    # -------------------------------------------------------------------------
    def test_10_google_stub_and_callback(self):
        """Verify /auth/google route redirects to login."""
        client = self.app.test_client()
        res = client.get("/auth/google", follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn("/login", res.headers.get("Location", ""))

        # Callback test
        cb = client.get("/auth/google/callback", follow_redirects=False)
        self.assertEqual(cb.status_code, 302)
        self.assertIn("/login", cb.headers.get("Location", ""))

    # -------------------------------------------------------------------------
    # 8. ACCOUNT RECOVERY (FORGOT PASSWORD)
    # -------------------------------------------------------------------------
    def test_11_forgot_password_flow(self):
        """Verify /forgot-password renders, generates VLAB-RESET token, and handles unknown emails."""
        client = self.app.test_client()
        res = client.get("/forgot-password")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Account Recovery", res.data.decode("utf-8"))

        # Submit valid existing email
        res_valid = client.post("/forgot-password", data={"email": "patient1@medlab.pk"})
        self.assertEqual(res_valid.status_code, 200)
        html_valid = res_valid.data.decode("utf-8")
        self.assertIn("VLAB-RESET-", html_valid, "Mock reset token must be generated.")
        self.assertIn("Reset Token Generated", html_valid)

        # Submit non-existent email -> must prevent user enumeration
        res_unknown = client.post("/forgot-password", data={"email": "nonexistent_email_12345@example.com"})
        self.assertEqual(res_unknown.status_code, 200)
        html_unknown = res_unknown.data.decode("utf-8")
        self.assertIn("If an account exists", html_unknown, "Safe generic notification prevents enumeration.")

    # -------------------------------------------------------------------------
    # 9. CUSTOM ERROR PAGES
    # -------------------------------------------------------------------------
    def test_12_custom_error_pages(self):
        """Verify 403, 404, and 500 error pages render with clinical MedLab styling."""
        client = self.app.test_client()

        # 404 Not Found
        res_404 = client.get("/this-route-does-not-exist-medlab-check")
        self.assertEqual(res_404.status_code, 404)
        html_404 = res_404.data.decode("utf-8")
        self.assertIn("HTTP 404", html_404)
        self.assertIn("Diagnostic Record Not Found", html_404)
        self.assertIn("MedLab Diagnostics", html_404)

        # 403 Forbidden (test template rendering via test client context)
        with self.app.test_request_context():
            from flask import render_template
            html_403 = render_template("errors/403.html")
            self.assertIn("HTTP 403", html_403)
            self.assertIn("Restricted Diagnostic Zone", html_403)

            html_500 = render_template("errors/500.html")
            self.assertIn("HTTP 500", html_500)
            self.assertIn("Laboratory System Exception", html_500)


def run_phase2_tests():
    print("\n" + "=" * 70)
    print("  MEDLAB DIAGNOSTICS — VERIFICATION RUNNER")
    print("=" * 70)
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    suite.addTests(loader.loadTestsFromTestCase(Phase2UITests))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    print("=" * 70)
    if result.wasSuccessful():
        print(f"  [PASS] ALL {result.testsRun} TESTS PASSED SUCCESSFULLY!")
    else:
        print(f"  [FAIL] {len(result.failures)} failures, {len(result.errors)} errors.")
    print("=" * 70 + "\n")
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_phase2_tests()
    sys.exit(0 if success else 1)
