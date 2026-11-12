-- =============================================================================
-- MedLab System — Migration v3: Supabase Authentication
-- File   : database/migration_v3_supabase.sql
-- Safe   : Fully additive and idempotent. Run as many times as you like.
--          NEVER drops existing tables, columns, or data.
-- How to run:
--   mysql -u root -p medlab_db < database/migration_v3_supabase.sql
-- =============================================================================

USE medlab_db;

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 1 : Add email_verified (Default 1 for all existing and seeded accounts)
-- ─────────────────────────────────────────────────────────────────────────────
SET @has_email_verified = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'email_verified'
);

SET @sql_email_verified = IF(
    @has_email_verified = 0,
    "ALTER TABLE users ADD COLUMN email_verified TINYINT(1) NOT NULL DEFAULT 1 AFTER password_hash",
    "SELECT 1 -- email_verified already exists"
);
PREPARE stmt FROM @sql_email_verified;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 2 : Add supabase_uid (Unique UUID from Supabase)
-- ─────────────────────────────────────────────────────────────────────────────
SET @has_supabase_uid = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'supabase_uid'
);

SET @sql_supabase_uid = IF(
    @has_supabase_uid = 0,
    "ALTER TABLE users ADD COLUMN supabase_uid CHAR(36) NULL UNIQUE AFTER email_verified",
    "SELECT 1 -- supabase_uid already exists"
);
PREPARE stmt FROM @sql_supabase_uid;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 3 : Ensure auth_provider is ENUM('local','google')
-- ─────────────────────────────────────────────────────────────────────────────
SET @has_auth_provider = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'auth_provider'
);

SET @sql_auth_provider = IF(
    @has_auth_provider = 0,
    "ALTER TABLE users ADD COLUMN auth_provider ENUM('local','google') NOT NULL DEFAULT 'local' AFTER supabase_uid",
    "SELECT 1 -- auth_provider already exists"
);
PREPARE stmt FROM @sql_auth_provider;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 4 : Ensure password_hash is NULLABLE (for OAuth users)
-- ─────────────────────────────────────────────────────────────────────────────
SET @is_pwd_nullable = (
    SELECT IS_NULLABLE FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'password_hash'
);

SET @sql_pwd_null = IF(
    @is_pwd_nullable = 'NO',
    "ALTER TABLE users MODIFY COLUMN password_hash VARCHAR(255) NULL",
    "SELECT 1 -- password_hash is already nullable"
);
PREPARE stmt FROM @sql_pwd_null;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 5 : Index on supabase_uid for fast lookup during OAuth verification
-- ─────────────────────────────────────────────────────────────────────────────
SET @has_idx_supabase = (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND INDEX_NAME = 'idx_users_supabase_uid'
);

SET @sql_idx_supabase = IF(
    @has_idx_supabase = 0,
    "CREATE INDEX idx_users_supabase_uid ON users(supabase_uid)",
    "SELECT 1 -- index already exists"
);
PREPARE stmt FROM @sql_idx_supabase;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SELECT 'migration_v3_supabase.sql applied successfully.' AS status;
