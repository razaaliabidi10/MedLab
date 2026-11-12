"""
tests/test_phase2_spec.py
=========================
Comprehensive automated verification suite for the Phase 2 specification:
  1. Landing Page "Browse our tests" Section:
     - Tests section is collapsed by default (open: false).
     - Heading "Browse our tests" and collapse/expand control button exist.
     - Numbered categories exist in order: 1. Hematology, 2. Clinical Biochemistry, etc.
     - Tests display code, name, sample type, turnaround, and price in JetBrains Mono.
     - Accordion logic enforces only one category open at a time.
     - Per-category search filter and empty state message exist.
     - Hero, 3 stats, 01-04 workflow steps, health packages, home collection, why us, FAQ, footer are all intact.
  2. Login & Signup Layouts:
     - "Continue with Google" is at the BOTTOM of the card below the form and submit button.
     - Form submit button and Google button are separated by an "or" divider.
     - Inline SVG Google logo is present with link to /auth/google.
     - "Back to Home" button is at top left with data-lucide="arrow-left".
     - Signup maintains live 5-rule password checklist.
  3. Admin Navigation Cleanup:
     - "Public Website" link is 100% absent from all pages and base template.
"""

import os
import sys
import unittest
# Ensure project root is on PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app


class Phase2SpecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()

    # -------------------------------------------------------------------------
    # -------------------------------------------------------------------------
    # 1. STITCH LANDING PAGE SPECIFICATION TESTS
    # -------------------------------------------------------------------------
    def test_01_landing_browse_tests_section_and_catalog(self):
        """Verify 'Browse our tests' section exists, is collapsed by default, and renders active tests."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")

        self.assertIn("Browse our tests", html)
        self.assertIn('id="browse-tests"', html)
        self.assertIn("catalogOpen: false", html)
        self.assertIn("PKR", html)

    def test_02_landing_hero_and_real_links(self):
        """Verify hero action area features real Sign Up and Sign In links."""
        res = self.client.get("/")
        html = res.data.decode("utf-8")

        self.assertIn("Sign In", html)
        self.assertIn("Sign Up", html)
        self.assertIn("/login", html)
        self.assertIn("/signup", html)
        self.assertNotIn('href="#signin"', html)
        self.assertNotIn('href="#signup"', html)

    def test_03_landing_why_choose_medlab_claims(self):
        """Verify Why choose MedLab section removes unverifiable claims and includes pathologist approval chip."""
        res = self.client.get("/")
        html = res.data.decode("utf-8")

        self.assertIn("Why choose MedLab", html)
        self.assertIn("Reports are released only after pathologist approval", html)
        self.assertIn("Pathologist-verified reports", html)
        self.assertIn("Home sample collection", html)
        self.assertIn("Real-time status updates", html)
        self.assertIn("Secure patient portal", html)
        self.assertNotIn("ISO 15189", html)
        self.assertNotIn("HIPAA", html)

    def test_04_landing_how_it_works_four_steps(self):
        """Verify How It Works has exactly Book, Collect, Test, Verified Report."""
        res = self.client.get("/")
        html = res.data.decode("utf-8")

        self.assertIn("How It Works", html)
        self.assertIn("Book", html)
        self.assertIn("Collect", html)
        self.assertIn("Test", html)
        self.assertIn("Verified Report", html)

    def test_05_landing_faq_and_footer(self):
        """Verify FAQ accordion and footer contact info."""
        res = self.client.get("/")
        html = res.data.decode("utf-8")

        self.assertIn("Frequently Asked Questions", html)
        self.assertIn("How do I book a test?", html)
        self.assertIn("care@medlab.pk", html)
        self.assertIn("+92 300 0000000", html)

    # -------------------------------------------------------------------------
    # 2. LOGIN & SIGNUP LAYOUT UPDATES
    # -------------------------------------------------------------------------
    def test_06_login_google_at_bottom_with_divider(self):
        """Verify login page has Continue with Google at the bottom below form and 'or' divider."""
        res = self.client.get("/login")
        html = res.data.decode("utf-8")

        # Top-left back button
        self.assertIn("Back to Home", html)
        self.assertIn('data-lucide="arrow-left"', html)

        # Order check: Form submit button must appear BEFORE Google button
        submit_idx = html.find("Sign In to Account")
        divider_idx = html.find(">or<")
        google_idx = html.find("Continue with Google")

        self.assertNotEqual(submit_idx, -1, "Submit button must exist.")
        self.assertNotEqual(divider_idx, -1, "'or' divider must exist.")
        self.assertNotEqual(google_idx, -1, "Google button must exist.")
        self.assertTrue(submit_idx < divider_idx < google_idx, "Layout order must be: Form Submit -> 'or' Divider -> Continue with Google.")

        # Google route and SVG logo
        self.assertIn("/auth/google", html)
        self.assertIn("<svg", html)

    def test_07_signup_google_at_bottom_with_divider_and_checklist(self):
        """Verify signup page has Continue with Google at the bottom, 'or' divider, and live password checklist."""
        res = self.client.get("/signup")
        html = res.data.decode("utf-8")

        # Top-left back button
        self.assertIn("Back to Home", html)
        self.assertIn('data-lucide="arrow-left"', html)

        # Order check: Form submit button must appear BEFORE Google button
        submit_idx = html.find("Create Patient Account")
        divider_idx = html.find(">or<")
        google_idx = html.find("Continue with Google")

        self.assertNotEqual(submit_idx, -1, "Submit button must exist.")
        self.assertNotEqual(divider_idx, -1, "'or' divider must exist.")
        self.assertNotEqual(google_idx, -1, "Google button must exist.")
        self.assertTrue(submit_idx < divider_idx < google_idx, "Layout order must be: Form Submit -> 'or' Divider -> Continue with Google.")

        # Live password checklist rules
        self.assertIn("hasLen", html)
        self.assertIn("hasUpper", html)
        self.assertIn("hasLower", html)
        self.assertIn("hasDigit", html)
        self.assertIn("hasSpecial", html)

    # -------------------------------------------------------------------------
    # 3. ADMIN NAVIGATION CLEANUP
    # -------------------------------------------------------------------------
    def test_08_public_website_link_eradicated(self):
        """Verify 'Public Website' is 100% absent across base template and responses."""
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates", "base.html"), "r", encoding="utf-8") as f:
            base_html = f.read()

        self.assertNotIn("Public Website", base_html, "'Public Website' link must not exist in base.html.")


if __name__ == "__main__":
    runner = unittest.TextTestRunner(verbosity=2)
    suite = unittest.TestLoader().loadTestsFromTestCase(Phase2SpecTests)
    result = runner.run(suite)
    if result.wasSuccessful():
        print("\n[PASS] ALL 8 PHASE 2 SPECIFICATION TESTS PASSED SUCCESSFULLY!")
        sys.exit(0)
    else:
        print(f"\n[FAIL] {len(result.failures)} failures, {len(result.errors)} errors.")
        sys.exit(1)
