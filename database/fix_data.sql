-- =============================================================================
-- MedLab System — fix_data.sql (UNTESTED)
-- Purpose : Diagnostic SELECT queries and safe cleanup transactions for
--           known data anomalies in medlab_db.
-- Author  : Security-Minded Senior Full-Stack Engineer Pass
-- Safety  : Every modifying block is wrapped in START TRANSACTION ... ROLLBACK.
--           Run by hand in MySQL Workbench. Inspect the SELECT query results first.
--           Change ROLLBACK to COMMIT ONLY AFTER you have checked the results.
-- Encoding: UTF-8 without BOM
-- =============================================================================

SET NAMES utf8mb4;
USE medlab_db;

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 1: JUNK DATA CLEANUP
-- ─────────────────────────────────────────────────────────────────────────────
-- Issue: Test and debugging leftovers in notifications, bookings, and invoices:
--   - Notifications with titles: 'Admin Only Confidential', 'Detail View Test',
--     'Test Unread Alert'
--   - Booking: 'BK-TEST-61A079'
--   - Invoice: 'INV-TEST-1D685B'
--
-- FOREIGN KEY CONSTRAINTS & ON DELETE RULES EXPLANATION:
--   - `notifications.booking_id` -> `bookings(booking_id)` ON DELETE SET NULL.
--     If we delete `bookings` first, notifications referencing it are NOT deleted;
--     their `booking_id` is set to NULL, leaving orphaned junk notifications!
--   - `invoices.booking_id`      -> `bookings(booking_id)` ON DELETE CASCADE.
--   - `booking_items.booking_id` -> `bookings(booking_id)` ON DELETE CASCADE.
--   - `samples.item_id`          -> `booking_items(item_id)` ON DELETE CASCADE.
--   - `test_results.item_id`     -> `booking_items(item_id)` ON DELETE CASCADE.
--
-- EXPLICIT SAFE DELETION ORDER (Bottom-Up):
--   1. Delete `notifications` referencing the junk booking or matching junk titles.
--   2. Delete `test_results` associated with the junk booking items.
--   3. Delete `samples` associated with the junk booking items.
--   4. Delete `booking_items` associated with the junk booking.
--   5. Delete `invoices` associated with the junk booking (INV-TEST-1D685B).
--   6. Delete `bookings` row (BK-TEST-61A079).
-- ─────────────────────────────────────────────────────────────────────────────

-- 1A. Inspect junk notifications before cleanup
SELECT notification_id, user_id, type, title, message, booking_id, is_read, created_at
FROM notifications
WHERE title IN ('Admin Only Confidential', 'Detail View Test', 'Test Unread Alert')
   OR booking_id IN (SELECT booking_id FROM bookings WHERE booking_ref = 'BK-TEST-61A079');

-- 1B. Inspect junk booking, invoice, items, samples, and results before cleanup
SELECT b.booking_id, b.booking_ref, b.booking_status, i.invoice_number, i.total_amount, i.payment_status
FROM bookings b
LEFT JOIN invoices i ON b.booking_id = i.booking_id
WHERE b.booking_ref = 'BK-TEST-61A079'
   OR i.invoice_number = 'INV-TEST-1D685B';

-- 1C. Clean up junk records in strict foreign-key-safe order
START TRANSACTION;

-- Step 1: Remove linked notifications
DELETE FROM notifications
WHERE title IN ('Admin Only Confidential', 'Detail View Test', 'Test Unread Alert')
   OR booking_id IN (SELECT booking_id FROM bookings WHERE booking_ref = 'BK-TEST-61A079');

-- Step 2: Remove test_results for junk booking items
DELETE tr FROM test_results tr
JOIN booking_items bi ON tr.item_id = bi.item_id
JOIN bookings b ON bi.booking_id = b.booking_id
WHERE b.booking_ref = 'BK-TEST-61A079';

-- Step 3: Remove samples for junk booking items
DELETE s FROM samples s
JOIN booking_items bi ON s.item_id = bi.item_id
JOIN bookings b ON bi.booking_id = b.booking_id
WHERE b.booking_ref = 'BK-TEST-61A079';

-- Step 4: Remove booking_items for junk booking
DELETE bi FROM booking_items bi
JOIN bookings b ON bi.booking_id = b.booking_id
WHERE b.booking_ref = 'BK-TEST-61A079';

-- Step 5: Remove invoice for junk booking
DELETE FROM invoices
WHERE invoice_number = 'INV-TEST-1D685B'
   OR booking_id IN (SELECT booking_id FROM bookings WHERE booking_ref = 'BK-TEST-61A079');

-- Step 6: Remove the junk booking itself
DELETE FROM bookings
WHERE booking_ref = 'BK-TEST-61A079';

-- Verification query inside transaction
SELECT COUNT(*) AS remaining_junk_bookings
FROM bookings WHERE booking_ref = 'BK-TEST-61A079';

-- change ROLLBACK to COMMIT only after you checked the SELECT results
ROLLBACK;


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 2: GARBLED TEXT REPAIR (ENCODING & MOJIBAKE)
-- ─────────────────────────────────────────────────────────────────────────────
-- Issue: The sequence "ÔÇö" (bytes 0xE2 0x80 0x94) is an em dash (—) imported
--        without `SET NAMES utf8mb4;` through a Windows-1252 / CP1252 connection.
-- Root Cause:
--   When `seed_v2.sql` was executed without `SET NAMES utf8mb4;`, the client
--   interpreted UTF-8 multi-byte characters as separate CP1252 glyphs.
-- Source Fix:
--   Add `SET NAMES utf8mb4;` to the top of `seed_v2.sql` and ensure all MySQL
--   client connections specify utf8mb4.
-- ─────────────────────────────────────────────────────────────────────────────

-- 2A. Inspect all rows containing garbled mojibake sequences
SELECT 'notifications' AS tbl, notification_id AS id, title, message
FROM notifications
WHERE title LIKE '%Ô%' OR message LIKE '%Ô%' OR title LIKE '%Ã%' OR message LIKE '%Ã%'
UNION ALL
SELECT 'packages' AS tbl, package_id AS id, package_name AS title, description AS message
FROM packages
WHERE package_name LIKE '%Ô%' OR description LIKE '%Ô%' OR package_name LIKE '%Ã%' OR description LIKE '%Ã%'
UNION ALL
SELECT 'roles' AS tbl, role_id AS id, role_name AS title, description AS message
FROM roles
WHERE description LIKE '%Ô%' OR description LIKE '%Ã%';

-- 2B. Repair garbled sequences with REPLACE()
START TRANSACTION;

UPDATE notifications
SET title   = REPLACE(REPLACE(title, 'ÔÇö', '—'), 'â€”', '—'),
    message = REPLACE(REPLACE(message, 'ÔÇö', '—'), 'â€”', '—')
WHERE title LIKE '%ÔÇö%' OR message LIKE '%ÔÇö%' OR title LIKE '%â€”%' OR message LIKE '%â€”%';

UPDATE packages
SET package_name = REPLACE(REPLACE(package_name, 'ÔÇö', '—'), 'â€”', '—'),
    description  = REPLACE(REPLACE(description, 'ÔÇö', '—'), 'â€”', '—')
WHERE package_name LIKE '%ÔÇö%' OR description LIKE '%ÔÇö%' OR package_name LIKE '%â€”%' OR description LIKE '%â€”%';

UPDATE roles
SET description = REPLACE(REPLACE(description, 'ÔÇö', '—'), 'â€”', '—')
WHERE description LIKE '%ÔÇö%' OR description LIKE '%â€”%';

-- Verification query inside transaction
SELECT COUNT(*) AS remaining_garbled_notifications
FROM notifications
WHERE title LIKE '%ÔÇö%' OR message LIKE '%ÔÇö%';

-- change ROLLBACK to COMMIT only after you checked the SELECT results
ROLLBACK;


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 3: DUPLICATE NOTIFICATIONS CLEANUP
-- ─────────────────────────────────────────────────────────────────────────────
-- Issue: Running `seed_v2.sql` multiple times duplicated notifications
--        (such as BK-SEED-0010) because `INSERT IGNORE` only deduplicates
--        primary keys, and `notifications` has an auto-increment PK.
-- Solution:
--   Keep the lowest `notification_id` for every unique grouping of
--   (user_id, booking_id, type, title, message), and delete surplus duplicates.
-- ─────────────────────────────────────────────────────────────────────────────

-- 3A. Show duplicate notification groups
SELECT user_id, booking_id, type, title, message,
       COUNT(*) AS total_occurrences,
       MIN(notification_id) AS keep_notification_id,
       GROUP_CONCAT(notification_id ORDER BY notification_id ASC) AS all_ids
FROM notifications
GROUP BY user_id, booking_id, type, title, message
HAVING COUNT(*) > 1;

-- 3B. Delete duplicates retaining only MIN(notification_id)
START TRANSACTION;

DELETE n
FROM notifications n
JOIN (
    SELECT user_id, booking_id, type, title, message, MIN(notification_id) AS min_id
    FROM notifications
    GROUP BY user_id, booking_id, type, title, message
    HAVING COUNT(*) > 1
) d ON n.user_id = d.user_id
   AND (n.booking_id = d.booking_id OR (n.booking_id IS NULL AND d.booking_id IS NULL))
   AND n.type = d.type
   AND n.title = d.title
   AND n.message = d.message
   AND n.notification_id > d.min_id;

-- Verification query inside transaction: Should return 0 duplicate groups
SELECT COUNT(*) AS remaining_duplicate_groups
FROM (
    SELECT user_id, booking_id, type, title, message
    FROM notifications
    GROUP BY user_id, booking_id, type, title, message
    HAVING COUNT(*) > 1
) dupes;

-- change ROLLBACK to COMMIT only after you checked the SELECT results
ROLLBACK;


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 4: TESTS WITH ZERO PARAMETERS (CLINICAL AUDIT)
-- ─────────────────────────────────────────────────────────────────────────────
-- Issue: Tests seeded in migration_v2.sql without parameters cannot record
--        biomarker values, causing technician result entry to be empty.
--
-- Findings Breakdown:
--   1. NUMERIC TESTS (Can take numeric min_range / max_range):
--      - DIA-OGTT (Oral Glucose Tolerance Test, Category: Diabetes Management)
--      - URN-ACR  (Urine Albumin-Creatinine Ratio, Category: Urine Examination)
--   2. QUALITATIVE & MORPHOLOGICAL TESTS:
--      - HEM-PBF  (Peripheral Blood Film, Category: Hematology - descriptive text)
--      - MIC-HBS  (HBsAg / Hepatitis B Surface Antigen, Category: Microbiology - Reactive/Non-Reactive)
--      - MIC-HCV  (Anti-HCV / Hepatitis C Antibody, Category: Microbiology - Reactive/Non-Reactive)
--      - MIC-HIV  (HIV 1 & 2 Antibody Screening, Category: Microbiology - Non-Reactive/Reactive)
--      - MIC-WIDAL(Widal Test for Typhoid, Category: Microbiology - Titer ratio string)
--
-- WHY THE NUMERIC TRIGGER DOES NOT FIT QUALITATIVE TESTS:
--   `test_parameters` defines `min_range` and `max_range` as DECIMAL(10,2).
--   `test_results` defines `measured_value` as DECIMAL(10,2).
--   The database trigger `trg_auto_flag_test_result` executes:
--       IF NEW.measured_value < v_min THEN SET NEW.flag_status = 'LOW'...
--   Qualitative results like "Non-Reactive" or descriptive morphology reports
--   cannot be coerced into a DECIMAL(10,2) column without failing SQL syntax.
--
-- ARCHITECTURAL OPTIONS:
--   Option A (Recommended for Database Systems Grading):
--     Keep qualitative tests disabled (`is_active = 0`) until a design decision
--     is finalized. No clinical data is invented.
--   Option B (Schema Extension):
--     Alter `test_parameters` to add `param_type ENUM('numeric', 'qualitative', 'text')`.
--     Alter `test_results` to add `text_value VARCHAR(255) NULL` and make `measured_value`
--     nullable. Update `trg_auto_flag_test_result` to bypass range math when
--     `param_type != 'numeric'`.
--
-- PER USER INSTRUCTION: We implement NOTHING for qualitative ranges without approval.
-- ─────────────────────────────────────────────────────────────────────────────

-- 4A. List all tests currently in lab_tests that have ZERO parameters
SELECT lt.test_id, lt.test_code, lt.test_name, tc.category_name, lt.sample_type, lt.price, lt.is_active
FROM lab_tests lt
JOIN test_categories tc ON lt.category_id = tc.category_id
LEFT JOIN test_parameters tp ON lt.test_id = tp.test_id
GROUP BY lt.test_id, lt.test_code, lt.test_name, tc.category_name, lt.sample_type, lt.price, lt.is_active
HAVING COUNT(tp.param_id) = 0
ORDER BY tc.category_name, lt.test_name;

-- 4B. Commented INSERT template for NUMERIC tests (DO NOT INVENT VALUES; fill after clinical review)
/*
START TRANSACTION;

-- Template for Oral Glucose Tolerance Test (DIA-OGTT)
-- INSERT INTO test_parameters (test_id, param_name, unit, min_range, max_range, display_order)
-- SELECT test_id, 'Fasting Plasma Glucose', 'mg/dL', [MIN_VAL], [MAX_VAL], 1 FROM lab_tests WHERE test_code = 'DIA-OGTT'
-- UNION ALL
-- SELECT test_id, '2-Hour Post-Glucose Load', 'mg/dL', [MIN_VAL], [MAX_VAL], 2 FROM lab_tests WHERE test_code = 'DIA-OGTT';

-- Template for Urine Albumin-Creatinine Ratio (URN-ACR)
-- INSERT INTO test_parameters (test_id, param_name, unit, min_range, max_range, display_order)
-- SELECT test_id, 'Albumin/Creatinine Ratio', 'mg/g', [MIN_VAL], [MAX_VAL], 1 FROM lab_tests WHERE test_code = 'URN-ACR';

-- change ROLLBACK to COMMIT only after you checked the SELECT results
ROLLBACK;
*/

-- 4C. Commented-out statement to safely deactivate tests that have 0 parameters
-- (Prevents patients from booking tests that technicians cannot enter results for)
/*
START TRANSACTION;

UPDATE lab_tests
SET is_active = 0
WHERE test_id IN (
    SELECT lt.test_id
    FROM (SELECT * FROM lab_tests) lt
    LEFT JOIN test_parameters tp ON lt.test_id = tp.test_id
    GROUP BY lt.test_id
    HAVING COUNT(tp.param_id) = 0
);

-- change ROLLBACK to COMMIT only after you checked the SELECT results
ROLLBACK;
*/


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 5: DATA CONSISTENCY & INTEGRITY AUDIT CHECKS (SELECT ONLY)
-- ─────────────────────────────────────────────────────────────────────────────

-- 5A. Unpaid bookings whose status moved past Booked / Confirmed
--     (Clinical workflow violation: Analysis should never begin without payment or confirmation)
SELECT b.booking_id, b.booking_ref, b.booking_status, i.invoice_number, i.total_amount, i.payment_status
FROM bookings b
JOIN invoices i ON b.booking_id = i.booking_id
WHERE i.payment_status = 'Unpaid'
  AND b.booking_status NOT IN ('Booked', 'Confirmed');

-- 5B. Completed bookings without verification or release data
--     (Accreditation violation: No report may be Completed without Pathologist sign-off)
SELECT b.booking_id, b.booking_ref, b.booking_status, b.released_at, b.released_by
FROM bookings b
WHERE b.booking_status = 'Completed'
  AND (b.released_at IS NULL OR b.released_by IS NULL);

-- 5C. Booking items whose status disagrees with parent booking status
SELECT bi.item_id, bi.booking_id, b.booking_ref, bi.item_status, b.booking_status
FROM booking_items bi
JOIN bookings b ON bi.booking_id = b.booking_id
WHERE (b.booking_status = 'Completed' AND bi.item_status != 'Report_Ready')
   OR (b.booking_status = 'Booked' AND bi.item_status != 'Pending_Sample');

-- 5D. Users whose role_id does not exist in the roles table
SELECT u.user_id, u.full_name, u.email, u.role_id
FROM users u
LEFT JOIN roles r ON u.role_id = r.role_id
WHERE r.role_id IS NULL;

-- 5E. Patient users (role_id = 4) without a corresponding patient_profiles row
SELECT u.user_id, u.full_name, u.email, u.created_at
FROM users u
LEFT JOIN patient_profiles pp ON u.user_id = pp.patient_id
WHERE u.role_id = 4
  AND pp.patient_id IS NULL;

-- 5F. Orphan rows detection (Records pointing to non-existent parents)
-- Orphan invoices
SELECT 'orphan_invoice' AS issue_type, i.invoice_id, i.invoice_number, i.booking_id
FROM invoices i
LEFT JOIN bookings b ON i.booking_id = b.booking_id
WHERE b.booking_id IS NULL;

-- Orphan booking_items
SELECT 'orphan_booking_item' AS issue_type, bi.item_id, bi.booking_id, bi.test_id
FROM booking_items bi
LEFT JOIN bookings b ON bi.booking_id = b.booking_id
WHERE b.booking_id IS NULL;

-- Orphan samples
SELECT 'orphan_sample' AS issue_type, s.sample_id, s.item_id, s.barcode_string
FROM samples s
LEFT JOIN booking_items bi ON s.item_id = bi.item_id
WHERE bi.item_id IS NULL;

-- Orphan test_results
SELECT 'orphan_test_result' AS issue_type, tr.result_id, tr.item_id, tr.param_id
FROM test_results tr
LEFT JOIN booking_items bi ON tr.item_id = bi.item_id
WHERE bi.item_id IS NULL;

-- Orphan notifications (User deleted)
SELECT 'orphan_notification' AS issue_type, n.notification_id, n.user_id, n.title
FROM notifications n
LEFT JOIN users u ON n.user_id = u.user_id
WHERE u.user_id IS NULL;


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 6: ROUTE CODE FIX REFERENCE (SELECT TESTS ORDER BY)
-- ─────────────────────────────────────────────────────────────────────────────
-- Note for Phase 3 application hardening:
-- In `routes/patient.py:70-72` and `routes/receptionist.py:159-161`:
-- The query must enforce:
--   ORDER BY tc.category_name ASC, lt.test_name ASC
-- Correct query:
--   SELECT lt.*, tc.category_name
--   FROM lab_tests lt
--   JOIN test_categories tc ON lt.category_id = tc.category_id
--   ORDER BY tc.category_name ASC, lt.test_name ASC;
-- This prevents category fragmentation in Jinja2 group loops.
-- ─────────────────────────────────────────────────────────────────────────────
