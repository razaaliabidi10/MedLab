"""
database/generate_seed_hashes.py
=================================
Run this ONCE to pre-compute Werkzeug password hashes and write them
directly into database/seed_v2.sql at the placeholder positions.

Usage (from project root, with venv active):
    python database/generate_seed_hashes.py

It will print the seed SQL with real hashes to stdout and also
overwrite database/seed_v2.sql so you can run it directly in MySQL.
"""

import os
import sys

# Add project root to path so we can import from the venv
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from werkzeug.security import generate_password_hash

METHOD = "pbkdf2:sha256"

# Demo credentials (one per role)
ACCOUNTS = [
    # (full_name,           email,                       phone,          password,        role_id)
    ("Raza Ali",            "admin@medlab.pk",           "+923001234567", "Admin@8521!",   1),
    ("Sara Noor",           "receptionist@medlab.pk",    "+923011234567", "Recp@8521!",    2),
    ("Bilal Ahmed",         "technician@medlab.pk",      "+923021234567", "Tech@8521!",    3),
    ("Aisha Khan",          "patient1@medlab.pk",        "+923031234567", "Patient@8521!", 4),
    ("Hamid Raza",          "patient2@medlab.pk",        "+923041234567", "Patient@8521!", 4),
    ("Zara Malik",          "patient3@medlab.pk",        "+923051234567", "Patient@8521!", 4),
    ("Usman Tariq",         "patient4@medlab.pk",        "+923061234567", "Patient@8521!", 4),
    ("Fatima Sheikh",       "patient5@medlab.pk",        "+923071234567", "Patient@8521!", 4),
    ("Ali Hassan",          "patient6@medlab.pk",        "+923081234567", "Patient@8521!", 4),
    ("Mehwish Butt",        "patient7@medlab.pk",        "+923091234567", "Patient@8521!", 4),
    ("Kamran Iqbal",        "patient8@medlab.pk",        "+923101234567", "Patient@8521!", 4),
    ("Tariq Collector",     "collector@medlab.pk",       "+923111234567", "Coll@8521!",    5),
    ("Dr. Nadia Pathologist","pathologist@medlab.pk",    "+923121234567", "Path@8521!",    6),
]

def main():
    # Ensure stdout can handle ASCII output on Windows
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    rows = []
    for full_name, email, phone, password, role_id in ACCOUNTS:
        h = generate_password_hash(password, method=METHOD)
        rows.append((role_id, full_name, email, phone, h))
        print(f"  [{role_id}] {email:<35}  ok  hash computed")

    print("\nGenerating seed_v2.sql ...\n")

    # Build the SQL string with real hashes
    sql = generate_seed_sql(rows)

    out_path = os.path.join(os.path.dirname(__file__), "seed_v2.sql")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(sql)

    print(f"✅  Written to: {out_path}")
    print()
    print("━" * 60)
    print("DEMO CREDENTIALS (all must pass the password policy)")
    print("━" * 60)
    for full_name, email, phone, password, role_id in ACCOUNTS:
        role_map = {1:"admin", 2:"receptionist", 3:"technician",
                    4:"patient", 5:"sample_collector", 6:"pathologist"}
        print(f"  [{role_map[role_id]:<17}]  {email:<35}  pw: {password}")
    print("━" * 60)
    print()
    print("Next step:")
    print("  mysql -u root -p medlab_db < database/seed_v2.sql")


def generate_seed_sql(rows):
    """
    Returns the complete seed_v2.sql content with real password hashes.
    rows = [(role_id, full_name, email, phone, hash), ...]
    """
    # Split rows by role for convenience
    admin_rows  = [r for r in rows if r[0] == 1]
    staff_rows  = [r for r in rows if r[0] in (2, 3, 5, 6)]
    patient_rows = [r for r in rows if r[0] == 4]

    lines = [SEED_HEADER]

    # Users — admin (no created_by since it's the very first user)
    # Uses INSERT ... SELECT WHERE NOT EXISTS + UPDATE so it works whether admin already exists or not without triggering trg_enforce_role_creation
    for role_id, full_name, email, phone, h in admin_rows:
        lines.append(
            f"INSERT INTO users (role_id, full_name, email, phone, password_hash, is_active)\n"
            f"SELECT {role_id}, '{full_name}', '{email}', '{phone}', '{h}', TRUE\n"
            f"WHERE NOT EXISTS (SELECT 1 FROM (SELECT user_id FROM users WHERE role_id = {role_id}) AS _chk);\n"
            f"UPDATE users SET full_name = '{full_name}', phone = '{phone}', password_hash = '{h}', is_active = TRUE WHERE email = '{email}';\n"
        )

    # Users — staff (created_by = admin, we'll use a sub-select)
    for role_id, full_name, email, phone, h in staff_rows:
        lines.append(
            f"INSERT IGNORE INTO users (role_id, full_name, email, phone, password_hash, is_active, created_by)\n"
            f"VALUES ({role_id}, '{full_name}', '{email}', '{phone}', '{h}', TRUE,\n"
            f"        (SELECT user_id FROM (SELECT user_id FROM users WHERE email='admin@medlab.pk') AS t));\n"
        )

    # Users — patients (no created_by)
    for role_id, full_name, email, phone, h in patient_rows:
        lines.append(
            f"INSERT IGNORE INTO users (role_id, full_name, email, phone, password_hash, is_active)\n"
            f"VALUES ({role_id}, '{full_name}', '{email}', '{phone}', '{h}', TRUE);\n"
        )

    lines.append(SEED_BODY)
    return "\n".join(lines)


SEED_HEADER = """\
-- =============================================================================
-- MedLab System — Seed v2
-- File   : database/seed_v2.sql
-- GENERATED BY: database/generate_seed_hashes.py
-- Safe   : Fully rerunnable (INSERT IGNORE + ON DUPLICATE KEY UPDATE).
-- How to run:
--   mysql -u root -p medlab_db < database/seed_v2.sql
-- =============================================================================
USE medlab_db;

-- ─────────────────────────────────────────────────────────────────────────────
-- USERS (admin, staff, patients)
-- ─────────────────────────────────────────────────────────────────────────────
"""

SEED_BODY = r"""
-- ─────────────────────────────────────────────────────────────────────────────
-- PATIENT PROFILES (one row per patient user)
-- ─────────────────────────────────────────────────────────────────────────────
INSERT IGNORE INTO patient_profiles (patient_id, date_of_birth, gender, blood_group, address)
SELECT u.user_id,
       CASE u.email
           WHEN 'patient1@medlab.pk' THEN '1990-03-15'
           WHEN 'patient2@medlab.pk' THEN '1985-07-22'
           WHEN 'patient3@medlab.pk' THEN '1978-11-08'
           WHEN 'patient4@medlab.pk' THEN '1995-01-30'
           WHEN 'patient5@medlab.pk' THEN '2000-06-12'
           WHEN 'patient6@medlab.pk' THEN '1968-09-25'
           WHEN 'patient7@medlab.pk' THEN '1992-12-03'
           WHEN 'patient8@medlab.pk' THEN '1975-04-17'
       END,
       CASE u.email
           WHEN 'patient1@medlab.pk' THEN 'Female'
           WHEN 'patient2@medlab.pk' THEN 'Male'
           WHEN 'patient3@medlab.pk' THEN 'Female'
           WHEN 'patient4@medlab.pk' THEN 'Male'
           WHEN 'patient5@medlab.pk' THEN 'Female'
           WHEN 'patient6@medlab.pk' THEN 'Male'
           WHEN 'patient7@medlab.pk' THEN 'Female'
           WHEN 'patient8@medlab.pk' THEN 'Male'
       END,
       CASE u.email
           WHEN 'patient1@medlab.pk' THEN 'B+'
           WHEN 'patient2@medlab.pk' THEN 'O+'
           WHEN 'patient3@medlab.pk' THEN 'A+'
           WHEN 'patient4@medlab.pk' THEN 'AB+'
           WHEN 'patient5@medlab.pk' THEN 'B-'
           WHEN 'patient6@medlab.pk' THEN 'O-'
           WHEN 'patient7@medlab.pk' THEN 'A-'
           WHEN 'patient8@medlab.pk' THEN 'A+'
       END,
       CASE u.email
           WHEN 'patient1@medlab.pk' THEN 'House 12, Block A, Gulshan-e-Iqbal, Karachi'
           WHEN 'patient2@medlab.pk' THEN 'Flat 5, Al-Noor Apartments, Nazimabad, Karachi'
           WHEN 'patient3@medlab.pk' THEN '34 Garden Road, Clifton, Karachi'
           WHEN 'patient4@medlab.pk' THEN 'Bungalow 7, DHA Phase 2, Karachi'
           WHEN 'patient5@medlab.pk' THEN '221 Tariq Road, PECHS, Karachi'
           WHEN 'patient6@medlab.pk' THEN 'House 88, Korangi Industrial Area, Karachi'
           WHEN 'patient7@medlab.pk' THEN 'Flat 3B, Safari Apartments, North Nazimabad, Karachi'
           WHEN 'patient8@medlab.pk' THEN '15 Shahrah-e-Faisal, Near Metropole, Karachi'
       END
FROM users u
WHERE u.role_id = 4;

-- ─────────────────────────────────────────────────────────────────────────────
-- STAFF PROFILES (receptionist, technician, collector, pathologist)
-- ─────────────────────────────────────────────────────────────────────────────
INSERT IGNORE INTO staff_profiles (staff_id, employee_code, qualification, shift_timing, joining_date)
SELECT u.user_id,
       CASE u.email
           WHEN 'receptionist@medlab.pk' THEN 'RECP-001'
           WHEN 'technician@medlab.pk'   THEN 'TECH-001'
           WHEN 'collector@medlab.pk'    THEN 'COLL-001'
           WHEN 'pathologist@medlab.pk'  THEN 'PATH-001'
       END,
       CASE u.email
           WHEN 'receptionist@medlab.pk' THEN 'BCS Medical Administration'
           WHEN 'technician@medlab.pk'   THEN 'BSc Medical Laboratory Technology'
           WHEN 'collector@medlab.pk'    THEN 'Diploma in Phlebotomy'
           WHEN 'pathologist@medlab.pk'  THEN 'MBBS, MRCPath (UK), FCPS Pathology'
       END,
       CASE u.email
           WHEN 'receptionist@medlab.pk' THEN 'Morning'
           WHEN 'technician@medlab.pk'   THEN 'Morning'
           WHEN 'collector@medlab.pk'    THEN 'Morning'
           WHEN 'pathologist@medlab.pk'  THEN 'Morning'
       END,
       CASE u.email
           WHEN 'receptionist@medlab.pk' THEN '2023-01-15'
           WHEN 'technician@medlab.pk'   THEN '2022-09-01'
           WHEN 'collector@medlab.pk'    THEN '2024-03-10'
           WHEN 'pathologist@medlab.pk'  THEN '2021-06-01'
       END
FROM users u
WHERE u.role_id IN (2, 3, 5, 6);


-- ─────────────────────────────────────────────────────────────────────────────
-- TEST PARAMETERS for new tests added in migration_v2
-- (CBC, LFT, Lipid already seeded in medlab_db_full.sql)
-- ─────────────────────────────────────────────────────────────────────────────
-- Helper: insert params for a named test (idempotent via INSERT IGNORE on uq_item_param)
-- We re-insert CBC, LFT, etc. using IGNORE so existing rows are unchanged.

-- HbA1c
INSERT IGNORE INTO test_parameters (test_id, param_name, unit, min_range, max_range, display_order)
SELECT t.test_id, v.param_name, v.unit, v.min_range, v.max_range, v.display_order
FROM lab_tests t
JOIN (
    SELECT 'HbA1c (%)' AS param_name, '%' AS unit, 4.00 AS min_range, 5.60 AS max_range, 1 AS display_order
) v ON t.test_code = 'BIO-HBA';

-- TSH
INSERT IGNORE INTO test_parameters (test_id, param_name, unit, min_range, max_range, display_order)
SELECT t.test_id, v.param_name, v.unit, v.min_range, v.max_range, v.display_order
FROM lab_tests t
CROSS JOIN (
    SELECT 'TSH (Thyroid Stimulating Hormone)' AS param_name, 'mIU/L' AS unit, 0.40 AS min_range, 4.00 AS max_range, 1 AS display_order
    UNION ALL SELECT 'Free T4 (FT4)', 'ng/dL', 0.80, 1.80, 2
) v WHERE t.test_code = 'THY-TSH';

-- T3
INSERT IGNORE INTO test_parameters (test_id, param_name, unit, min_range, max_range, display_order)
SELECT t.test_id, v.param_name, v.unit, v.min_range, v.max_range, v.display_order
FROM lab_tests t
CROSS JOIN (
    SELECT 'Total T3' AS param_name, 'nmol/L' AS unit, 1.20 AS min_range, 2.80 AS max_range, 1 AS display_order
) v WHERE t.test_code = 'THY-T3';

-- T4
INSERT IGNORE INTO test_parameters (test_id, param_name, unit, min_range, max_range, display_order)
SELECT t.test_id, v.param_name, v.unit, v.min_range, v.max_range, v.display_order
FROM lab_tests t
CROSS JOIN (
    SELECT 'Total T4 (Thyroxine)' AS param_name, 'nmol/L' AS unit, 60.00 AS min_range, 150.00 AS max_range, 1 AS display_order
) v WHERE t.test_code = 'THY-T4';

-- FT4
INSERT IGNORE INTO test_parameters (test_id, param_name, unit, min_range, max_range, display_order)
SELECT t.test_id, v.param_name, v.unit, v.min_range, v.max_range, v.display_order
FROM lab_tests t
CROSS JOIN (
    SELECT 'Free Thyroxine (FT4)' AS param_name, 'ng/dL' AS unit, 0.80 AS min_range, 1.80 AS max_range, 1 AS display_order
) v WHERE t.test_code = 'THY-FT4';

-- Urine R/E
INSERT IGNORE INTO test_parameters (test_id, param_name, unit, min_range, max_range, display_order)
SELECT t.test_id, v.param_name, v.unit, v.min_range, v.max_range, v.display_order
FROM lab_tests t
CROSS JOIN (
    SELECT 'pH'            AS param_name, ''       AS unit, 4.50 AS min_range, 8.00 AS max_range, 1 AS display_order UNION ALL
    SELECT 'Specific Gravity', '',                          1.005,              1.030,             2 UNION ALL
    SELECT 'Glucose (Urine)', 'mg/dL',                      0.00,               15.00,             3 UNION ALL
    SELECT 'Protein (Urine)', 'mg/dL',                      0.00,               20.00,             4
) v WHERE t.test_code = 'URN-RE';

-- Vitamin D
INSERT IGNORE INTO test_parameters (test_id, param_name, unit, min_range, max_range, display_order)
SELECT t.test_id, v.param_name, v.unit, v.min_range, v.max_range, v.display_order
FROM lab_tests t
CROSS JOIN (
    SELECT '25-OH Vitamin D' AS param_name, 'ng/mL' AS unit, 30.00 AS min_range, 100.00 AS max_range, 1 AS display_order
) v WHERE t.test_code = 'VIT-D';

-- Vitamin B12
INSERT IGNORE INTO test_parameters (test_id, param_name, unit, min_range, max_range, display_order)
SELECT t.test_id, v.param_name, v.unit, v.min_range, v.max_range, v.display_order
FROM lab_tests t
CROSS JOIN (
    SELECT 'Serum B12 (Cobalamin)' AS param_name, 'pg/mL' AS unit, 200.00 AS min_range, 900.00 AS max_range, 1 AS display_order
) v WHERE t.test_code = 'VIT-B12';

-- Serum Ferritin
INSERT IGNORE INTO test_parameters (test_id, param_name, unit, min_range, max_range, display_order)
SELECT t.test_id, v.param_name, v.unit, v.min_range, v.max_range, v.display_order
FROM lab_tests t
CROSS JOIN (
    SELECT 'Serum Ferritin' AS param_name, 'ng/mL' AS unit, 12.00 AS min_range, 300.00 AS max_range, 1 AS display_order
) v WHERE t.test_code = 'VIT-FER';

-- CRP
INSERT IGNORE INTO test_parameters (test_id, param_name, unit, min_range, max_range, display_order)
SELECT t.test_id, v.param_name, v.unit, v.min_range, v.max_range, v.display_order
FROM lab_tests t
CROSS JOIN (
    SELECT 'C-Reactive Protein' AS param_name, 'mg/L' AS unit, 0.00 AS min_range, 6.00 AS max_range, 1 AS display_order
) v WHERE t.test_code = 'BIO-CRP';

-- ESR
INSERT IGNORE INTO test_parameters (test_id, param_name, unit, min_range, max_range, display_order)
SELECT t.test_id, v.param_name, v.unit, v.min_range, v.max_range, v.display_order
FROM lab_tests t
CROSS JOIN (
    SELECT 'ESR (Male)' AS param_name, 'mm/hr' AS unit, 0.00 AS min_range, 15.00 AS max_range, 1 AS display_order UNION ALL
    SELECT 'ESR (Female)',              'mm/hr',          0.00,              20.00,              2
) v WHERE t.test_code = 'HEM-ESR';

-- PPBS
INSERT IGNORE INTO test_parameters (test_id, param_name, unit, min_range, max_range, display_order)
SELECT t.test_id, v.param_name, v.unit, v.min_range, v.max_range, v.display_order
FROM lab_tests t
CROSS JOIN (
    SELECT 'Post-Prandial Blood Sugar' AS param_name, 'mg/dL' AS unit, 70.00 AS min_range, 140.00 AS max_range, 1 AS display_order
) v WHERE t.test_code = 'DIA-PPBS';


-- ─────────────────────────────────────────────────────────────────────────────
-- PACKAGES (4 test bundles)
-- ─────────────────────────────────────────────────────────────────────────────
INSERT IGNORE INTO packages (package_code, package_name, description, discount_pct) VALUES
('PKG-WELLMAN',   'Wellness Panel (Men)',
 'CBC + LFT + Lipid Profile + RFT + FBS + Vitamin D — comprehensive annual checkup for men.',
 15.00),
('PKG-WELLWOMAN', 'Wellness Panel (Women)',
 'CBC + LFT + TSH + FBS + Vitamin B12 + Serum Ferritin — annual checkup for women.',
 15.00),
('PKG-DIABETES',  'Diabetes Monitoring Pack',
 'FBS + HbA1c + PPBS + Urine R/E + RFT — full diabetes management panel.',
 10.00),
('PKG-THYROID',   'Thyroid Function Pack',
 'TSH + T3 + T4 + FT4 — complete thyroid assessment.',
 12.00);

-- Package ↔ test links
INSERT IGNORE INTO package_tests (package_id, test_id)
SELECT p.package_id, t.test_id
FROM packages p
JOIN lab_tests t ON (
    (p.package_code = 'PKG-WELLMAN'   AND t.test_code IN ('HEM-CBC','BIO-LFT','BIO-LIP','BIO-RFT','END-FBS','VIT-D')) OR
    (p.package_code = 'PKG-WELLWOMAN' AND t.test_code IN ('HEM-CBC','BIO-LFT','THY-TSH','END-FBS','VIT-B12','VIT-FER')) OR
    (p.package_code = 'PKG-DIABETES'  AND t.test_code IN ('END-FBS','BIO-HBA','DIA-PPBS','URN-RE','BIO-RFT')) OR
    (p.package_code = 'PKG-THYROID'   AND t.test_code IN ('THY-TSH','THY-T3','THY-T4','THY-FT4'))
);


-- ─────────────────────────────────────────────────────────────────────────────
-- BOOKINGS (20+ bookings spread across all statuses)
-- ─────────────────────────────────────────────────────────────────────────────
-- We disable the state-machine trigger for seed insertion (it only affects UPDATE,
-- so INSERT with any status is fine — trigger fires on BEFORE UPDATE).

-- Booking 1: Completed (patient1, CBC+LFT) — verified, report unlocked
INSERT IGNORE INTO bookings
    (booking_ref, patient_id, appointment_date, appointment_slot,
     booking_status, collection_type, created_at)
SELECT 'BK-SEED-0001', u.user_id, DATE_SUB(CURDATE(),INTERVAL 10 DAY), '08:00 AM - 10:00 AM',
       'Completed', 'Lab', DATE_SUB(NOW(), INTERVAL 10 DAY)
FROM users u WHERE u.email = 'patient1@medlab.pk';

INSERT IGNORE INTO booking_items (booking_id, test_id, price_at_booking, item_status)
SELECT b.booking_id, t.test_id, t.price, 'Report_Ready'
FROM bookings b JOIN lab_tests t ON t.test_code IN ('HEM-CBC','BIO-LFT')
WHERE b.booking_ref = 'BK-SEED-0001';

INSERT IGNORE INTO invoices (booking_id, invoice_number, total_amount, payment_status, payment_method, received_by, paid_at)
SELECT b.booking_id, 'INV-SEED-0001', 3000.00, 'Paid', 'Cash_At_Counter',
       (SELECT user_id FROM users WHERE email='receptionist@medlab.pk'),
       DATE_SUB(NOW(), INTERVAL 10 DAY)
FROM bookings b WHERE b.booking_ref = 'BK-SEED-0001';

-- Booking 2: Completed (patient2, Lipid Profile + FBS)
INSERT IGNORE INTO bookings
    (booking_ref, patient_id, appointment_date, appointment_slot,
     booking_status, collection_type, created_at)
SELECT 'BK-SEED-0002', u.user_id, DATE_SUB(CURDATE(),INTERVAL 8 DAY), '10:00 AM - 12:00 PM',
       'Completed', 'Lab', DATE_SUB(NOW(), INTERVAL 8 DAY)
FROM users u WHERE u.email = 'patient2@medlab.pk';

INSERT IGNORE INTO booking_items (booking_id, test_id, price_at_booking, item_status)
SELECT b.booking_id, t.test_id, t.price, 'Report_Ready'
FROM bookings b JOIN lab_tests t ON t.test_code IN ('BIO-LIP','END-FBS')
WHERE b.booking_ref = 'BK-SEED-0002';

INSERT IGNORE INTO invoices (booking_id, invoice_number, total_amount, payment_status, payment_method, received_by, paid_at)
SELECT b.booking_id, 'INV-SEED-0002', 2700.00, 'Paid', 'Card',
       (SELECT user_id FROM users WHERE email='receptionist@medlab.pk'),
       DATE_SUB(NOW(), INTERVAL 8 DAY)
FROM bookings b WHERE b.booking_ref = 'BK-SEED-0002';

-- Booking 3: Completed (patient3, RFT)
INSERT IGNORE INTO bookings
    (booking_ref, patient_id, appointment_date, appointment_slot,
     booking_status, collection_type, created_at)
SELECT 'BK-SEED-0003', u.user_id, DATE_SUB(CURDATE(),INTERVAL 6 DAY), '08:00 AM - 10:00 AM',
       'Completed', 'Lab', DATE_SUB(NOW(), INTERVAL 6 DAY)
FROM users u WHERE u.email = 'patient3@medlab.pk';

INSERT IGNORE INTO booking_items (booking_id, test_id, price_at_booking, item_status)
SELECT b.booking_id, t.test_id, t.price, 'Report_Ready'
FROM bookings b JOIN lab_tests t ON t.test_code = 'BIO-RFT'
WHERE b.booking_ref = 'BK-SEED-0003';

INSERT IGNORE INTO invoices (booking_id, invoice_number, total_amount, payment_status, payment_method, received_by, paid_at)
SELECT b.booking_id, 'INV-SEED-0003', 1600.00, 'Paid', 'Online',
       (SELECT user_id FROM users WHERE email='receptionist@medlab.pk'),
       DATE_SUB(NOW(), INTERVAL 6 DAY)
FROM bookings b WHERE b.booking_ref = 'BK-SEED-0003';

-- Booking 4: Completed (patient4, CBC+TSH)
INSERT IGNORE INTO bookings
    (booking_ref, patient_id, appointment_date, appointment_slot,
     booking_status, collection_type, created_at)
SELECT 'BK-SEED-0004', u.user_id, DATE_SUB(CURDATE(),INTERVAL 5 DAY), '10:00 AM - 12:00 PM',
       'Completed', 'Lab', DATE_SUB(NOW(), INTERVAL 5 DAY)
FROM users u WHERE u.email = 'patient4@medlab.pk';

INSERT IGNORE INTO booking_items (booking_id, test_id, price_at_booking, item_status)
SELECT b.booking_id, t.test_id, t.price, 'Report_Ready'
FROM bookings b JOIN lab_tests t ON t.test_code IN ('HEM-CBC','THY-TSH')
WHERE b.booking_ref = 'BK-SEED-0004';

INSERT IGNORE INTO invoices (booking_id, invoice_number, total_amount, payment_status, payment_method, received_by, paid_at)
SELECT b.booking_id, 'INV-SEED-0004', 2400.00, 'Paid', 'Cash_At_Counter',
       (SELECT user_id FROM users WHERE email='receptionist@medlab.pk'),
       DATE_SUB(NOW(), INTERVAL 5 DAY)
FROM bookings b WHERE b.booking_ref = 'BK-SEED-0004';

-- Booking 5: Completed (patient5, Vitamin D — result is LOW to test flags)
INSERT IGNORE INTO bookings
    (booking_ref, patient_id, appointment_date, appointment_slot,
     booking_status, collection_type, created_at)
SELECT 'BK-SEED-0005', u.user_id, DATE_SUB(CURDATE(),INTERVAL 4 DAY), '02:00 PM - 04:00 PM',
       'Completed', 'Home', DATE_SUB(NOW(), INTERVAL 4 DAY)
FROM users u WHERE u.email = 'patient5@medlab.pk';

INSERT IGNORE INTO booking_items (booking_id, test_id, price_at_booking, item_status)
SELECT b.booking_id, t.test_id, t.price, 'Report_Ready'
FROM bookings b JOIN lab_tests t ON t.test_code = 'VIT-D'
WHERE b.booking_ref = 'BK-SEED-0005';

INSERT IGNORE INTO invoices (booking_id, invoice_number, total_amount, payment_status, payment_method, received_by, paid_at)
SELECT b.booking_id, 'INV-SEED-0005', 2500.00, 'Paid', 'Online',
       (SELECT user_id FROM users WHERE email='receptionist@medlab.pk'),
       DATE_SUB(NOW(), INTERVAL 4 DAY)
FROM bookings b WHERE b.booking_ref = 'BK-SEED-0005';

-- ─────────────────────────────────────────────────────────────────────────────
-- SAMPLES for completed bookings
-- ─────────────────────────────────────────────────────────────────────────────
INSERT IGNORE INTO samples (item_id, barcode_string, collected_by, collected_at, sample_status)
SELECT bi.item_id,
       CONCAT('SMP-SEED-', LPAD(bi.item_id, 5, '0')),
       (SELECT user_id FROM users WHERE email='collector@medlab.pk'),
       DATE_SUB(NOW(), INTERVAL 9 DAY),
       'Analyzed'
FROM booking_items bi
JOIN bookings b ON bi.booking_id = b.booking_id
WHERE b.booking_ref IN ('BK-SEED-0001','BK-SEED-0002','BK-SEED-0003','BK-SEED-0004','BK-SEED-0005');


-- ─────────────────────────────────────────────────────────────────────────────
-- TEST RESULTS for completed bookings (mix of NORMAL, HIGH, LOW)
-- Trigger trg_auto_flag_test_result fires on insert and sets flag_status automatically.
-- ─────────────────────────────────────────────────────────────────────────────

-- Booking 1: CBC + LFT for patient1 (Hb is LOW at 11.5, WBC HIGH at 12.5)
INSERT IGNORE INTO test_results (item_id, param_id, measured_value, technician_id, verified_by, pathologist_verified_at)
SELECT bi.item_id, tp.param_id,
       CASE tp.param_name
           WHEN 'Hemoglobin (Hb)'             THEN 11.50  -- LOW (normal 13-17)
           WHEN 'Total Leukocyte Count (WBC)'  THEN 12.50  -- HIGH (normal 4-11)
           WHEN 'Platelet Count'               THEN 280.00 -- NORMAL
           WHEN 'Red Blood Cell Count (RBC)'   THEN 4.80   -- NORMAL
           WHEN 'Hematocrit (PCV)'             THEN 44.00  -- NORMAL
           WHEN 'Total Bilirubin'              THEN 0.80   -- NORMAL
           WHEN 'SGPT (ALT)'                   THEN 45.00  -- NORMAL
           WHEN 'SGOT (AST)'                   THEN 38.00  -- NORMAL
           WHEN 'Alkaline Phosphatase (ALP)'   THEN 95.00  -- NORMAL
           ELSE 0.00
       END,
       (SELECT user_id FROM users WHERE email='technician@medlab.pk'),
       (SELECT user_id FROM users WHERE email='pathologist@medlab.pk'),
       DATE_SUB(NOW(), INTERVAL 9 DAY)
FROM booking_items bi
JOIN bookings b  ON bi.booking_id = b.booking_id
JOIN lab_tests lt ON bi.test_id = lt.test_id
JOIN test_parameters tp ON tp.test_id = lt.test_id
WHERE b.booking_ref = 'BK-SEED-0001';

-- Booking 2: Lipid Profile (Total Cholesterol HIGH) + FBS (NORMAL)
INSERT IGNORE INTO test_results (item_id, param_id, measured_value, technician_id, verified_by, pathologist_verified_at)
SELECT bi.item_id, tp.param_id,
       CASE tp.param_name
           WHEN 'Total Cholesterol'           THEN 230.00 -- HIGH (normal <200)
           WHEN 'Triglycerides'               THEN 180.00 -- HIGH (normal <150)
           WHEN 'HDL Cholesterol'             THEN 38.00  -- LOW (normal 40-60)
           WHEN 'LDL Cholesterol'             THEN 155.00 -- HIGH (normal <100)
           WHEN 'Plasma Glucose (Fasting)'    THEN 85.00  -- NORMAL
           ELSE 0.00
       END,
       (SELECT user_id FROM users WHERE email='technician@medlab.pk'),
       (SELECT user_id FROM users WHERE email='pathologist@medlab.pk'),
       DATE_SUB(NOW(), INTERVAL 7 DAY)
FROM booking_items bi
JOIN bookings b  ON bi.booking_id = b.booking_id
JOIN lab_tests lt ON bi.test_id = lt.test_id
JOIN test_parameters tp ON tp.test_id = lt.test_id
WHERE b.booking_ref = 'BK-SEED-0002';

-- Booking 3: RFT — all NORMAL
INSERT IGNORE INTO test_results (item_id, param_id, measured_value, technician_id, verified_by, pathologist_verified_at)
SELECT bi.item_id, tp.param_id,
       CASE tp.param_name
           WHEN 'Serum Creatinine'        THEN 1.00  -- NORMAL
           WHEN 'Blood Urea Nitrogen (BUN)' THEN 14.00 -- NORMAL
           WHEN 'Serum Uric Acid'         THEN 5.50  -- NORMAL
           ELSE 0.00
       END,
       (SELECT user_id FROM users WHERE email='technician@medlab.pk'),
       (SELECT user_id FROM users WHERE email='pathologist@medlab.pk'),
       DATE_SUB(NOW(), INTERVAL 5 DAY)
FROM booking_items bi
JOIN bookings b  ON bi.booking_id = b.booking_id
JOIN lab_tests lt ON bi.test_id = lt.test_id
JOIN test_parameters tp ON tp.test_id = lt.test_id
WHERE b.booking_ref = 'BK-SEED-0003';

-- Booking 5: Vitamin D — LOW (deficient at 12 ng/mL)
INSERT IGNORE INTO test_results (item_id, param_id, measured_value, technician_id, verified_by, pathologist_verified_at)
SELECT bi.item_id, tp.param_id,
       12.00,  -- LOW (normal 30-100 ng/mL)
       (SELECT user_id FROM users WHERE email='technician@medlab.pk'),
       (SELECT user_id FROM users WHERE email='pathologist@medlab.pk'),
       DATE_SUB(NOW(), INTERVAL 3 DAY)
FROM booking_items bi
JOIN bookings b  ON bi.booking_id = b.booking_id
JOIN lab_tests lt ON bi.test_id = lt.test_id
JOIN test_parameters tp ON tp.test_id = lt.test_id
WHERE b.booking_ref = 'BK-SEED-0005';


-- ─────────────────────────────────────────────────────────────────────────────
-- MORE BOOKINGS — in-progress stages
-- ─────────────────────────────────────────────────────────────────────────────

-- Booking 6: Pending_Verification (patient6, CBC) — technician done, awaiting pathologist
INSERT IGNORE INTO bookings (booking_ref, patient_id, appointment_date, appointment_slot, booking_status, collection_type)
SELECT 'BK-SEED-0006', u.user_id, DATE_SUB(CURDATE(),INTERVAL 2 DAY), '08:00 AM - 10:00 AM',
       'Pending_Verification', 'Lab'
FROM users u WHERE u.email = 'patient6@medlab.pk';

INSERT IGNORE INTO booking_items (booking_id, test_id, price_at_booking, item_status)
SELECT b.booking_id, t.test_id, t.price, 'Report_Ready'
FROM bookings b JOIN lab_tests t ON t.test_code = 'HEM-CBC'
WHERE b.booking_ref = 'BK-SEED-0006';

INSERT IGNORE INTO invoices (booking_id, invoice_number, total_amount, payment_status, payment_method, received_by, paid_at)
SELECT b.booking_id, 'INV-SEED-0006', 1200.00, 'Paid', 'Cash_At_Counter',
       (SELECT user_id FROM users WHERE email='receptionist@medlab.pk'), DATE_SUB(NOW(), INTERVAL 2 DAY)
FROM bookings b WHERE b.booking_ref = 'BK-SEED-0006';

INSERT IGNORE INTO samples (item_id, barcode_string, collected_by, collected_at, sample_status)
SELECT bi.item_id, CONCAT('SMP-SEED-', LPAD(bi.item_id+100, 5, '0')),
       (SELECT user_id FROM users WHERE email='collector@medlab.pk'), DATE_SUB(NOW(), INTERVAL 2 DAY), 'Analyzed'
FROM booking_items bi JOIN bookings b ON bi.booking_id=b.booking_id
WHERE b.booking_ref = 'BK-SEED-0006';

-- Booking 7: In_Analysis (patient7, LFT)
INSERT IGNORE INTO bookings (booking_ref, patient_id, appointment_date, appointment_slot, booking_status, collection_type)
SELECT 'BK-SEED-0007', u.user_id, DATE_SUB(CURDATE(),INTERVAL 1 DAY), '10:00 AM - 12:00 PM',
       'In_Analysis', 'Lab'
FROM users u WHERE u.email = 'patient7@medlab.pk';

INSERT IGNORE INTO booking_items (booking_id, test_id, price_at_booking, item_status)
SELECT b.booking_id, t.test_id, t.price, 'Sample_Collected'
FROM bookings b JOIN lab_tests t ON t.test_code = 'BIO-LFT'
WHERE b.booking_ref = 'BK-SEED-0007';

INSERT IGNORE INTO invoices (booking_id, invoice_number, total_amount, payment_status, payment_method, received_by, paid_at)
SELECT b.booking_id, 'INV-SEED-0007', 1800.00, 'Paid', 'Card',
       (SELECT user_id FROM users WHERE email='receptionist@medlab.pk'), DATE_SUB(NOW(), INTERVAL 1 DAY)
FROM bookings b WHERE b.booking_ref = 'BK-SEED-0007';

INSERT IGNORE INTO samples (item_id, barcode_string, collected_by, collected_at, sample_status)
SELECT bi.item_id, CONCAT('SMP-SEED-', LPAD(bi.item_id+200, 5, '0')),
       (SELECT user_id FROM users WHERE email='collector@medlab.pk'), DATE_SUB(NOW(), INTERVAL 1 DAY), 'Collected'
FROM booking_items bi JOIN bookings b ON bi.booking_id=b.booking_id
WHERE b.booking_ref = 'BK-SEED-0007';

-- Booking 8: Sample_Collected (patient8, Lipid Profile) — collector done, tech not started
INSERT IGNORE INTO bookings (booking_ref, patient_id, appointment_date, appointment_slot, booking_status, collection_type)
SELECT 'BK-SEED-0008', u.user_id, CURDATE(), '08:00 AM - 10:00 AM',
       'Sample_Collected', 'Lab'
FROM users u WHERE u.email = 'patient8@medlab.pk';

INSERT IGNORE INTO booking_items (booking_id, test_id, price_at_booking, item_status)
SELECT b.booking_id, t.test_id, t.price, 'Sample_Collected'
FROM bookings b JOIN lab_tests t ON t.test_code = 'BIO-LIP'
WHERE b.booking_ref = 'BK-SEED-0008';

INSERT IGNORE INTO invoices (booking_id, invoice_number, total_amount, payment_status, payment_method, received_by, paid_at)
SELECT b.booking_id, 'INV-SEED-0008', 2200.00, 'Paid', 'Cash_At_Counter',
       (SELECT user_id FROM users WHERE email='receptionist@medlab.pk'), NOW()
FROM bookings b WHERE b.booking_ref = 'BK-SEED-0008';

INSERT IGNORE INTO samples (item_id, barcode_string, collected_by, collected_at, sample_status)
SELECT bi.item_id, CONCAT('SMP-SEED-', LPAD(bi.item_id+300, 5, '0')),
       (SELECT user_id FROM users WHERE email='collector@medlab.pk'), NOW(), 'Collected'
FROM booking_items bi JOIN bookings b ON bi.booking_id=b.booking_id
WHERE b.booking_ref = 'BK-SEED-0008';

-- Booking 9: Confirmed (patient1, TSH) — payment done, awaiting collector
INSERT IGNORE INTO bookings (booking_ref, patient_id, appointment_date, appointment_slot, booking_status, collection_type)
SELECT 'BK-SEED-0009', u.user_id, DATE_ADD(CURDATE(),INTERVAL 1 DAY), '10:00 AM - 12:00 PM',
       'Confirmed', 'Lab'
FROM users u WHERE u.email = 'patient1@medlab.pk';

INSERT IGNORE INTO booking_items (booking_id, test_id, price_at_booking, item_status)
SELECT b.booking_id, t.test_id, t.price, 'Pending_Sample'
FROM bookings b JOIN lab_tests t ON t.test_code = 'THY-TSH'
WHERE b.booking_ref = 'BK-SEED-0009';

INSERT IGNORE INTO invoices (booking_id, invoice_number, total_amount, payment_status, payment_method, received_by, paid_at)
SELECT b.booking_id, 'INV-SEED-0009', 1200.00, 'Paid', 'Online',
       (SELECT user_id FROM users WHERE email='receptionist@medlab.pk'), NOW()
FROM bookings b WHERE b.booking_ref = 'BK-SEED-0009';

-- Booking 10: Booked (patient2, CBC+RFT) — just booked, no payment yet
INSERT IGNORE INTO bookings (booking_ref, patient_id, appointment_date, appointment_slot, booking_status, collection_type)
SELECT 'BK-SEED-0010', u.user_id, DATE_ADD(CURDATE(),INTERVAL 2 DAY), '02:00 PM - 04:00 PM',
       'Booked', 'Lab'
FROM users u WHERE u.email = 'patient2@medlab.pk';

INSERT IGNORE INTO booking_items (booking_id, test_id, price_at_booking, item_status)
SELECT b.booking_id, t.test_id, t.price, 'Pending_Sample'
FROM bookings b JOIN lab_tests t ON t.test_code IN ('HEM-CBC','BIO-RFT')
WHERE b.booking_ref = 'BK-SEED-0010';

INSERT IGNORE INTO invoices (booking_id, invoice_number, total_amount, payment_status)
SELECT b.booking_id, 'INV-SEED-0010', 2800.00, 'Unpaid'
FROM bookings b WHERE b.booking_ref = 'BK-SEED-0010';

-- Booking 11: Cancelled (patient3)
INSERT IGNORE INTO bookings (booking_ref, patient_id, appointment_date, appointment_slot, booking_status, collection_type)
SELECT 'BK-SEED-0011', u.user_id, DATE_SUB(CURDATE(),INTERVAL 3 DAY), '04:00 PM - 06:00 PM',
       'Cancelled', 'Lab'
FROM users u WHERE u.email = 'patient3@medlab.pk';

INSERT IGNORE INTO booking_items (booking_id, test_id, price_at_booking, item_status)
SELECT b.booking_id, t.test_id, t.price, 'Pending_Sample'
FROM bookings b JOIN lab_tests t ON t.test_code = 'BIO-CRP'
WHERE b.booking_ref = 'BK-SEED-0011';

INSERT IGNORE INTO invoices (booking_id, invoice_number, total_amount, payment_status)
SELECT b.booking_id, 'INV-SEED-0011', 900.00, 'Unpaid'
FROM bookings b WHERE b.booking_ref = 'BK-SEED-0011';

-- Booking 12: Booked + Home collection (patient4, Vitamin D)
INSERT IGNORE INTO bookings (booking_ref, patient_id, appointment_date, appointment_slot, booking_status, collection_type, collection_address)
SELECT 'BK-SEED-0012', u.user_id, DATE_ADD(CURDATE(),INTERVAL 3 DAY), '08:00 AM - 10:00 AM',
       'Booked', 'Home', 'Bungalow 7, DHA Phase 2, Karachi'
FROM users u WHERE u.email = 'patient4@medlab.pk';

INSERT IGNORE INTO booking_items (booking_id, test_id, price_at_booking, item_status)
SELECT b.booking_id, t.test_id, t.price, 'Pending_Sample'
FROM bookings b JOIN lab_tests t ON t.test_code = 'VIT-D'
WHERE b.booking_ref = 'BK-SEED-0012';

INSERT IGNORE INTO invoices (booking_id, invoice_number, total_amount, payment_status)
SELECT b.booking_id, 'INV-SEED-0012', 2500.00, 'Unpaid'
FROM bookings b WHERE b.booking_ref = 'BK-SEED-0012';

-- ─────────────────────────────────────────────────────────────────────────────
-- NOTIFICATIONS (pre-seeded so every role sees them)
-- ─────────────────────────────────────────────────────────────────────────────

-- Admin: new bookings
INSERT IGNORE INTO notifications (user_id, type, title, message, booking_id, is_read)
SELECT u.user_id, 'booking', 'New Booking Received',
       'Booking BK-SEED-0010 created by Usman Tariq. Payment pending.',
       b.booking_id, FALSE
FROM users u, bookings b
WHERE u.email='admin@medlab.pk' AND b.booking_ref='BK-SEED-0010';

-- Receptionist: new booking to process payment
INSERT IGNORE INTO notifications (user_id, type, title, message, booking_id, is_read)
SELECT u.user_id, 'booking', 'New Booking — Payment Due',
       'Booking BK-SEED-0010: Usman Tariq is waiting for payment confirmation.',
       b.booking_id, FALSE
FROM users u, bookings b
WHERE u.email='receptionist@medlab.pk' AND b.booking_ref='BK-SEED-0010';

-- Patient: booking confirmation
INSERT IGNORE INTO notifications (user_id, type, title, message, booking_id, is_read)
SELECT u.user_id, 'booking', 'Booking Confirmed',
       'Your booking BK-SEED-0009 for Thyroid Stimulating Hormone is confirmed. Please arrive on time.',
       b.booking_id, FALSE
FROM users u, bookings b
WHERE u.email='patient1@medlab.pk' AND b.booking_ref='BK-SEED-0009';

-- Collector: sample to collect today
INSERT IGNORE INTO notifications (user_id, type, title, message, booking_id, is_read)
SELECT u.user_id, 'sample', 'Sample Collection Due',
       'Booking BK-SEED-0009: Thyroid sample for Aisha Khan is scheduled for tomorrow.',
       b.booking_id, FALSE
FROM users u, bookings b
WHERE u.email='collector@medlab.pk' AND b.booking_ref='BK-SEED-0009';

-- Technician: sample received, analysis pending
INSERT IGNORE INTO notifications (user_id, type, title, message, booking_id, is_read)
SELECT u.user_id, 'sample', 'Sample Ready for Analysis',
       'Sample SMP-SEED-00307 (Lipid Profile) for Mehwish Butt is ready for analysis.',
       b.booking_id, FALSE
FROM users u, bookings b
WHERE u.email='technician@medlab.pk' AND b.booking_ref='BK-SEED-0007';

-- Pathologist: results awaiting verification
INSERT IGNORE INTO notifications (user_id, type, title, message, booking_id, is_read)
SELECT u.user_id, 'result', 'Results Awaiting Your Approval',
       'CBC results for Ali Hassan (BK-SEED-0006) have been entered and require pathologist verification.',
       b.booking_id, FALSE
FROM users u, bookings b
WHERE u.email='pathologist@medlab.pk' AND b.booking_ref='BK-SEED-0006';

-- Patient: report ready
INSERT IGNORE INTO notifications (user_id, type, title, message, booking_id, is_read)
SELECT u.user_id, 'result', 'Your Report is Ready',
       'Your diagnostic report for Vitamin D (BK-SEED-0005) has been verified and is now available.',
       b.booking_id, FALSE
FROM users u, bookings b
WHERE u.email='patient5@medlab.pk' AND b.booking_ref='BK-SEED-0005';

-- ─────────────────────────────────────────────────────────────────────────────
-- END OF SEED v2
-- ─────────────────────────────────────────────────────────────────────────────
SELECT 'seed_v2.sql applied successfully.' AS status;
"""


if __name__ == "__main__":
    main()
