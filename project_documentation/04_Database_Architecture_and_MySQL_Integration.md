# MedLab Management System — Document 4: Database Architecture & MySQL Integration

---

## 1. How the MySQL Database Connection Works

### Architecture: Separation of Client & Server
A common point of confusion in web development is how the database is connected. 

In MedLab, **MySQL does not run inside the Python code or inside Antigravity**. 
* **MySQL Server** is an independent, dedicated relational database server daemon running on the host system (listening on TCP port `3306`). It manages physical disk storage, table spaces, indexes, transactions, and concurrency locking.
* **Antigravity / Flask Workspace** is the client application environment where Python processes run. 

They communicate over the **TCP/IP networking protocol** using standard MySQL client protocol packets:

```
┌──────────────────────────────────────────────┐
│           Python / Flask Client              │
│       (Running inside Antigravity)           │
│                                              │
│   1. Reads credentials from .env             │
│   2. Calls db.get_db_connection()            │
└──────────────────────┬───────────────────────┘
                       │
                       │ TCP/IP Socket Connection (127.0.0.1:3306)
                       ▼
┌──────────────────────────────────────────────┐
│             MySQL Database Server            │
│          (Independent Daemon Process)        │
│                                              │
│   • Database: medlab_db                      │
│   • Character Set: utf8mb4                   │
│   • Storage Engine: InnoDB (ACID compliant)  │
│   • Triggers, Foreign Keys & Relational DDL  │
└──────────────────────────────────────────────┘
```

---

### The Connection Pipeline Step-by-Step

#### Step 1: Environment Configuration (`.env`)
Database credentials are never hardcoded in source code. They are defined in the project's root `.env` file:
```ini
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=medlab_db
```

#### Step 2: Configuration Hydration (`config.py`)
At server startup, `python-dotenv` loads the variables into Python's `os.environ`, and `config.py` binds them to the `Config` class:
```python
class Config:
    DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
    DB_PORT = int(os.environ.get("DB_PORT", 3306))
    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_NAME = os.environ.get("DB_NAME", "medlab_db")
```

#### Step 3: Establishing the Connection Handle (`db.py`)
When a request requires database access, `db.get_db_connection()` is called. It uses Oracle's official `mysql.connector` driver:
```python
import mysql.connector
from flask import current_app

def get_db_connection():
    cfg = current_app.config
    return mysql.connector.connect(
        host=cfg["DB_HOST"],
        port=cfg["DB_PORT"],
        user=cfg["DB_USER"],
        password=cfg["DB_PASSWORD"],
        database=cfg["DB_NAME"],
        charset="utf8mb4",
        collation="utf8mb4_unicode_ci",
        autocommit=False,  # Enforces explicit transaction control
    )
```

#### Step 4: Query Execution & Resource Cleanup
`db.py` provides two distinct helper functions to ensure safe execution:

1. **`query_db(sql, params=(), one=False)`** — For read-only operations (`SELECT`):
   * Uses a dictionary cursor (`cursor(dictionary=True)`), so rows are returned as readable key-value objects rather than raw tuples.
   * Employs parameterized queries (`%s`), completely immunizing the system against **SQL Injection**.
   * Always closes cursors and connections inside a `finally:` block, preventing MySQL connection leaks or "Too Many Connections" crashes.

2. **`execute_db(sql, params=())`** — For write operations (`INSERT`, `UPDATE`, `DELETE`):
   * Wraps queries inside an explicit transaction.
   * Calls `conn.commit()` upon successful execution and returns `cursor.lastrowid`.
   * Calls `conn.rollback()` if an error or trigger failure occurs, guaranteeing that no partial or corrupt state is saved.

---

## 2. Exhaustive Walkthrough of Database Tables

The `medlab_db` database is structured strictly in Third Normal Form (3NF) across 17 relational tables, using the **InnoDB** storage engine:

### 1. `roles` (Lookup Table)
Defines authorized user categories.
* `role_id` (TINYINT UNSIGNED, PK): Numeric role identifier (1 to 6).
* `role_name` (VARCHAR(30), UNIQUE): Machine name (`admin`, `receptionist`, `technician`, `patient`, `sample_collector`, `pathologist`).
* `description` (VARCHAR(255)): Human-readable role description.

### 2. `users` (Core Authentication Table)
Stores user credentials and security state.
* `user_id` (INT UNSIGNED, AUTO_INCREMENT, PK): Primary user ID.
* `role_id` (TINYINT UNSIGNED, FK -> `roles.role_id`): User's operational role.
* `full_name` (VARCHAR(100)): Full legal name.
* `email` (VARCHAR(120), UNIQUE): Unique login email address.
* `phone` (VARCHAR(20), UNIQUE): Contact telephone number.
* `password_hash` (VARCHAR(255)): PBKDF2/SHA-256 salted password hash.
* `avatar_url` (VARCHAR(255)): Filename of the user's profile avatar.
* `is_active` (BOOLEAN): Account status flag.
* `login_attempts` (TINYINT UNSIGNED): Failed login counter for brute-force lockout.
* `lockout_until` (TIMESTAMP, NULL): Expiration time of temporary login lockout.
* `must_change_password` (BOOLEAN): Flags temporary passwords that must be changed on next login.
* `email_verified` (BOOLEAN): Email verification status.
* `auth_provider` (ENUM('local','google')): Identity provider.
* `created_by` (INT UNSIGNED, FK -> `users.user_id`): Staff administrator who created the account.

### 3. `patient_profiles` (1:1 Extension Table)
Stores clinical demographics for registered patients.
* `patient_id` (INT UNSIGNED, PK, FK -> `users.user_id` ON DELETE CASCADE): Ties directly to the user record.
* `date_of_birth` (DATE): Patient birth date (used to calculate age for reference ranges).
* `gender` (ENUM('Male', 'Female', 'Other')): Biological sex.
* `blood_group` (ENUM('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')): Blood group type.
* `address` (VARCHAR(255)): Residential address for home sample collection.
* `medical_notes` (TEXT): Chronic conditions, allergies, or physician notes.

### 4. `staff_profiles` (1:1 Extension Table)
Stores employment metadata for hospital personnel.
* `staff_id` (INT UNSIGNED, PK, FK -> `users.user_id` ON DELETE CASCADE): Ties to the staff member's user record.
* `employee_code` (VARCHAR(20), UNIQUE): Official staff identification code (e.g., `EMP-001`).
* `qualification` (VARCHAR(120)): Degrees and certifications (e.g., `MBBS, FRCPath`, `BSc MLT`).
* `shift_timing` (ENUM('Morning', 'Evening', 'Night')): Assigned work shift.
* `joining_date` (DATE): Date of employment commencement.

### 5. `test_categories` (Catalog Grouping)
Organizes diagnostic tests by laboratory department.
* `category_id` (INT UNSIGNED, AUTO_INCREMENT, PK): Category identifier.
* `category_name` (VARCHAR(80), UNIQUE): Department name (`Hematology`, `Clinical Biochemistry`, etc.).
* `department_code` (VARCHAR(10), UNIQUE): Short code (e.g., `HEM`, `BIO`, `END`).
* `is_active` (BOOLEAN): Availability flag.

### 6. `lab_tests` (Diagnostic Test Catalog)
Master catalog of available medical examinations.
* `test_id` (INT UNSIGNED, AUTO_INCREMENT, PK): Test identifier.
* `category_id` (INT UNSIGNED, FK -> `test_categories.category_id`): Department.
* `test_code` (VARCHAR(20), UNIQUE): Laboratory test code (e.g., `HEM-CBC`, `BIO-LFT`).
* `test_name` (VARCHAR(120), UNIQUE): Clinical test name.
* `sample_type` (ENUM('Blood (EDTA)', 'Blood (Serum)', 'Fasting Blood', 'Urine', 'Swab')): Required specimen vial.
* `price` (DECIMAL(10,2)): Base cost in Pakistani Rupees (PKR).
* `turnaround_hours` (INT UNSIGNED): Expected turnaround time (e.g., 12 or 24 hours).
* `pre_test_instructions` (VARCHAR(255)): Patient preparation rules (e.g., fasting requirements).
* `is_active` (BOOLEAN): Active status.

### 7. `test_parameters` (Biomarkers & Reference Ranges)
Defines individual analytes measured within each test and their normal physiological boundaries.
* `param_id` (INT UNSIGNED, AUTO_INCREMENT, PK): Analyte identifier.
* `test_id` (INT UNSIGNED, FK -> `lab_tests.test_id` ON DELETE CASCADE): Parent test.
* `param_name` (VARCHAR(100)): Chemical/cellular name (e.g., `Hemoglobin (Hb)`, `Platelet Count`).
* `unit` (VARCHAR(30)): Measurement unit (e.g., `g/dL`, `x10^3 /uL`, `mg/dL`).
* `min_range` (DECIMAL(10,2)): Minimum physiological reference value.
* `max_range` (DECIMAL(10,2)): Maximum physiological reference value.
* `display_order` (TINYINT UNSIGNED): Sequence ordering on printed reports.
* *Constraint*: `CHECK (max_range >= min_range)` ensures inverted bounds cannot be entered.

### 8. `time_slots` (Capacity-Managed Appointment Windows)
Controls booking capacity per date and time window.
* `slot_id` (INT UNSIGNED, AUTO_INCREMENT, PK): Slot identifier.
* `slot_date` (DATE): Appointment date.
* `slot_label` (ENUM): Time window (`08:00 AM - 10:00 AM`, `10:00 AM - 12:00 PM`, `02:00 PM - 04:00 PM`, `04:00 PM - 06:00 PM`).
* `max_capacity` (TINYINT UNSIGNED): Maximum appointments allowed per window (default 20).
* `booked_count` (TINYINT UNSIGNED): Current reservations in this slot.
* `is_active` (BOOLEAN): Slot availability flag.

### 9. `packages` & `package_tests` (Discount Bundles)
* `packages`: Health checkup packages (e.g., Executive Health Checkup) offering promotional discounts (`discount_pct`).
* `package_tests`: M:N composite junction table mapping multiple `lab_tests` to a `package`.

### 10. `bookings` (Master Booking Orders)
Tracks patient reservations and end-to-end clinical workflow state.
* `booking_id` (INT UNSIGNED, AUTO_INCREMENT, PK): Master booking ID.
* `booking_ref` (VARCHAR(25), UNIQUE): Human-readable reference (e.g., `BK-202611-0001`).
* `patient_id` (INT UNSIGNED, FK -> `users.user_id`): Client user ID.
* `slot_id` (INT UNSIGNED, FK -> `time_slots.slot_id`): Assigned appointment slot.
* `appointment_date` (DATE): Scheduled examination date.
* `appointment_slot` (VARCHAR(50)): Text label of the appointment window.
* `collection_type` (ENUM('Lab', 'Home')): Counter phlebotomy visit or home collection.
* `collection_address` (VARCHAR(255)): Destination address for home phlebotomy visits.
* `collector_id` (INT UNSIGNED, FK -> `users.user_id`): Phlebotomist assigned to collect specimen.
* `pathologist_id` (INT UNSIGNED, FK -> `users.user_id`): Consultant doctor who signed off the report.
* `booking_status` (ENUM): Current clinical lifecycle state:
  `Booked` -> `Sample_Collected` -> `In_Analysis` -> `Pending_Verification` -> `Completed` (or `Cancelled`).
* `released_at` (TIMESTAMP, NULL): Exact moment the pathologist unlocked the report.
* `verification_notes` (TEXT): Clinical remarks written by the pathologist.

### 11. `booking_items` (Order Line Items)
Line items mapping tests to a booking.
* `item_id` (INT UNSIGNED, AUTO_INCREMENT, PK): Line item identifier.
* `booking_id` (INT UNSIGNED, FK -> `bookings.booking_id` ON DELETE CASCADE).
* `test_id` (INT UNSIGNED, FK -> `lab_tests.test_id`): Ordered test.
* `price_at_booking` (DECIMAL(10,2)): Frozen price snapshot at the moment of booking.
* `item_status` (ENUM('Pending_Sample', 'Sample_Collected', 'Report_Ready')).

### 12. `samples` (Specimen & Barcode Tracking)
Tracks physical sample tubes and laboratory chain-of-custody.
* `sample_id` (INT UNSIGNED, AUTO_INCREMENT, PK): Specimen record ID.
* `item_id` (INT UNSIGNED, UNIQUE, FK -> `booking_items.item_id` ON DELETE CASCADE).
* `barcode_string` (VARCHAR(40), UNIQUE): Machine-scannable barcode (e.g., `MED-2026-0001-CBC`).
* `collected_by` (INT UNSIGNED, FK -> `users.user_id`): Phlebotomist who drew the sample.
* `collected_at` (TIMESTAMP): Date and time of specimen collection.
* `sample_status` (ENUM('Collected', 'Analyzed', 'Rejected')).
* `rejection_reason` (VARCHAR(255)): Mandatory explanation if a specimen is discarded.

### 13. `test_results` (Biomarker Measurements)
Records analytical values and automated abnormal flags.
* `result_id` (INT UNSIGNED, AUTO_INCREMENT, PK): Result record ID.
* `item_id` (INT UNSIGNED, FK -> `booking_items.item_id` ON DELETE CASCADE).
* `param_id` (INT UNSIGNED, FK -> `test_parameters.param_id`): Analyte measured.
* `measured_value` (DECIMAL(10,2)): Exact numerical reading recorded by the technician.
* `flag_status` (ENUM('LOW', 'NORMAL', 'HIGH')): Automated physiological evaluation calculated by triggers.
* `is_abnormal` (BOOLEAN): Boolean indicator (TRUE if `flag_status != 'NORMAL'`).
* `technician_id` (INT UNSIGNED, FK -> `users.user_id`): Technologist who entered the data.
* `verified_at` (TIMESTAMP): Data entry timestamp.
* `verified_by` (INT UNSIGNED, FK -> `users.user_id`): Doctor who verified the measurement.
* `pathologist_comment` (TEXT): Revision instructions if sent back for re-testing.

### 14. `invoices` (Billing & Payments)
Manages financial accounting.
* `invoice_id` (INT UNSIGNED, AUTO_INCREMENT, PK): Invoice record ID.
* `booking_id` (INT UNSIGNED, UNIQUE, FK -> `bookings.booking_id` ON DELETE CASCADE).
* `invoice_number` (VARCHAR(30), UNIQUE): Formatted invoice number (e.g., `INV-202611-0001`).
* `total_amount` (DECIMAL(10,2)): Net payable amount in PKR.
* `payment_status` (ENUM('Unpaid', 'Paid', 'Refunded')): Payment reconciliation status.
* `payment_method` (ENUM('Cash_At_Counter', 'Card', 'Online')): Payment medium.
* `received_by` (INT UNSIGNED, FK -> `users.user_id`): Cashier or receptionist who collected payment.
* `paid_at` (TIMESTAMP, NULL): Timestamp of payment receipt.

### 15. `notifications` (User Alert Dispatch)
In-app notification system.
* `notification_id` (INT UNSIGNED, AUTO_INCREMENT, PK).
* `user_id` (INT UNSIGNED, FK -> `users.user_id` ON DELETE CASCADE): Target recipient.
* `type` (ENUM('booking', 'payment', 'sample', 'result', 'account', 'general')).
* `title` (VARCHAR(150)): Alert headline.
* `message` (TEXT): Detailed notification text.
* `link` (VARCHAR(255)): URL destination for quick navigation.
* `is_read` (BOOLEAN): Read status.

### 16. `audit_log` (Compliance & Security Trail)
Immutable security log recording critical actions.
* `log_id` (INT UNSIGNED, AUTO_INCREMENT, PK).
* `user_id` (INT UNSIGNED, FK -> `users.user_id` ON DELETE SET NULL).
* `action` (VARCHAR(60)): Action identifier (e.g., `LOGIN_SUCCESS`, `CREATE_BOOKING`, `APPROVE_REPORT`).
* `table_affected` (VARCHAR(50)): Database table name.
* `record_id` (INT UNSIGNED): Primary key of the affected row.
* `details` (TEXT): JSON or descriptive payload of changes.
* `ip_address` (VARCHAR(45)): Client IP address.
* `created_at` (TIMESTAMP): Event timestamp.

---

## 3. Database Logic: Triggers, Views & Engines

### Automated Physiological Flagging Triggers
Quality control is enforced at the database level rather than the frontend:
* **`trg_auto_flag_test_result` (BEFORE INSERT)** & **`trg_auto_flag_test_result_update` (BEFORE UPDATE)**:
  When a technician inserts or updates a row in `test_results`, the trigger queries `test_parameters` for `min_range` and `max_range`:
  ```sql
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
  ```
  This guarantees that human oversight can never accidentally publish an out-of-range value as normal.

### Architectural Security Trigger
* **`trg_enforce_role_creation` (BEFORE INSERT ON `users`)**:
  * Blocks creating more than one Master Admin account (`role_id = 1`).
  * Enforces that Staff accounts (roles 2, 3, 5, 6) can never self-register; they can only be created by an authenticated Administrator. Any violation raises `SQLSTATE '45000'`.

### Optimized Views
* **`vw_technician_worklist`**: Performs pre-joined, indexed queries across `samples`, `booking_items`, `bookings`, `users`, `patient_profiles`, and `lab_tests` to return pending laboratory tasks without complex application queries.
* **`vw_staff_directory`**: Aggregates staff records across all employment roles for directory displays.

