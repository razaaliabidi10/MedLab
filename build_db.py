import os
import sys
# pyrefly: ignore[missing-import]
import mysql.connector
# pyrefly: ignore[missing-import]
from werkzeug.security import generate_password_hash

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ============================================================================
# DATABASE CONFIGURATION READ FROM ENVIRONMENT / .ENV
# Never hardcode sensitive root or database passwords in source control.
# ============================================================================
DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("DB_PORT", 3306))
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "medlab_db")

DDL_STATEMENTS = [
    f"DROP DATABASE IF EXISTS {DB_NAME}",
    (
        f"CREATE DATABASE {DB_NAME} CHARACTER SET utf8mb4 COLLATE"
        " utf8mb4_unicode_ci"
    ),
    f"USE {DB_NAME}",
    # 1. ROLES (Lookup table - 3NF)
    """
    CREATE TABLE roles (
        role_id TINYINT UNSIGNED PRIMARY KEY,
        role_name VARCHAR(30) NOT NULL UNIQUE,
        description VARCHAR(255) NOT NULL
    ) ENGINE=InnoDB
    """,
    # 2. USERS (Unified authentication table - Email & Phone are UNIQUE and locked in profile)
    """
    CREATE TABLE users (
        user_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        role_id TINYINT UNSIGNED NOT NULL,
        full_name VARCHAR(100) NOT NULL,
        email VARCHAR(120) NOT NULL UNIQUE,
        phone VARCHAR(20) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        avatar_url VARCHAR(255) NOT NULL DEFAULT 'default_avatar.png',
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_by INT UNSIGNED NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT fk_users_role FOREIGN KEY (role_id) REFERENCES roles(role_id) ON UPDATE CASCADE ON DELETE RESTRICT,
        CONSTRAINT fk_users_creator FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE SET NULL
    ) ENGINE=InnoDB
    """,
    # 3. PATIENT PROFILES (1:1 Extension of users for clinical details)
    """
    CREATE TABLE patient_profiles (
        patient_id INT UNSIGNED PRIMARY KEY,
        date_of_birth DATE NULL,
        gender ENUM('Male', 'Female', 'Other') NULL,
        blood_group ENUM('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-') NULL,
        address VARCHAR(255) NULL,
        medical_notes TEXT NULL,
        CONSTRAINT fk_patient_user FOREIGN KEY (patient_id) REFERENCES users(user_id) ON DELETE CASCADE
    ) ENGINE=InnoDB
    """,
    # 4. STAFF PROFILES (1:1 Extension of users for Receptionist & Lab Technician)
    """
    CREATE TABLE staff_profiles (
        staff_id INT UNSIGNED PRIMARY KEY,
        employee_code VARCHAR(20) NOT NULL UNIQUE,
        qualification VARCHAR(120) NOT NULL,
        shift_timing ENUM('Morning', 'Evening', 'Night') NOT NULL DEFAULT 'Morning',
        joining_date DATE NOT NULL,
        CONSTRAINT fk_staff_user FOREIGN KEY (staff_id) REFERENCES users(user_id) ON DELETE CASCADE
    ) ENGINE=InnoDB
    """,
    # 5. TEST CATEGORIES
    """
    CREATE TABLE test_categories (
        category_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        category_name VARCHAR(80) NOT NULL UNIQUE,
        department_code VARCHAR(10) NOT NULL UNIQUE,
        is_active BOOLEAN NOT NULL DEFAULT TRUE
    ) ENGINE=InnoDB
    """,
    # 6. LAB TESTS (Master catalog)
    """
    CREATE TABLE lab_tests (
        test_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        category_id INT UNSIGNED NOT NULL,
        test_code VARCHAR(20) NOT NULL UNIQUE,
        test_name VARCHAR(120) NOT NULL UNIQUE,
        sample_type ENUM('Blood (EDTA)', 'Blood (Serum)', 'Fasting Blood', 'Urine', 'Swab') NOT NULL,
        price DECIMAL(10, 2) NOT NULL CHECK (price >= 0),
        turnaround_hours INT UNSIGNED NOT NULL DEFAULT 24,
        pre_test_instructions VARCHAR(255) DEFAULT 'No special preparation required.',
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        CONSTRAINT fk_test_category FOREIGN KEY (category_id) REFERENCES test_categories(category_id) ON DELETE RESTRICT
    ) ENGINE=InnoDB
    """,
    # 7. TEST PARAMETERS (Atomic biomarkers for 1NF/3NF compliance)
    """
    CREATE TABLE test_parameters (
        param_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        test_id INT UNSIGNED NOT NULL,
        param_name VARCHAR(100) NOT NULL,
        unit VARCHAR(30) NOT NULL,
        min_range DECIMAL(10, 2) NOT NULL,
        max_range DECIMAL(10, 2) NOT NULL,
        display_order TINYINT UNSIGNED DEFAULT 1,
        CONSTRAINT fk_param_test FOREIGN KEY (test_id) REFERENCES lab_tests(test_id) ON DELETE CASCADE,
        CONSTRAINT chk_valid_range CHECK (max_range >= min_range)
    ) ENGINE=InnoDB
    """,
    # 8. BOOKINGS (Master appointment record)
    """
    CREATE TABLE bookings (
        booking_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        booking_ref VARCHAR(25) NOT NULL UNIQUE,
        patient_id INT UNSIGNED NOT NULL,
        appointment_date DATE NOT NULL,
        appointment_slot ENUM('08:00 AM - 10:00 AM', '10:00 AM - 12:00 PM', '02:00 PM - 04:00 PM', '04:00 PM - 06:00 PM') NOT NULL,
        booking_status ENUM('Booked', 'Sample_Collected', 'In_Analysis', 'Completed', 'Cancelled') NOT NULL DEFAULT 'Booked',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_booking_patient FOREIGN KEY (patient_id) REFERENCES users(user_id) ON DELETE RESTRICT
    ) ENGINE=InnoDB
    """,
    # 9. BOOKING ITEMS (M:N Junction table between bookings and lab_tests)
    """
    CREATE TABLE booking_items (
        item_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        booking_id INT UNSIGNED NOT NULL,
        test_id INT UNSIGNED NOT NULL,
        price_at_booking DECIMAL(10, 2) NOT NULL,
        item_status ENUM('Pending_Sample', 'Sample_Collected', 'Report_Ready') NOT NULL DEFAULT 'Pending_Sample',
        CONSTRAINT fk_item_booking FOREIGN KEY (booking_id) REFERENCES bookings(booking_id) ON DELETE CASCADE,
        CONSTRAINT fk_item_test FOREIGN KEY (test_id) REFERENCES lab_tests(test_id) ON DELETE RESTRICT,
        CONSTRAINT uq_booking_test UNIQUE (booking_id, test_id)
    ) ENGINE=InnoDB
    """,
    # 10. SAMPLES (Phlebotomy tube & barcode tracking)
    """
    CREATE TABLE samples (
        sample_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        item_id INT UNSIGNED NOT NULL UNIQUE,
        barcode_string VARCHAR(40) NOT NULL UNIQUE,
        collected_by INT UNSIGNED NOT NULL,
        collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        sample_status ENUM('Collected', 'Analyzed', 'Rejected') NOT NULL DEFAULT 'Collected',
        CONSTRAINT fk_sample_item FOREIGN KEY (item_id) REFERENCES booking_items(item_id) ON DELETE CASCADE,
        CONSTRAINT fk_sample_collector FOREIGN KEY (collected_by) REFERENCES users(user_id) ON DELETE RESTRICT
    ) ENGINE=InnoDB
    """,
    # 11. TEST RESULTS (Individual parameter readings entered by Lab Technician)
    """
    CREATE TABLE test_results (
        result_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        item_id INT UNSIGNED NOT NULL,
        param_id INT UNSIGNED NOT NULL,
        measured_value DECIMAL(10, 2) NOT NULL,
        flag_status ENUM('LOW', 'NORMAL', 'HIGH') NOT NULL DEFAULT 'NORMAL',
        is_abnormal BOOLEAN NOT NULL DEFAULT FALSE,
        technician_id INT UNSIGNED NOT NULL,
        verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_result_item FOREIGN KEY (item_id) REFERENCES booking_items(item_id) ON DELETE CASCADE,
        CONSTRAINT fk_result_param FOREIGN KEY (param_id) REFERENCES test_parameters(param_id) ON DELETE RESTRICT,
        CONSTRAINT fk_result_tech FOREIGN KEY (technician_id) REFERENCES users(user_id) ON DELETE RESTRICT,
        CONSTRAINT uq_item_param UNIQUE (item_id, param_id)
    ) ENGINE=InnoDB
    """,
    # 12. INVOICES (1:1 Financial record per booking)
    """
    CREATE TABLE invoices (
        invoice_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        booking_id INT UNSIGNED NOT NULL UNIQUE,
        invoice_number VARCHAR(30) NOT NULL UNIQUE,
        total_amount DECIMAL(10, 2) NOT NULL CHECK (total_amount >= 0),
        payment_status ENUM('Unpaid', 'Paid', 'Refunded') NOT NULL DEFAULT 'Unpaid',
        payment_method ENUM('Cash_At_Counter', 'Card', 'Online') DEFAULT 'Cash_At_Counter',
        received_by INT UNSIGNED NULL,
        paid_at TIMESTAMP NULL,
        CONSTRAINT fk_invoice_booking FOREIGN KEY (booking_id) REFERENCES bookings(booking_id) ON DELETE CASCADE,
        CONSTRAINT fk_invoice_receiver FOREIGN KEY (received_by) REFERENCES users(user_id) ON DELETE SET NULL
    ) ENGINE=InnoDB
    """,
    # PERFORMANCE INDEXES
    "CREATE INDEX idx_users_role ON users(role_id)",
    (
        "CREATE INDEX idx_bookings_date_status ON bookings(appointment_date,"
        " booking_status)"
    ),
    "CREATE INDEX idx_samples_barcode ON samples(barcode_string)",
    # VIEW 1: Lab Technician Pending Worklist
    """
    CREATE OR REPLACE VIEW vw_technician_worklist AS
    SELECT 
        s.sample_id, s.barcode_string, s.collected_at, s.sample_status,
        bi.item_id, bi.booking_id, b.booking_ref,
        u.full_name AS patient_name, pp.gender AS patient_gender,
        lt.test_id, lt.test_code, lt.test_name, lt.sample_type
    FROM samples s
    JOIN booking_items bi ON s.item_id = bi.item_id
    JOIN bookings b ON bi.booking_id = b.booking_id
    JOIN users u ON b.patient_id = u.user_id
    LEFT JOIN patient_profiles pp ON u.user_id = pp.patient_id
    JOIN lab_tests lt ON bi.test_id = lt.test_id
    WHERE s.sample_status = 'Collected' AND bi.item_status = 'Sample_Collected'
    """,
    # VIEW 2: Admin Staff Directory
    """
    CREATE OR REPLACE VIEW vw_staff_directory AS
    SELECT 
        u.user_id, u.full_name, u.email, u.phone, u.avatar_url, u.is_active, u.created_at,
        r.role_id, r.role_name, sp.employee_code, sp.qualification, sp.shift_timing, sp.joining_date
    FROM users u
    JOIN roles r ON u.role_id = r.role_id
    LEFT JOIN staff_profiles sp ON u.user_id = sp.staff_id
    WHERE u.role_id IN (2, 3)
    """,
    # TRIGGER 1: Strict Role Creation Guardrail (Only 1 Admin, and only Admin can create Staff)
    """
    CREATE TRIGGER trg_enforce_role_creation
    BEFORE INSERT ON users
    FOR EACH ROW
    BEGIN
        DECLARE admin_count INT;
        DECLARE creator_role TINYINT;

        IF NEW.role_id = 1 THEN
            SELECT COUNT(*) INTO admin_count FROM users WHERE role_id = 1;
            IF admin_count >= 1 THEN
                SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'SECURITY VIOLATION: System already has a single Master Admin.';
            END IF;
        END IF;

        IF NEW.role_id IN (2, 3) THEN
            IF NEW.created_by IS NULL THEN
                SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'SECURITY VIOLATION: Staff accounts cannot self-register. Admin ID required.';
            END IF;

            SELECT role_id INTO creator_role FROM users WHERE user_id = NEW.created_by;
            IF creator_role != 1 THEN
                SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'SECURITY VIOLATION: Only the Admin can provision Receptionist or Lab Technician accounts.';
            END IF;
        END IF;
    END
    """,
    # TRIGGER 2: Auto-flag LOW / NORMAL / HIGH on Test Result Insert
    """
    CREATE TRIGGER trg_auto_flag_test_result
    BEFORE INSERT ON test_results
    FOR EACH ROW
    BEGIN
        DECLARE v_min DECIMAL(10, 2);
        DECLARE v_max DECIMAL(10, 2);

        SELECT min_range, max_range INTO v_min, v_max
        FROM test_parameters
        WHERE param_id = NEW.param_id;

        IF NEW.measured_value < v_min THEN
            SET NEW.flag_status = 'LOW';
            SET NEW.is_abnormal = TRUE;
        ELSEIF NEW.measured_value > v_max THEN
            SET NEW.flag_status = 'HIGH';
            SET NEW.is_abnormal = TRUE;
        ELSE
            SET NEW.flag_status = 'NORMAL';
            SET NEW.is_abnormal = FALSE;
        END IF;
    END
    """,
    # TRIGGER 3: Auto-flag LOW / NORMAL / HIGH on Test Result Update
    """
    CREATE TRIGGER trg_auto_flag_test_result_update
    BEFORE UPDATE ON test_results
    FOR EACH ROW
    BEGIN
        DECLARE v_min DECIMAL(10, 2);
        DECLARE v_max DECIMAL(10, 2);

        SELECT min_range, max_range INTO v_min, v_max
        FROM test_parameters
        WHERE param_id = NEW.param_id;

        IF NEW.measured_value < v_min THEN
            SET NEW.flag_status = 'LOW';
            SET NEW.is_abnormal = TRUE;
        ELSEIF NEW.measured_value > v_max THEN
            SET NEW.flag_status = 'HIGH';
            SET NEW.is_abnormal = TRUE;
        ELSE
            SET NEW.flag_status = 'NORMAL';
            SET NEW.is_abnormal = FALSE;
        END IF;
    END
    """,
    # SEED DATA: Roles, Categories, Tests, and Parameters
    """
    INSERT INTO roles (role_id, role_name, description) VALUES
    (1, 'admin', 'System Administrator - Full control over staff, catalog, and analytics'),
    (2, 'receptionist', 'Receptionist & Phlebotomist - Handles check-in, billing, and sample barcodes'),
    (3, 'technician', 'Lab Technician - Enters parameter values and generates diagnostic reports'),
    (4, 'patient', 'Registered Patient - Books tests and views verified diagnostic reports')
    """,
    """
    INSERT INTO test_categories (category_id, category_name, department_code) VALUES
    (1, 'Hematology', 'HEM'),
    (2, 'Clinical Biochemistry', 'BIO'),
    (3, 'Endocrinology & Metabolism', 'END'),
    (4, 'Immunology & Serology', 'IMM')
    """,
    """
    INSERT INTO lab_tests (test_id, category_id, test_code, test_name, sample_type, price, turnaround_hours, pre_test_instructions) VALUES
    (1, 1, 'HEM-CBC', 'Complete Blood Count (CBC)', 'Blood (EDTA)', 1200.00, 12, 'No special fasting required.'),
    (2, 2, 'BIO-LFT', 'Liver Function Test (LFT)', 'Blood (Serum)', 1800.00, 24, '8-10 hours fasting recommended.'),
    (3, 2, 'BIO-LIP', 'Lipid Profile (Coronary Risk)', 'Fasting Blood', 2200.00, 24, 'Strict 12-hour water-only fasting required.'),
    (4, 3, 'END-FBS', 'Fasting Blood Glucose (FBS)', 'Fasting Blood', 500.00, 6, '8-10 hours overnight fasting required.'),
    (5, 2, 'BIO-RFT', 'Renal Function Test (RFT)', 'Blood (Serum)', 1600.00, 12, 'Stay normally hydrated prior to sample collection.')
    """,
    """
    INSERT INTO test_parameters (test_id, param_name, unit, min_range, max_range, display_order) VALUES
    (1, 'Hemoglobin (Hb)', 'g/dL', 13.00, 17.00, 1),
    (1, 'Total Leukocyte Count (WBC)', 'x10^3 /uL', 4.00, 11.00, 2),
    (1, 'Platelet Count', 'x10^3 /uL', 150.00, 410.00, 3),
    (1, 'Red Blood Cell Count (RBC)', 'million/uL', 4.50, 5.50, 4),
    (1, 'Hematocrit (PCV)', '%', 40.00, 50.00, 5),
    (2, 'Total Bilirubin', 'mg/dL', 0.20, 1.20, 1),
    (2, 'SGPT (ALT)', 'U/L', 7.00, 56.00, 2),
    (2, 'SGOT (AST)', 'U/L', 8.00, 48.00, 3),
    (2, 'Alkaline Phosphatase (ALP)', 'U/L', 44.00, 147.00, 4),
    (3, 'Total Cholesterol', 'mg/dL', 125.00, 200.00, 1),
    (3, 'Triglycerides', 'mg/dL', 40.00, 150.00, 2),
    (3, 'HDL Cholesterol', 'mg/dL', 40.00, 60.00, 3),
    (3, 'LDL Cholesterol', 'mg/dL', 0.00, 100.00, 4),
    (4, 'Plasma Glucose (Fasting)', 'mg/dL', 70.00, 99.00, 1),
    (5, 'Serum Creatinine', 'mg/dL', 0.70, 1.30, 1),
    (5, 'Blood Urea Nitrogen (BUN)', 'mg/dL', 7.00, 20.00, 2),
    (5, 'Serum Uric Acid', 'mg/dL', 3.50, 7.20, 3)
    """,
]


def run_setup():
  print("=" * 70)
  print("⚠️  CRITICAL SAFETY GUARD: DESTRUCTIVE ACTION DETECTED")
  print(f"This script will DROP and RECREATE the database: '{DB_NAME}'")
  print("ALL EXISTING PATIENT RECORDS, BOOKINGS, RESULTS, AND AUDITS WILL BE WIPED.")
  print("=" * 70)

  # Check for explicit environment authorization
  allow_reset = os.environ.get("ALLOW_DB_RESET", "").strip().upper()
  if allow_reset != "YES":
    try:
      confirm = input(f"To proceed, please type the database name exactly ('{DB_NAME}'): ").strip()
      if confirm != DB_NAME:
        print("❌ Aborted: Confirmation did not match database name. Database was NOT modified.")
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
      print("\n❌ Operation aborted by user. Database was NOT modified.")
      sys.exit(1)

  try:
    conn = mysql.connector.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD
    )
    cursor = conn.cursor()
    print("✅ [1/3] Connected to MySQL Server!")

    for stmt in DDL_STATEMENTS:
      cursor.execute(stmt)
    conn.commit()
    print(
        "✅ [2/3] Built `medlab_db` (12 Tables, 3 Triggers, 2 Views, 5 Lab"
        " Tests, 17 Biomarkers)!"
    )

    # Seed the single Master Admin account with pbkdf2:sha256 hashing
    admin_hash = generate_password_hash("Admin@123", method="pbkdf2:sha256")
    cursor.execute(
        """
            INSERT INTO users (role_id, full_name, email, phone, password_hash, is_active)
            VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            1,
            "Raza Ali",
            "admin@medlab.pk",
            "+923001234567",
            admin_hash,
            True,
        ),
    )
    conn.commit()

    # Export a clean .sql file into database/medlab_db_full.sql for university submission
    os.makedirs("database", exist_ok=True)
    with open("database/medlab_db_full.sql", "w", encoding="utf-8") as f:
      for stmt in DDL_STATEMENTS:
        f.write(stmt.strip() + ";\n\n")

    print("✅ [3/3] Master Admin Seeded & SQL Script Exported!")
    print("-" * 60)
    print("🔐 ADMIN LOGIN:    admin@medlab.pk")
    print("🔑 ADMIN PASSWORD: Admin@123")
    print("-" * 60)

    cursor.close()
    conn.close()

  except mysql.connector.Error as err:
    print(f"\n❌ MYSQL ERROR: {err}")


if __name__ == "__main__":
  run_setup()