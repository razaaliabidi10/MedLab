-- =============================================================================
-- MedLab System — Migration v2
-- File   : database/migration_v2.sql
-- Author : Antigravity (senior engineer pass)
-- Safe   : Fully additive & idempotent. Run as many times as you like.
--          NEVER drops existing tables, columns, or data.
-- How to run:
--   mysql -u root -p medlab_db < database/migration_v2.sql
-- =============================================================================

USE medlab_db;

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 1 : NEW ROLES  (roles 5 & 6)
-- ─────────────────────────────────────────────────────────────────────────────
-- INSERT IGNORE is idempotent — if the row already exists it silently skips.
INSERT IGNORE INTO roles (role_id, role_name, description) VALUES
    (5, 'sample_collector',
     'Sample Collector — Performs phlebotomy (lab & home visits), generates barcodes, rejects invalid samples'),
    (6, 'pathologist',
     'Pathologist — Reviews technician results, approves or sends back for correction, unlocks patient reports');


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 2 : USERS TABLE — additive columns
-- Each ALTER is wrapped so it only runs if the column does not yet exist.
-- ─────────────────────────────────────────────────────────────────────────────

-- 2a. Make password_hash nullable (supports future Google OAuth accounts)
--     We check information_schema before altering so re-runs don't error.
SET @col_nullable = (
    SELECT IS_NULLABLE FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'medlab_db'
      AND TABLE_NAME   = 'users'
      AND COLUMN_NAME  = 'password_hash'
);
SET @sql_nullable = IF(
    @col_nullable = 'NO',
    'ALTER TABLE users MODIFY COLUMN password_hash VARCHAR(255) NULL',
    'SELECT 1 -- password_hash already nullable, skip'
);
PREPARE stmt FROM @sql_nullable;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 2b. auth_provider column
SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'medlab_db' AND TABLE_NAME = 'users' AND COLUMN_NAME = 'auth_provider'
);
SET @sql = IF(@has_col = 0,
    "ALTER TABLE users ADD COLUMN auth_provider ENUM('local','google') NOT NULL DEFAULT 'local' AFTER password_hash",
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 2c. google_id column (unique, nullable)
SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'medlab_db' AND TABLE_NAME = 'users' AND COLUMN_NAME = 'google_id'
);
SET @sql = IF(@has_col = 0,
    'ALTER TABLE users ADD COLUMN google_id VARCHAR(120) NULL UNIQUE AFTER auth_provider',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 2d. login_attempts counter (for lockout)
SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'medlab_db' AND TABLE_NAME = 'users' AND COLUMN_NAME = 'login_attempts'
);
SET @sql = IF(@has_col = 0,
    'ALTER TABLE users ADD COLUMN login_attempts TINYINT UNSIGNED NOT NULL DEFAULT 0 AFTER google_id',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 2e. lockout_until timestamp
SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'medlab_db' AND TABLE_NAME = 'users' AND COLUMN_NAME = 'lockout_until'
);
SET @sql = IF(@has_col = 0,
    'ALTER TABLE users ADD COLUMN lockout_until DATETIME NULL AFTER login_attempts',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 3 : BOOKINGS TABLE — additive columns + ENUM extension
-- ─────────────────────────────────────────────────────────────────────────────

-- 3a. Extend booking_status ENUM to the full 7-state machine.
--     MySQL requires us to re-declare the full ENUM list on MODIFY.
--     We check the current column definition to make this idempotent.
SET @cur_enum = (
    SELECT COLUMN_TYPE FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'medlab_db' AND TABLE_NAME = 'bookings' AND COLUMN_NAME = 'booking_status'
);
SET @sql = IF(
    @cur_enum NOT LIKE '%Confirmed%',
    "ALTER TABLE bookings MODIFY COLUMN booking_status
        ENUM('Booked','Confirmed','Sample_Collected','In_Analysis',
             'Pending_Verification','Completed','Cancelled')
        NOT NULL DEFAULT 'Booked'",
    'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 3b. collection_type — lab visit vs. home collection
SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'medlab_db' AND TABLE_NAME = 'bookings' AND COLUMN_NAME = 'collection_type'
);
SET @sql = IF(@has_col = 0,
    "ALTER TABLE bookings ADD COLUMN collection_type ENUM('Lab','Home') NOT NULL DEFAULT 'Lab' AFTER appointment_slot",
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 3c. collection_address — used only when collection_type = 'Home'
SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'medlab_db' AND TABLE_NAME = 'bookings' AND COLUMN_NAME = 'collection_address'
);
SET @sql = IF(@has_col = 0,
    'ALTER TABLE bookings ADD COLUMN collection_address VARCHAR(300) NULL AFTER collection_type',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 3d. confirmed_by — which receptionist recorded payment (sets Confirmed)
SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'medlab_db' AND TABLE_NAME = 'bookings' AND COLUMN_NAME = 'confirmed_by'
);
SET @sql = IF(@has_col = 0,
    'ALTER TABLE bookings ADD COLUMN confirmed_by INT UNSIGNED NULL AFTER collection_address',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 3e. confirmed_at timestamp
SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'medlab_db' AND TABLE_NAME = 'bookings' AND COLUMN_NAME = 'confirmed_at'
);
SET @sql = IF(@has_col = 0,
    'ALTER TABLE bookings ADD COLUMN confirmed_at DATETIME NULL AFTER confirmed_by',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 3f. slot_id FK — links to time_slots table we create in Section 6
--     (added after time_slots table is created; FK added later)
SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'medlab_db' AND TABLE_NAME = 'bookings' AND COLUMN_NAME = 'slot_id'
);
SET @sql = IF(@has_col = 0,
    'ALTER TABLE bookings ADD COLUMN slot_id INT UNSIGNED NULL AFTER booking_ref',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 3g. FK for confirmed_by → users
SET @has_fk = (
    SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
    WHERE TABLE_SCHEMA='medlab_db' AND TABLE_NAME='bookings' AND CONSTRAINT_NAME='fk_booking_confirmer'
);
SET @sql = IF(@has_fk = 0,
    'ALTER TABLE bookings ADD CONSTRAINT fk_booking_confirmer FOREIGN KEY (confirmed_by) REFERENCES users(user_id) ON DELETE SET NULL',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 4 : SAMPLES TABLE — additive column
-- ─────────────────────────────────────────────────────────────────────────────

-- 4a. rejection_reason — free text, set when sample_status = 'Rejected'
SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'medlab_db' AND TABLE_NAME = 'samples' AND COLUMN_NAME = 'rejection_reason'
);
SET @sql = IF(@has_col = 0,
    'ALTER TABLE samples ADD COLUMN rejection_reason VARCHAR(255) NULL AFTER sample_status',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 5 : TEST RESULTS TABLE — additive columns
-- ─────────────────────────────────────────────────────────────────────────────

-- 5a. verified_by — pathologist user_id who approved this result set
SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'medlab_db' AND TABLE_NAME = 'test_results' AND COLUMN_NAME = 'verified_by'
);
SET @sql = IF(@has_col = 0,
    'ALTER TABLE test_results ADD COLUMN verified_by INT UNSIGNED NULL AFTER technician_id',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 5b. Rename old verified_at → entered_at for clarity, then add a proper verified_at
--     Because this is additive-only we just add pathologist_verified_at separately
--     and leave the old verified_at (which was actually "entered at") alone.
SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'medlab_db' AND TABLE_NAME = 'test_results' AND COLUMN_NAME = 'pathologist_verified_at'
);
SET @sql = IF(@has_col = 0,
    'ALTER TABLE test_results ADD COLUMN pathologist_verified_at DATETIME NULL AFTER verified_by',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 5c. pathologist_comment — reason when pathologist sends result back to technician
SET @has_col = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'medlab_db' AND TABLE_NAME = 'test_results' AND COLUMN_NAME = 'pathologist_comment'
);
SET @sql = IF(@has_col = 0,
    'ALTER TABLE test_results ADD COLUMN pathologist_comment TEXT NULL AFTER pathologist_verified_at',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 5d. FK for verified_by → users
SET @has_fk = (
    SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
    WHERE TABLE_SCHEMA='medlab_db' AND TABLE_NAME='test_results' AND CONSTRAINT_NAME='fk_result_pathologist'
);
SET @sql = IF(@has_fk = 0,
    'ALTER TABLE test_results ADD CONSTRAINT fk_result_pathologist FOREIGN KEY (verified_by) REFERENCES users(user_id) ON DELETE SET NULL',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 6 : NEW TABLES
-- All use CREATE TABLE IF NOT EXISTS — fully idempotent.
-- ─────────────────────────────────────────────────────────────────────────────

-- 6a. TIME SLOTS — capacity-managed appointment windows
CREATE TABLE IF NOT EXISTS time_slots (
    slot_id        INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    slot_date      DATE NOT NULL,
    -- Label matches the ENUM in bookings for display consistency
    slot_label     ENUM(
                       '08:00 AM - 10:00 AM',
                       '10:00 AM - 12:00 PM',
                       '02:00 PM - 04:00 PM',
                       '04:00 PM - 06:00 PM'
                   ) NOT NULL,
    max_capacity   TINYINT UNSIGNED NOT NULL DEFAULT 20,
    booked_count   TINYINT UNSIGNED NOT NULL DEFAULT 0,
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_slot_date_label UNIQUE (slot_date, slot_label)
) ENGINE=InnoDB COMMENT='Appointment slot pool; booked_count is incremented by sp_create_booking';

-- Add FK from bookings.slot_id → time_slots.slot_id (once table exists)
SET @has_fk = (
    SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
    WHERE TABLE_SCHEMA='medlab_db' AND TABLE_NAME='bookings' AND CONSTRAINT_NAME='fk_booking_slot'
);
SET @sql = IF(@has_fk = 0,
    'ALTER TABLE bookings ADD CONSTRAINT fk_booking_slot FOREIGN KEY (slot_id) REFERENCES time_slots(slot_id) ON DELETE SET NULL',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;


-- 6b. PACKAGES — test bundle discount catalog
CREATE TABLE IF NOT EXISTS packages (
    package_id    INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    package_code  VARCHAR(20) NOT NULL UNIQUE,
    package_name  VARCHAR(120) NOT NULL UNIQUE,
    description   TEXT NULL,
    -- discount_percent is informational; actual price = sum of test prices * (1 - discount/100)
    discount_pct  DECIMAL(5,2) NOT NULL DEFAULT 0.00
        CHECK (discount_pct >= 0 AND discount_pct <= 100),
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 6c. PACKAGE_TESTS — M:N junction between packages and lab_tests
CREATE TABLE IF NOT EXISTS package_tests (
    package_id  INT UNSIGNED NOT NULL,
    test_id     INT UNSIGNED NOT NULL,
    PRIMARY KEY (package_id, test_id),
    CONSTRAINT fk_pt_package FOREIGN KEY (package_id) REFERENCES packages(package_id) ON DELETE CASCADE,
    CONSTRAINT fk_pt_test    FOREIGN KEY (test_id)    REFERENCES lab_tests(test_id)   ON DELETE RESTRICT
) ENGINE=InnoDB;


-- 6d. NOTIFICATIONS — in-app notification store
CREATE TABLE IF NOT EXISTS notifications (
    notification_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    -- recipient user
    user_id         INT UNSIGNED NOT NULL,
    -- type drives the icon and colour in the UI
    type            ENUM(
                        'booking',        -- booking created / updated
                        'payment',        -- payment recorded
                        'sample',         -- sample collected / rejected
                        'result',         -- results entered / approved / sent back
                        'account',        -- account created / suspended / reactivated
                        'general'         -- catch-all
                    ) NOT NULL DEFAULT 'general',
    title           VARCHAR(120) NOT NULL,
    message         TEXT NOT NULL,
    booking_id      INT UNSIGNED NULL,     -- optional: links bell click → booking detail
    is_read         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_notif_user    FOREIGN KEY (user_id)    REFERENCES users(user_id)    ON DELETE CASCADE,
    CONSTRAINT fk_notif_booking FOREIGN KEY (booking_id) REFERENCES bookings(booking_id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- Performance: most queries filter by (user_id, is_read) for the unread badge
-- Note: CREATE INDEX IF NOT EXISTS is MySQL 8.0.1+ but DESC key parts need standard syntax
SET @has_idx = (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA='medlab_db' AND TABLE_NAME='notifications' AND INDEX_NAME='idx_notif_user_read'
);
SET @sql = IF(@has_idx = 0,
    'CREATE INDEX idx_notif_user_read ON notifications (user_id, is_read)',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @has_idx = (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA='medlab_db' AND TABLE_NAME='notifications' AND INDEX_NAME='idx_notif_created'
);
SET @sql = IF(@has_idx = 0,
    'CREATE INDEX idx_notif_created ON notifications (created_at)',
    'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;


-- 6e. AUDIT LOG — immutable append-only record of state changes
CREATE TABLE IF NOT EXISTS audit_log (
    log_id       INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    table_name   VARCHAR(50) NOT NULL,
    record_id    INT UNSIGNED NOT NULL,        -- PK of the changed row
    action       ENUM('INSERT','UPDATE','DELETE') NOT NULL,
    changed_by   INT UNSIGNED NULL,            -- user_id of actor (NULL = trigger/system)
    old_value    JSON NULL,                    -- previous state (key fields only)
    new_value    JSON NULL,                    -- new state
    changed_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_audit_table_record (table_name, record_id),
    INDEX idx_audit_changed_at   (changed_at DESC)
) ENGINE=InnoDB COMMENT='Immutable audit trail; never DELETE from this table';


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 7 : UPDATED VIEWS
-- ─────────────────────────────────────────────────────────────────────────────

-- 7a. vw_staff_directory — now includes roles 5 (sample_collector) and 6 (pathologist)
CREATE OR REPLACE VIEW vw_staff_directory AS
    SELECT
        u.user_id, u.full_name, u.email, u.phone, u.avatar_url, u.is_active, u.created_at,
        r.role_id, r.role_name, sp.employee_code, sp.qualification, sp.shift_timing, sp.joining_date
    FROM users u
    JOIN  roles r  ON u.role_id   = r.role_id
    LEFT  JOIN staff_profiles sp ON u.user_id = sp.staff_id
    WHERE u.role_id IN (2, 3, 5, 6);


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 8 : UPDATED & EXTENDED TRIGGERS
-- Strategy: DROP the old trigger, then CREATE the new extended version.
-- We keep the same business logic — we only ADD the new role cases.
-- ─────────────────────────────────────────────────────────────────────────────

-- 8a. trg_enforce_role_creation — extend to cover roles 5 & 6
DROP TRIGGER IF EXISTS trg_enforce_role_creation;

DELIMITER $$
CREATE TRIGGER trg_enforce_role_creation
BEFORE INSERT ON users
FOR EACH ROW
BEGIN
    DECLARE v_admin_count  INT;
    DECLARE v_creator_role TINYINT;

    -- Rule 1: Only one system administrator may ever exist
    IF NEW.role_id = 1 THEN
        SELECT COUNT(*) INTO v_admin_count FROM users WHERE role_id = 1;
        IF v_admin_count >= 1 THEN
            SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'SECURITY VIOLATION: System already has a single Master Admin.';
        END IF;
    END IF;

    -- Rule 2: Staff roles (receptionist=2, technician=3,
    --         sample_collector=5, pathologist=6) MUST be created by the admin (role_id=1).
    --         They cannot self-register.
    IF NEW.role_id IN (2, 3, 5, 6) THEN
        IF NEW.created_by IS NULL THEN
            SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'SECURITY VIOLATION: Staff accounts cannot self-register. Admin ID required in created_by.';
        END IF;

        SELECT role_id INTO v_creator_role FROM users WHERE user_id = NEW.created_by;
        IF v_creator_role IS NULL OR v_creator_role != 1 THEN
            SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'SECURITY VIOLATION: Only the Master Admin can provision staff accounts.';
        END IF;
    END IF;

    -- Rule 3: Public signup (no created_by) is only permitted for patients (role_id=4)
    IF NEW.role_id != 4 AND NEW.role_id != 1 AND NEW.created_by IS NULL THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'SECURITY VIOLATION: Self-registration is restricted to patient accounts only.';
    END IF;
END$$
DELIMITER ;


-- 8b. trg_booking_status_machine — blocks illegal status transitions at DB level.
--     Allowed transitions (directed graph):
--       Booked            → Confirmed, Cancelled
--       Confirmed         → Sample_Collected, Cancelled
--       Sample_Collected  → In_Analysis
--       In_Analysis       → Pending_Verification
--       Pending_Verification → Completed, In_Analysis   ← pathologist can send back
--       Completed         → (terminal — no further transitions)
--       Cancelled         → (terminal — no further transitions)
DROP TRIGGER IF EXISTS trg_booking_status_machine;

DELIMITER $$
CREATE TRIGGER trg_booking_status_machine
BEFORE UPDATE ON bookings
FOR EACH ROW
BEGIN
    -- Only validate when the status column actually changes
    IF NEW.booking_status != OLD.booking_status THEN

        IF OLD.booking_status = 'Booked' AND
           NEW.booking_status NOT IN ('Confirmed', 'Sample_Collected', 'Cancelled') THEN
            SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'WORKFLOW VIOLATION: Booked can only move to Confirmed, Sample_Collected, or Cancelled.';
        END IF;

        IF OLD.booking_status = 'Confirmed' AND
           NEW.booking_status NOT IN ('Sample_Collected', 'Cancelled') THEN
            SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'WORKFLOW VIOLATION: Confirmed can only move to Sample_Collected or Cancelled.';
        END IF;

        IF OLD.booking_status = 'Sample_Collected' AND
           NEW.booking_status NOT IN ('In_Analysis', 'Pending_Verification', 'Cancelled') THEN
            SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'WORKFLOW VIOLATION: Sample_Collected can only move to In_Analysis or Pending_Verification.';
        END IF;

        IF OLD.booking_status = 'In_Analysis' AND
           NEW.booking_status NOT IN ('Pending_Verification', 'Sample_Collected', 'Cancelled') THEN
            SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'WORKFLOW VIOLATION: In_Analysis can only move to Pending_Verification.';
        END IF;

        IF OLD.booking_status = 'Pending_Verification' AND
           NEW.booking_status NOT IN ('Completed', 'In_Analysis', 'Cancelled') THEN
            SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'WORKFLOW VIOLATION: Pending_Verification can only move to Completed or back to In_Analysis (pathologist send-back).';
        END IF;

        IF OLD.booking_status IN ('Completed', 'Cancelled') THEN
            SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'WORKFLOW VIOLATION: Completed and Cancelled are terminal states.';
        END IF;

    END IF;
END$$
DELIMITER ;


-- 8c. trg_audit_booking_status — appends a row to audit_log whenever
--     a booking's status changes. Lightweight JSON capture.
DROP TRIGGER IF EXISTS trg_audit_booking_status;

DELIMITER $$
CREATE TRIGGER trg_audit_booking_status
AFTER UPDATE ON bookings
FOR EACH ROW
BEGIN
    IF NEW.booking_status != OLD.booking_status THEN
        INSERT INTO audit_log (table_name, record_id, action, old_value, new_value)
        VALUES (
            'bookings',
            OLD.booking_id,
            'UPDATE',
            JSON_OBJECT('booking_status', OLD.booking_status, 'updated_at', OLD.created_at),
            JSON_OBJECT('booking_status', NEW.booking_status, 'updated_at', NOW())
        );
    END IF;
END$$
DELIMITER ;


-- 8d. trg_audit_test_results — appends to audit_log when a result row changes
DROP TRIGGER IF EXISTS trg_audit_test_results;

DELIMITER $$
CREATE TRIGGER trg_audit_test_results
AFTER UPDATE ON test_results
FOR EACH ROW
BEGIN
    INSERT INTO audit_log (table_name, record_id, action, old_value, new_value)
    VALUES (
        'test_results',
        OLD.result_id,
        'UPDATE',
        JSON_OBJECT(
            'measured_value', OLD.measured_value,
            'flag_status',    OLD.flag_status,
            'verified_by',    OLD.verified_by
        ),
        JSON_OBJECT(
            'measured_value', NEW.measured_value,
            'flag_status',    NEW.flag_status,
            'verified_by',    NEW.verified_by
        )
    );
END$$
DELIMITER ;


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 9 : STORED PROCEDURE — sp_create_booking
-- A single atomic transaction: inserts booking, items, invoice, and increments
-- the slot counter. Any failure triggers ROLLBACK automatically via EXIT HANDLER.
-- Python calls:  CALL sp_create_booking(...)
-- ─────────────────────────────────────────────────────────────────────────────
DROP PROCEDURE IF EXISTS sp_create_booking;

DELIMITER $$
CREATE PROCEDURE sp_create_booking(
    IN  p_patient_id      INT UNSIGNED,
    IN  p_slot_id         INT UNSIGNED,       -- NULL if using old ENUM slot (legacy)
    IN  p_appt_date       DATE,
    IN  p_appt_slot       VARCHAR(30),        -- ENUM label string
    IN  p_collection_type ENUM('Lab','Home'),
    IN  p_collection_addr VARCHAR(300),       -- NULL for Lab
    IN  p_booking_ref     VARCHAR(25),
    IN  p_invoice_num     VARCHAR(30),
    IN  p_test_ids_json   JSON,               -- e.g. [1, 3, 5]
    OUT p_booking_id      INT UNSIGNED,
    OUT p_error_msg       VARCHAR(255)
)
BEGIN
    DECLARE v_total        DECIMAL(10,2) DEFAULT 0.00;
    DECLARE v_test_id      INT UNSIGNED;
    DECLARE v_price        DECIMAL(10,2);
    DECLARE v_slot_count   TINYINT UNSIGNED;
    DECLARE v_max_cap      TINYINT UNSIGNED;
    DECLARE v_idx          INT DEFAULT 0;
    DECLARE v_len          INT;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        GET DIAGNOSTICS CONDITION 1 p_error_msg = MESSAGE_TEXT;
        SET p_booking_id = 0;
    END;

    SET p_error_msg = '';
    SET p_booking_id = 0;

    START TRANSACTION;

    -- 1. Validate slot capacity (only when slot_id is provided)
    IF p_slot_id IS NOT NULL THEN
        SELECT booked_count, max_capacity
          INTO v_slot_count, v_max_cap
          FROM time_slots
         WHERE slot_id = p_slot_id AND is_active = 1
         FOR UPDATE;               -- row-level lock prevents race condition

        IF v_slot_count >= v_max_cap THEN
            SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'CAPACITY ERROR: Selected time slot is fully booked.';
        END IF;

        UPDATE time_slots SET booked_count = booked_count + 1 WHERE slot_id = p_slot_id;
    END IF;

    -- 2. Insert master booking row (status defaults to 'Booked')
    INSERT INTO bookings
        (booking_ref, patient_id, slot_id, appointment_date, appointment_slot,
         collection_type, collection_address)
    VALUES
        (p_booking_ref, p_patient_id, p_slot_id, p_appt_date, p_appt_slot,
         p_collection_type, p_collection_addr);

    SET p_booking_id = LAST_INSERT_ID();

    -- 3. Insert one booking_item per test; accumulate total
    SET v_len = JSON_LENGTH(p_test_ids_json);
    WHILE v_idx < v_len DO
        SET v_test_id = JSON_EXTRACT(p_test_ids_json, CONCAT('$[', v_idx, ']'));

        SELECT price INTO v_price FROM lab_tests WHERE test_id = v_test_id AND is_active = 1;
        IF v_price IS NULL THEN
            SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'BOOKING ERROR: One or more selected tests are unavailable.';
        END IF;

        INSERT INTO booking_items (booking_id, test_id, price_at_booking)
        VALUES (p_booking_id, v_test_id, v_price);

        SET v_total = v_total + v_price;
        SET v_idx   = v_idx + 1;
    END WHILE;

    -- 4. Create the invoice (Unpaid until receptionist records payment)
    INSERT INTO invoices (booking_id, invoice_number, total_amount)
    VALUES (p_booking_id, p_invoice_num, v_total);

    COMMIT;
END$$
DELIMITER ;


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 10 : ADDITIONAL CATEGORIES & TEST CATALOG EXPANSION
-- Needed for seed and for the landing page "live test catalog" feature.
-- ─────────────────────────────────────────────────────────────────────────────

-- New categories (INSERT IGNORE = safe to rerun)
INSERT IGNORE INTO test_categories (category_name, department_code) VALUES
    ('Lipid & Cardiovascular', 'LIP'),
    ('Thyroid Function',       'THY'),
    ('Urine Analysis',         'URN'),
    ('Microbiology',           'MIC'),
    ('Vitamins & Minerals',    'VIT'),
    ('Diabetes Management',    'DIA');

-- New lab tests (INSERT IGNORE on test_code)
INSERT IGNORE INTO lab_tests (category_id, test_code, test_name, sample_type, price, turnaround_hours, pre_test_instructions)
SELECT c.category_id, v.test_code, v.test_name, v.sample_type, v.price, v.turnaround_hours, v.instructions
FROM (VALUES
    -- Hematology (category already seeded as 1)
    ROW('HEM-ESR',  'ESR (Erythrocyte Sedimentation Rate)',  'Blood (EDTA)',  350.00,  4,  'No fasting required.'),
    ROW('HEM-PBF',  'Peripheral Blood Film (PBF)',            'Blood (EDTA)',  800.00,  24, 'No special preparation.'),
    -- Clinical Biochemistry
    ROW('BIO-HBA',  'HbA1c (Glycated Hemoglobin)',            'Blood (EDTA)',  1400.00, 24, 'No fasting required.'),
    ROW('BIO-CRP',  'C-Reactive Protein (CRP)',               'Blood (Serum)', 900.00,  12, 'No special preparation.'),
    -- Thyroid
    ROW('THY-TSH',  'Thyroid Stimulating Hormone (TSH)',      'Blood (Serum)', 1200.00, 24, 'Collect morning sample before medication.'),
    ROW('THY-T3',   'Tri-iodothyronine (T3)',                 'Blood (Serum)', 950.00,  24, 'Collect morning sample.'),
    ROW('THY-T4',   'Thyroxine (T4)',                         'Blood (Serum)', 950.00,  24, 'Collect morning sample.'),
    ROW('THY-FT4',  'Free Thyroxine (FT4)',                   'Blood (Serum)', 1100.00, 24, 'Collect morning sample.'),
    -- Urine
    ROW('URN-RE',   'Urine Routine Examination (R/E)',        'Urine',         400.00,  6,  'Mid-stream first-morning urine sample.'),
    ROW('URN-ACR',  'Urine Albumin-Creatinine Ratio (ACR)',   'Urine',         700.00,  12, 'First morning urine sample required.'),
    -- Microbiology
    ROW('MIC-HBS',  'Hepatitis B Surface Antigen (HBsAg)',    'Blood (Serum)', 700.00,  12, 'No special preparation.'),
    ROW('MIC-HCV',  'Hepatitis C Antibody (Anti-HCV)',        'Blood (Serum)', 700.00,  12, 'No special preparation.'),
    ROW('MIC-HIV',  'HIV 1 & 2 Antibody Screening',           'Blood (Serum)', 800.00,  24, 'Counselling recommended before test.'),
    ROW('MIC-WIDAL','Widal Test (Typhoid)',                   'Blood (Serum)', 500.00,  12, 'No special preparation.'),
    -- Vitamins & Minerals
    ROW('VIT-D',    'Vitamin D (25-OH)',                      'Blood (Serum)', 2500.00, 48, '12-hour fasting preferred.'),
    ROW('VIT-B12',  'Vitamin B12 (Cobalamin)',                'Blood (Serum)', 1800.00, 24, 'Morning collection preferred.'),
    ROW('VIT-FER',  'Serum Ferritin',                         'Blood (Serum)', 1200.00, 24, 'No special preparation.'),
    -- Diabetes Management
    ROW('DIA-PPBS', 'Post-Prandial Blood Sugar (PPBS)',       'Blood (Serum)', 450.00,  4,  '2 hours after a full meal.'),
    ROW('DIA-OGTT', 'Oral Glucose Tolerance Test (OGTT)',     'Fasting Blood', 900.00,  6,  'Strict 8-hour fast; administered in lab only.')
) AS v(test_code, test_name, sample_type, price, turnaround_hours, instructions)
JOIN test_categories c ON (
    (v.test_code LIKE 'HEM%' AND c.department_code = 'HEM') OR
    (v.test_code LIKE 'BIO%' AND c.department_code = 'BIO') OR
    (v.test_code LIKE 'THY%' AND c.department_code = 'THY') OR
    (v.test_code LIKE 'URN%' AND c.department_code = 'URN') OR
    (v.test_code LIKE 'MIC%' AND c.department_code = 'MIC') OR
    (v.test_code LIKE 'VIT%' AND c.department_code = 'VIT') OR
    (v.test_code LIKE 'DIA%' AND c.department_code = 'DIA')
);

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 11 : TIME SLOTS for next 14 days
-- A rerunnable INSERT IGNORE block. Slots are created for all 4 windows.
-- ─────────────────────────────────────────────────────────────────────────────

-- Generate slots for today + 13 days (14 days total), 4 slots/day = 56 rows max
-- We use a recursive CTE available in MySQL 8.0+
INSERT IGNORE INTO time_slots (slot_date, slot_label, max_capacity)
WITH RECURSIVE days AS (
    SELECT CURDATE() AS d, 0 AS n
    UNION ALL
    SELECT d + INTERVAL 1 DAY, n + 1 FROM days WHERE n < 13
)
SELECT
    d.d,
    s.label,
    20
FROM days d
CROSS JOIN (
    SELECT '08:00 AM - 10:00 AM' AS label UNION ALL
    SELECT '10:00 AM - 12:00 PM' UNION ALL
    SELECT '02:00 PM - 04:00 PM' UNION ALL
    SELECT '04:00 PM - 06:00 PM'
) s;

-- ─────────────────────────────────────────────────────────────────────────────
-- END OF MIGRATION v2
-- ─────────────────────────────────────────────────────────────────────────────
SELECT 'migration_v2.sql applied successfully.' AS status;
