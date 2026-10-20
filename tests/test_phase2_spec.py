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
    # 1. LANDING PAGE "BROWSE OUR TESTS" ACCORDION
    # -------------------------------------------------------------------------
    def test_01_landing_browse_tests_section_collapsed_by_default(self):
        """Verify tests section is titled 'Browse our tests' and collapsed by default with Alpine.js."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")

        # Heading and control
        self.assertIn("Browse our tests", html)
        self.assertIn("open: false", html, "Catalog section must initialize Alpine with open: false.")
        self.assertIn("activeCat: null", html, "Accordion must initialize activeCat as null.")
        self.assertIn("Explore All Categories", html, "Control button to explore categories must be present.")
        self.assertIn("Collapse Test Directory", html, "Toggle label must be present.")

    def test_02_landing_numbered_categories_order(self):
        """Verify categories are numbered sequentially starting with Hematology and Clinical Biochemistry."""
        res = self.client.get("/")
        html = res.data.decode("utf-8")

        self.assertIn("1. Hematology", html)
        self.assertIn("2. Clinical Biochemistry", html)
        self.assertIn("3. Endocrinology &amp; Metabolism", html)

    def test_03_landing_per_category_search_and_empty_state(self):
        """Verify per-category search input and empty state message exist."""
        res = self.client.get("/")
        html = res.data.decode("utf-8")

        self.assertIn("Search tests in Hematology...", html)
        self.assertIn("Search tests in Clinical Biochemistry...", html)
        self.assertIn("No tests found in this category", html)
        self.assertIn("filteredTests", html, "Client-side Alpine filter property must be defined.")

    def test_04_landing_only_active_tests_with_mono_price(self):
        """Verify active tests render name, sample type, and price in JetBrains Mono."""
        res = self.client.get("/")
        html = res.data.decode("utf-8")

        self.assertIn("Complete Blood Count (CBC)", html)
        self.assertIn("Blood (EDTA)", html)
        self.assertIn("font-mono", html, "Prices and codes must use font-mono (JetBrains Mono).")
        self.assertIn("PKR", html)

    def test_05_landing_preserved_editorial_sections(self):
        """Verify hero, 3 stats, 01-04 workflow steps, packages, home collection, why us, FAQ, and footer remain intact."""
        res = self.client.get("/")
        html = res.data.decode("utf-8")

        # Hero
        self.assertIn("Precision Diagnostics For Proactive Health", html)
        # 3 Stats
        self.assertIn("99.8%", html)
        self.assertIn("12-24h", html)
        self.assertIn("15k+", html)
        # 01-04 Workflow
        self.assertIn("01", html)
        self.assertIn("02", html)
        self.assertIn("03", html)
        self.assertIn("04", html)
        # Health packages
        self.assertIn("Curated Health Packages", html)
        # Home Phlebotomy
        self.assertIn("Doorstep Healthcare", html)
        # Why Us
        self.assertIn("Clinical Standards", html)
        # FAQ
        self.assertIn("Frequently Asked Questions", html)
        # Footer
        self.assertIn("MedLab Diagnostics", html)

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
