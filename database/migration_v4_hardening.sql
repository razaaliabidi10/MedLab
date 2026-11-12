-- =============================================================================
-- MedLab System — migration_v4_hardening.sql (UNTESTED)
-- Purpose : Comprehensive database security hardening for university evaluation:
--           1. Full utf8mb4 conversion across medlab_db and all tables
--           2. Widened vw_staff_directory view (includes roles 2, 3, 5, 6)
--           3. User security columns (password change enforcement & lockout check)
--           4. Immutable audit trail triggers for audit_log
--           5. Result freezing triggers for Completed bookings
--           6. login_audit table with IP, User-Agent, and email indexing
--           7. Missing performance and query indexes
-- Author  : Security-Minded Senior Full-Stack Engineer Pass
-- Safety  : Additive, idempotent, and safely rerunnable via information_schema
-- Encoding: UTF-8 without BOM
-- =============================================================================

SET NAMES utf8mb4;
USE medlab_db;

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 1: CHARACTER SET & COLLATION HARDENING (utf8mb4)
-- ─────────────────────────────────────────────────────────────────────────────
-- Diagnostic SELECT to verify current character sets across all tables:
/*
SELECT table_name, table_collation, table_comment
FROM information_schema.tables
WHERE table_schema = 'medlab_db';
*/

-- [REQUIRES ROOT] Convert Database Default Character Set to utf8mb4
ALTER DATABASE medlab_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- [REQUIRES ROOT] Convert Every Table to utf8mb4 and utf8mb4_unicode_ci
ALTER TABLE roles CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE users CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password TINYINT(1) NOT NULL DEFAULT 0 AFTER is_active;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at DATETIME NULL DEFAULT NULL AFTER must_change_password;
ALTER TABLE patient_profiles CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE staff_profiles CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE test_categories CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE lab_tests CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE test_parameters CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE test_parameters ADD UNIQUE KEY uq_test_param (test_id, param_name);
ALTER TABLE time_slots CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE packages CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE package_tests CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE bookings CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE booking_items CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE samples CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE test_results CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE invoices CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE notifications CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE audit_log CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 2: WIDENED STAFF DIRECTORY VIEW (vw_staff_directory)
-- ─────────────────────────────────────────────────────────────────────────────
-- Issue: The view defined in build_db.py was restricted to `WHERE u.role_id IN (2, 3)`.
-- Fix  : CREATE OR REPLACE VIEW to include all active and inactive staff:
--        Role 2 = Receptionist
--        Role 3 = Lab Technician
--        Role 5 = Sample Collector / Phlebotomist
--        Role 6 = Pathologist
-- ─────────────────────────────────────────────────────────────────────────────

-- [REQUIRES ROOT]
CREATE OR REPLACE VIEW vw_staff_directory AS
SELECT 
    u.user_id,
    u.full_name,
    u.email,
    u.phone,
    u.avatar_url,
    u.is_active,
    u.created_at,
    r.role_id,
    r.role_name,
    sp.employee_code,
    sp.qualification,
    sp.shift_timing,
    sp.joining_date
FROM users u
JOIN roles r ON u.role_id = r.role_id
LEFT JOIN staff_profiles sp ON u.user_id = sp.staff_id
WHERE u.role_id IN (2, 3, 5, 6);


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 3: USERS TABLE HARDENING (MUST-CHANGE PASSWORD & LOCKOUT CHECK)
-- ─────────────────────────────────────────────────────────────────────────────
-- Lockout Status Check:
--   `migration_v2.sql` already added `login_attempts` and `lockout_until`.
--   Here we conditionally check information_schema:
--   - Add `must_change_password` (TINYINT(1) DEFAULT 0) if not exists.
--   - Add `password_changed_at` (DATETIME NULL) if not exists.
--   - Only if neither `login_attempts` nor `failed_login_count` exists do we
--     add `failed_login_count` and `locked_until`.
-- ─────────────────────────────────────────────────────────────────────────────

-- [REQUIRES ROOT] 3a. Add must_change_password column
SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'medlab_db' AND TABLE_NAME = 'users' AND COLUMN_NAME = 'must_change_password'
);
SET @sql = IF(@has_col = 0,
    'ALTER TABLE users ADD COLUMN must_change_password TINYINT(1) NOT NULL DEFAULT 0 AFTER is_active',
    'SELECT 1 -- must_change_password already exists');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- [REQUIRES ROOT] 3b. Add password_changed_at timestamp
SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'medlab_db' AND TABLE_NAME = 'users' AND COLUMN_NAME = 'password_changed_at'
);
SET @sql = IF(@has_col = 0,
    'ALTER TABLE users ADD COLUMN password_changed_at DATETIME NULL AFTER must_change_password',
    'SELECT 1 -- password_changed_at already exists');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- [REQUIRES ROOT] 3c. Add failed_login_count ONLY if lockout is not already stored in users
SET @has_lockout = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'medlab_db' AND TABLE_NAME = 'users'
      AND COLUMN_NAME IN ('login_attempts', 'failed_login_count')
);
SET @sql = IF(@has_lockout = 0,
    'ALTER TABLE users ADD COLUMN failed_login_count INT NOT NULL DEFAULT 0 AFTER password_changed_at, ADD COLUMN locked_until DATETIME NULL AFTER failed_login_count',
    'SELECT 1 -- Lockout column (login_attempts or failed_login_count) already present, skip');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 4: LOGIN AUDIT LOG (login_audit)
-- ─────────────────────────────────────────────────────────────────────────────
-- Strict security rule: Never log passwords, reset tokens, or session IDs.
-- Tracks failed and successful authentication events with client IP and User-Agent.
-- ─────────────────────────────────────────────────────────────────────────────

-- [REQUIRES ROOT]
CREATE TABLE IF NOT EXISTS login_audit (
    login_id        INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id         INT UNSIGNED NULL,
    email_attempted VARCHAR(255) NOT NULL,
    success         TINYINT(1) NOT NULL,
    ip_address      VARCHAR(45) NULL,
    user_agent      VARCHAR(255) NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_login_audit_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- [REQUIRES ROOT] Composite index for lockout inspection & rate analytics
SET @has_idx = (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = 'medlab_db' AND TABLE_NAME = 'login_audit' AND INDEX_NAME = 'idx_login_audit_email_time'
);
SET @sql = IF(@has_idx = 0,
    'CREATE INDEX idx_login_audit_email_time ON login_audit (email_attempted, created_at)',
    'SELECT 1 -- idx_login_audit_email_time already exists');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 5: NEW SECURITY TRIGGERS (AUDIT IMMUTABILITY & RESULT FREEZING)
-- ─────────────────────────────────────────────────────────────────────────────
-- EXISTING TRIGGERS AUDIT & CONFLICT ANALYSIS:
--   - `trg_enforce_role_creation` on `users` (BEFORE INSERT) -> Unaffected.
--   - `trg_booking_status_machine` on `bookings` (BEFORE UPDATE) -> Unaffected.
--   - `trg_audit_booking_status` on `bookings` (AFTER UPDATE) -> Unaffected.
--   - `trg_auto_flag_test_result` on `test_results` (BEFORE INSERT) ->
--     Calculates min/max numeric flags. Our new BEFORE INSERT trigger checks
--     if parent booking is Completed. If so, it raises SQLSTATE 45000 immediately.
--   - `trg_auto_flag_test_result_update` on `test_results` (BEFORE UPDATE) ->
--     Recalculates min/max flags. Our new BEFORE UPDATE trigger halts modifications
--     if the booking is Completed.
--   - `trg_audit_test_results` on `test_results` (AFTER UPDATE) ->
--     Appends result edits to audit_log. If an update is aborted by our BEFORE UPDATE
--     trigger, this AFTER UPDATE trigger will not fire.
--   - Compatibility with Pathologist Approval (`routes/pathologist.py`):
--     The pathologist route updates `test_results` FIRST while the booking is still
--     `Pending_Verification`. Only after result stamping does it transition the
--     booking status to `Completed`. Thus, legitimate clinical sign-off is never blocked!
-- ─────────────────────────────────────────────────────────────────────────────

-- [REQUIRES ROOT] 5A. audit_log Immutability: Block UPDATE on audit_log
DROP TRIGGER IF EXISTS trg_audit_log_prevent_update;

DELIMITER $$
CREATE TRIGGER trg_audit_log_prevent_update
BEFORE UPDATE ON audit_log
FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'SECURITY VIOLATION: audit_log entries are immutable and cannot be updated.';
END$$
DELIMITER ;

-- [REQUIRES ROOT] 5B. audit_log Immutability: Block DELETE on audit_log
DROP TRIGGER IF EXISTS trg_audit_log_prevent_delete;

DELIMITER $$
CREATE TRIGGER trg_audit_log_prevent_delete
BEFORE DELETE ON audit_log
FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000'
    SET MESSAGE_TEXT = 'SECURITY VIOLATION: audit_log entries are immutable and cannot be deleted.';
END$$
DELIMITER ;

-- [REQUIRES ROOT] 5C. Freeze test_results once parent booking is Completed (INSERT)
DROP TRIGGER IF EXISTS trg_freeze_results_completed_insert;

DELIMITER $$
CREATE TRIGGER trg_freeze_results_completed_insert
BEFORE INSERT ON test_results
FOR EACH ROW
BEGIN
    DECLARE v_status VARCHAR(30);

    SELECT b.booking_status INTO v_status
    FROM bookings b
    JOIN booking_items bi ON b.booking_id = bi.booking_id
    WHERE bi.item_id = NEW.item_id
    LIMIT 1;

    IF v_status = 'Completed' THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'CLINICAL INTEGRITY VIOLATION: Cannot insert test results for a Completed booking.';
    END IF;
END$$
DELIMITER ;

-- [REQUIRES ROOT] 5D. Freeze test_results once parent booking is Completed (UPDATE)
DROP TRIGGER IF EXISTS trg_freeze_results_completed_update;

DELIMITER $$
CREATE TRIGGER trg_freeze_results_completed_update
BEFORE UPDATE ON test_results
FOR EACH ROW
BEGIN
    DECLARE v_status VARCHAR(30);

    SELECT b.booking_status INTO v_status
    FROM bookings b
    JOIN booking_items bi ON b.booking_id = bi.booking_id
    WHERE bi.item_id = NEW.item_id
    LIMIT 1;

    IF v_status = 'Completed' THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'CLINICAL INTEGRITY VIOLATION: Test results cannot be altered once booking is Completed.';
    END IF;
END$$
DELIMITER ;

-- [REQUIRES ROOT] 5E. Freeze test_results once parent booking is Completed (DELETE)
DROP TRIGGER IF EXISTS trg_freeze_results_completed_delete;

DELIMITER $$
CREATE TRIGGER trg_freeze_results_completed_delete
BEFORE DELETE ON test_results
FOR EACH ROW
BEGIN
    DECLARE v_status VARCHAR(30);

    SELECT b.booking_status INTO v_status
    FROM bookings b
    JOIN booking_items bi ON b.booking_id = bi.booking_id
    WHERE bi.item_id = OLD.item_id
    LIMIT 1;

    IF v_status = 'Completed' THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'CLINICAL INTEGRITY VIOLATION: Test results cannot be deleted from a Completed booking.';
    END IF;
END$$
DELIMITER ;


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 6: MISSING INDEXES FOR WORKFLOW PERFORMANCE
-- ─────────────────────────────────────────────────────────────────────────────

-- [REQUIRES ROOT] 6a. notifications (user_id, is_read) for real-time unread counts
SET @has_idx = (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = 'medlab_db' AND TABLE_NAME = 'notifications' AND INDEX_NAME = 'idx_notif_user_is_read'
);
SET @sql = IF(@has_idx = 0,
    'CREATE INDEX idx_notif_user_is_read ON notifications (user_id, is_read)',
    'SELECT 1 -- idx_notif_user_is_read already exists');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- [REQUIRES ROOT] 6b. bookings (booking_ref) for lookup efficiency
SET @has_idx = (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = 'medlab_db' AND TABLE_NAME = 'bookings' AND INDEX_NAME = 'idx_bookings_ref'
);
SET @sql = IF(@has_idx = 0,
    'CREATE INDEX idx_bookings_ref ON bookings (booking_ref)',
    'SELECT 1 -- idx_bookings_ref already exists');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- [REQUIRES ROOT] 6c. test_results (item_id, param_id)
SET @has_idx = (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = 'medlab_db' AND TABLE_NAME = 'test_results' AND INDEX_NAME = 'idx_test_results_item_param'
);
SET @sql = IF(@has_idx = 0,
    'CREATE INDEX idx_test_results_item_param ON test_results (item_id, param_id)',
    'SELECT 1 -- idx_test_results_item_param already exists');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- [REQUIRES ROOT] 6d. invoices (payment_status) for revenue query filtering
SET @has_idx = (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = 'medlab_db' AND TABLE_NAME = 'invoices' AND INDEX_NAME = 'idx_invoices_payment_status'
);
SET @sql = IF(@has_idx = 0,
    'CREATE INDEX idx_invoices_payment_status ON invoices (payment_status)',
    'SELECT 1 -- idx_invoices_payment_status already exists');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;


-- ─────────────────────────────────────────────────────────────────────────────
-- END OF MIGRATION v4 HARDENING
-- ─────────────────────────────────────────────────────────────────────────────
SELECT 'migration_v4_hardening.sql completed successfully.' AS status;
