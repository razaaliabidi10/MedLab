"""
database/migration_phase4.py
============================
Additive, idempotent migration for Phase 4:
  - Add released_at, released_by, patient_viewed_at, verification_comment to `bookings`
  - Add released_at, released_by, verification_comment to `test_results`
  - Allow 'REPORT_READY' enum value in `notifications.type`
  - Update `vw_technician_worklist` to include In_Analysis and sent-back samples
  - Backfill released_at/released_by for existing Completed bookings
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
import db


def run_migration():
    app = create_app()
    with app.app_context():
        conn = db.get_db_connection()
        cur = conn.cursor(dictionary=True)

        print("--- Running Phase 4 Migration ---")

        # 1. Inspect bookings columns
        cur.execute("""
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'bookings'
        """)
        booking_cols = {r["COLUMN_NAME"] for r in cur.fetchall()}

        if "released_at" not in booking_cols:
            print("Adding released_at to bookings...")
            cur.execute("ALTER TABLE bookings ADD COLUMN released_at DATETIME NULL AFTER booking_status")

        if "released_by" not in booking_cols:
            print("Adding released_by to bookings...")
            cur.execute("ALTER TABLE bookings ADD COLUMN released_by INT UNSIGNED NULL AFTER released_at")
            cur.execute("""
                ALTER TABLE bookings
                ADD CONSTRAINT fk_booking_released_by
                FOREIGN KEY (released_by) REFERENCES users(user_id) ON DELETE SET NULL
            """)

        if "patient_viewed_at" not in booking_cols:
            print("Adding patient_viewed_at to bookings...")
            cur.execute("ALTER TABLE bookings ADD COLUMN patient_viewed_at DATETIME NULL AFTER released_by")

        if "verification_comment" not in booking_cols:
            print("Adding verification_comment to bookings...")
            cur.execute("ALTER TABLE bookings ADD COLUMN verification_comment TEXT NULL AFTER patient_viewed_at")

        # 2. Inspect test_results columns
        cur.execute("""
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'test_results'
        """)
        tr_cols = {r["COLUMN_NAME"] for r in cur.fetchall()}

        if "released_at" not in tr_cols:
            print("Adding released_at to test_results...")
            cur.execute("ALTER TABLE test_results ADD COLUMN released_at DATETIME NULL AFTER pathologist_verified_at")

        if "released_by" not in tr_cols:
            print("Adding released_by to test_results...")
            cur.execute("ALTER TABLE test_results ADD COLUMN released_by INT UNSIGNED NULL AFTER released_at")

        if "verification_comment" not in tr_cols:
            print("Adding verification_comment to test_results...")
            cur.execute("ALTER TABLE test_results ADD COLUMN verification_comment TEXT NULL AFTER released_by")

        # 3. Allow REPORT_READY in notifications.type
        cur.execute("""
            ALTER TABLE notifications
            MODIFY COLUMN type ENUM('booking','payment','sample','result','account','general','REPORT_READY') NOT NULL DEFAULT 'general'
        """)
        print("Updated notifications.type enum.")

        # 4. Backfill released_at and released_by for existing Completed bookings
        cur.execute("""
            UPDATE bookings b
            JOIN (
                SELECT bi.booking_id, MAX(tr.pathologist_verified_at) AS v_at, MAX(tr.verified_by) AS v_by
                FROM booking_items bi
                JOIN test_results tr ON bi.item_id = tr.item_id
                GROUP BY bi.booking_id
            ) sub ON b.booking_id = sub.booking_id
            SET b.released_at = COALESCE(sub.v_at, b.created_at),
                b.released_by = sub.v_by
            WHERE b.booking_status = 'Completed' AND b.released_at IS NULL
        """)
        print("Backfilled released_at/released_by for completed bookings.")

        # Also backfill test_results.released_at / released_by if null
        cur.execute("""
            UPDATE test_results
            SET released_at = pathologist_verified_at,
                released_by = verified_by
            WHERE pathologist_verified_at IS NOT NULL AND released_at IS NULL
        """)

        # 5. Update vw_technician_worklist to include In_Analysis & sent-back items
        cur.execute("""
            CREATE OR REPLACE VIEW vw_technician_worklist AS
            SELECT 
                s.sample_id, s.barcode_string, s.collected_at, s.sample_status,
                bi.item_id, bi.booking_id, b.booking_ref, b.booking_status, b.verification_comment,
                u.full_name AS patient_name, pp.gender AS patient_gender,
                lt.test_id, lt.test_code, lt.test_name, lt.sample_type
            FROM samples s
            JOIN booking_items bi ON s.item_id = bi.item_id
            JOIN bookings b ON bi.booking_id = b.booking_id
            JOIN users u ON b.patient_id = u.user_id
            LEFT JOIN patient_profiles pp ON u.user_id = pp.patient_id
            JOIN lab_tests lt ON bi.test_id = lt.test_id
            WHERE s.sample_status != 'Rejected' AND b.booking_status IN ('Sample_Collected', 'In_Analysis')
        """)
        print("Updated vw_technician_worklist.")

        conn.commit()
        cur.close()
        conn.close()
        print("--- Phase 4 Migration Complete ---")


if __name__ == "__main__":
    run_migration()
