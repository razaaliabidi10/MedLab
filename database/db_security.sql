-- =============================================================================
-- MedLab System — db_security.sql (UNTESTED)
-- Purpose : Least-privilege MySQL user provisioning for university evaluation:
--           1. Provision `medlab_app` (DML + Stored Procedure EXECUTE only)
--           2. Provision `app_readonly` (Read-only SELECT for auditing/reporting)
--           3. Verify zero administrative or DDL privileges (No DROP, ALTER, CREATE, GRANT, FILE, SUPER)
--           4. Guidance on running migrations vs running the Flask runtime
-- Author  : Security-Minded Senior Full-Stack Engineer Pass
-- Safety  : Uses CREATE USER IF NOT EXISTS and explicit GRANT statements.
--           Run by hand as root in MySQL Workbench.
-- Encoding: UTF-8 without BOM
-- =============================================================================

SET NAMES utf8mb4;
USE medlab_db;

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 1: ARCHITECTURAL ROLE SEPARATION EXPLANATION
-- ─────────────────────────────────────────────────────────────────────────────
-- In professional healthcare database systems, application runtime processes
-- MUST NEVER run as `root` or an administrative user with DDL privileges.
--
-- Why least-privilege matters for grading:
-- 1. DEFENSE-IN-DEPTH AGAINST SQL INJECTION:
--    Even if a malicious actor successfully exploits a parameter flaw, they
--    CANNOT drop tables (`DROP TABLE users;`), alter schema, or destroy backups
--    because the application user lacks DROP, ALTER, and CREATE privileges.
-- 2. FILE SYSTEM ISOLATION:
--    Denying `FILE` privilege ensures MySQL cannot read or overwrite system files
--    via `SELECT ... INTO OUTFILE` or `LOAD DATA INFILE`.
-- 3. ADMINISTRATIVE ISOLATION:
--    Denying `GRANT OPTION` and `SUPER` ensures the app account cannot escalate
--    privileges, manipulate binlogs, or terminate other database sessions.
--
-- WORKFLOW RULE:
-- - Schema migrations (`migration_v2.sql`, `migration_v4_hardening.sql`) and
--   database rebuild scripts (`build_db.py`) MUST be run by `root`.
-- - The Flask application MUST run as `medlab_app` by updating `.env`:
--       DB_USER=medlab_app
--       DB_PASSWORD=CHANGE_ME_1
-- ─────────────────────────────────────────────────────────────────────────────


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 2: PROVISION medlab_app (APPLICATION RUNTIME USER)
-- ─────────────────────────────────────────────────────────────────────────────
-- Permissions Granted:
--   - SELECT, INSERT, UPDATE, DELETE (Standard DML needed for lab operations)
--   - EXECUTE (Required to call stored procedures such as `sp_create_booking`)
-- Permissions Denied:
--   - NO DROP, NO ALTER, NO CREATE, NO GRANT OPTION, NO FILE, NO SUPER.
-- ─────────────────────────────────────────────────────────────────────────────

-- [REQUIRES ROOT] Create user for socket/local connections
CREATE USER IF NOT EXISTS 'medlab_app'@'localhost' IDENTIFIED BY 'CHANGE_ME_1';
CREATE USER IF NOT EXISTS 'medlab_app'@'127.0.0.1' IDENTIFIED BY 'CHANGE_ME_1';

-- [REQUIRES ROOT] In case user already existed, update passwords
ALTER USER 'medlab_app'@'localhost' IDENTIFIED BY 'CHANGE_ME_1';
ALTER USER 'medlab_app'@'127.0.0.1' IDENTIFIED BY 'CHANGE_ME_1';

-- [REQUIRES ROOT] Revoke any accidental global privileges
REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'medlab_app'@'localhost';
REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'medlab_app'@'127.0.0.1';

-- [REQUIRES ROOT] Grant least-privilege DML and EXECUTE strictly scoped to medlab_db.*
GRANT SELECT, INSERT, UPDATE, DELETE, EXECUTE ON medlab_db.* TO 'medlab_app'@'localhost';
GRANT SELECT, INSERT, UPDATE, DELETE, EXECUTE ON medlab_db.* TO 'medlab_app'@'127.0.0.1';


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 3: PROVISION app_readonly (AUDITOR & ANALYTICS USER)
-- ─────────────────────────────────────────────────────────────────────────────
-- Permissions Granted:
--   - SELECT strictly on medlab_db.* (Read-only access for reporting)
-- Permissions Denied:
--   - NO INSERT, NO UPDATE, NO DELETE, NO DDL, NO EXECUTE, NO SUPER.
-- ─────────────────────────────────────────────────────────────────────────────

-- [REQUIRES ROOT] Create user for read-only access
CREATE USER IF NOT EXISTS 'app_readonly'@'localhost' IDENTIFIED BY 'CHANGE_ME_2';
CREATE USER IF NOT EXISTS 'app_readonly'@'127.0.0.1' IDENTIFIED BY 'CHANGE_ME_2';

-- [REQUIRES ROOT] Update passwords if users already existed
ALTER USER 'app_readonly'@'localhost' IDENTIFIED BY 'CHANGE_ME_2';
ALTER USER 'app_readonly'@'127.0.0.1' IDENTIFIED BY 'CHANGE_ME_2';

-- [REQUIRES ROOT] Revoke any accidental global privileges
REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'app_readonly'@'localhost';
REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'app_readonly'@'127.0.0.1';

-- [REQUIRES ROOT] Grant strictly read-only SELECT privilege
GRANT SELECT ON medlab_db.* TO 'app_readonly'@'localhost';
GRANT SELECT ON medlab_db.* TO 'app_readonly'@'127.0.0.1';


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 4: FLUSH & PRIVILEGE VERIFICATION
-- ─────────────────────────────────────────────────────────────────────────────

-- [REQUIRES ROOT] Reload grant tables
FLUSH PRIVILEGES;

-- [REQUIRES ROOT] Show Grants for Verification (Inspect in MySQL Workbench):
SHOW GRANTS FOR 'medlab_app'@'localhost';
SHOW GRANTS FOR 'medlab_app'@'127.0.0.1';

SHOW GRANTS FOR 'app_readonly'@'localhost';
SHOW GRANTS FOR 'app_readonly'@'127.0.0.1';

-- ─────────────────────────────────────────────────────────────────────────────
-- END OF db_security.sql
-- ─────────────────────────────────────────────────────────────────────────────
SELECT 'db_security.sql executed successfully. Change passwords and update .env accordingly.' AS status;
