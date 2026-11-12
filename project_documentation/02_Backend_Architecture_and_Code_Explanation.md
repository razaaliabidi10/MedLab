# MedLab Management System — Document 2: Backend Architecture & Implementation

---

## 1. Architectural Pattern: The Modular Monolith

MedLab follows the **Modular Monolith** architecture utilizing the **Application Factory** pattern and **Flask Blueprints**. 

Instead of an unwieldy single-file script, the backend separates concerns cleanly:
* **Configuration Layer (`config.py`)**: Centralizes environment variables, security flags, and file upload limits.
* **Extensions Layer (`extensions.py`)**: Decouples third-party extensions to eliminate circular dependencies.
* **Database Access Layer (`db.py`)**: Provides clean database connection pooling and raw SQL parameterization with automated transaction rollbacks.
* **Domain Model Layer (`models.py`)**: Wraps database records into object-oriented representations and enforces Role-Based Access Control (RBAC).
* **Validation Layer (`forms.py`)**: Intercepts and sanitizes user input using cryptographic CSRF tokens and strict WTForms validators.
* **Controller / Routing Layer (`routes/`)**: Encapsulates role-specific business logic into dedicated Blueprints.

```
                    ┌───────────────────────────────┐
                    │            app.py             │
                    │      (Application Factory)    │
                    └───────────────┬───────────────┘
                                    │
           ┌────────────────────────┼────────────────────────┐
           ▼                        ▼                        ▼
    extensions.py               config.py                  db.py
 (Login, CSRF, Limiter)   (Env & Security Flags)   (Pool, Query, Execute)
           │                        │                        │
           └────────────────────────┼────────────────────────┘
                                    ▼
                          models.py & forms.py
                       (User Class, RBAC Decorator)
                                    │
    ┌───────────┬───────────┬───────┴───┬───────────┬───────────┐
    ▼           ▼           ▼           ▼           ▼           ▼
auth.py     admin.py   receptionist.py tech.py  pathologist.py patient.py
```

---

## 2. Walkthrough of Core Root Files

### `app.py` — Application Factory & Master Entry Point
* **Purpose**: Creates, configures, and assembles the Flask WSGI application instance.
* **Key Functions & Logic**:
  * `create_app()`: Instantiates `Flask(__name__)`, loads configuration from `Config`, and initializes `extensions.py` (`login_manager`, `csrf`, `limiter`).
  * **Blueprint Registration**: Registers all 9 Blueprints (`auth_bp`, `admin_bp`, `receptionist_bp`, `technician_bp`, `patient_bp`, `collector_bp`, `pathologist_bp`, `notifications_bp`, `supabase_auth_bp`).
  * **Security Hooks**:
    * `@app.before_request enforce_password_change()`: If a user is flagged with `must_change_password = 1`, all requests (except logout and password change) are redirected to the password update screen.
    * `@app.after_request apply_security_headers()`: Injects HTTP security headers into every response:
      * `X-Content-Type-Options: nosniff` (prevents MIME-type sniffing attacks).
      * `X-Frame-Options: DENY` (mitigates clickjacking).
      * `Referrer-Policy: strict-origin-when-cross-origin`.
      * `Cache-Control: no-store` (prevents browser caching of private patient records after logout).
  * **Global Template Context (`inject_globals()`)**: Injects the server's live Karachi date (`today_karachi`), current time (`now_karachi_time`), and unread notification counts into every rendered Jinja template.
  * **Error Handlers**: Custom views for HTTP 403 (Forbidden), 404 (Not Found), 500 (Internal Server Error), and an interceptor for **MySQL Error 1644 / SQLSTATE 45000** (translating raw database trigger rejections into clean, visible user flash alerts).

---

### `config.py` — Environment & Security Configuration
* **Purpose**: Parses environment variables using `python-dotenv` and defines runtime operational rules.
* **Key Settings**:
  * `SECRET_KEY`: Cryptographic signing key for sessions and CSRF tokens. In production, a missing or default key raises an immediate fatal exception.
  * `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`: MySQL connection parameters.
  * `SESSION_COOKIE_HTTPONLY = True`: Blocks JavaScript `document.cookie` access (mitigating XSS session theft).
  * `SESSION_COOKIE_SAMESITE = 'Lax'`: Mitigates Cross-Site Request Forgery (CSRF).
  * `MAX_CONTENT_LENGTH = 2MB`: Restricts file upload sizes to prevent server memory exhaustion.
  * `ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}`: Whitelist for avatar uploads.

---

### `extensions.py` — Decoupled Singletons
* **Purpose**: Breaks circular import cycles between `app.py` and route modules.
* **Contents**:
  * `login_manager = LoginManager()`: Handles session authentication.
  * `csrf = CSRFProtect()`: Manages token issuance and validation.
  * `limiter = Limiter(key_func=get_remote_address)`: Rate-limiting provider.

---

### `db.py` — Database Engine & Transaction Management
* **Purpose**: Centralized database access layer communicating directly with MySQL.
* **Key Functions**:
  * `get_db_connection()`: Opens a fresh TCP connection to MySQL with character set `utf8mb4` and `autocommit=False`.
  * `query_db(sql, params=(), one=False)`:
    * Executes `SELECT` statements using a dictionary cursor (`cursor(dictionary=True)`).
    * Automatically closes cursors and connections in a `finally` block to prevent connection leaks.
    * Returns a list of dictionaries, or a single dictionary if `one=True`.
  * `execute_db(sql, params=())`:
    * Executes `INSERT`, `UPDATE`, or `DELETE` statements inside an ACID transaction.
    * Calls `conn.commit()` upon success and returns `cursor.lastrowid`.
    * Calls `conn.rollback()` if any error occurs, ensuring data consistency.

---

### `models.py` — Domain Models & Role Authorization
* **Purpose**: Defines user identity state and role access rules.
* **Key Elements**:
  * `class User(UserMixin)`: Wraps database rows into a Flask-Login compatible user object. Contains properties like `.is_admin`, `.is_receptionist`, `.is_technician`, `.is_patient`, `.is_collector`, and `.is_pathologist`.
  * `User.load(user_id)`: Static method queried by `login_manager.user_loader` to hydrate the active user from MySQL on every authenticated request.
  * `@role_required(*roles)`: Custom Python decorator. Checks if `current_user.role_id` exists in the allowed roles list; if not, immediately raises `abort(403)` (Forbidden).

---

### `forms.py` — Secure WTForms Validation
* **Purpose**: Validates all incoming form payloads prior to database queries.
* **Key Forms**:
  * `LoginForm`: Validates email/username and password.
  * `SignupForm`: Patient self-registration with strong password enforcement (length >= 8, uppercase, lowercase, numbers, special characters).
  * `ChangePasswordForm`: Enforces current password verification and new password matching.
  * `StaffForm`: Admin form for provisioning staff with employee codes, shifts, and qualifications.
  * `TestForm`: CRUD form for lab tests (pricing, turnaround hours, sample types).
  * `ResultEntryForm`: Dynamic biomarker entry form with range bounds.

---

### `build_db.py` — Database Initialization Runner
* **Purpose**: Standalone CLI script that creates the MySQL database from scratch, executes DDL statements, applies indexes, triggers, and seed data.

---

## 3. Walkthrough of the `routes/` Directory (Blueprints)

Every subsystem in MedLab is isolated within its own Blueprint in the `routes/` folder:

### 1. `routes/auth.py` — Authentication & Identity
* **Prefix / Scope**: `/login`, `/logout`, `/signup`, `/profile`, `/change-password`
* **Functionality**:
  * **Smart Username/Email Matching**: Allows logging in via full email or shorthand role handles (`admin`, `reception`, `tech`, `doctor`, `collector`, `patient`).
  * **Brute-Force Lockout Protection**: Increments `login_attempts` in MySQL on bad credentials; locks the account for 15 minutes (`lockout_until`) after 5 consecutive failures.
  * **Password Hashing**: Uses `werkzeug.security.check_password_hash` with PBKDF2/SHA-256 salt.
  * **Profile Management**: Allows updating phone numbers, addresses, and uploading profile avatars with secure image sanitization.

### 2. `routes/admin.py` — System Administration
* **Prefix / Scope**: `/admin/...` (Protected with `@role_required(1)`)
* **Functionality**:
  * **Analytics Dashboard**: Aggregates total revenue (PKR), active patient counts, test volumes, and recent system transactions.
  * **Staff Management**: Provisions new staff accounts (Receptionist, Technician, Collector, Pathologist) and automatically populates `staff_profiles`.
  * **Diagnostic Catalog Management**: Full CRUD operations on test categories (`test_categories`), lab tests (`lab_tests`), and reference parameters (`test_parameters`).
  * **Audit Trail**: Reads the immutable `audit_log` table to monitor system actions, logins, and status transitions.

### 3. `routes/receptionist.py` — Front Desk & Cash Counter
* **Prefix / Scope**: `/receptionist/...` (Protected with `@role_required(2)`)
* **Functionality**:
  * **Today's Patient Queue**: Displays all appointments scheduled for the current date in Karachi time.
  * **Walk-In Registration**: Quickly registers unregistered walk-in patients, selects required tests, and generates a booking with appointment slot.
  * **Billing & Counter Invoicing**: Generates invoices (`invoices` table), accepts cash or card payments, and marks invoices as `Paid`.
  * **Barcode Print View**: Renders printable barcode labels for specimen vials.

### 4. `routes/collector.py` — Sample Collection & Phlebotomy
* **Prefix / Scope**: `/collector/...` (Protected with `@role_required(5)`)
* **Functionality**:
  * **Field & Lab Worklist**: Lists all confirmed bookings awaiting phlebotomy, distinguishing between in-lab collections and home visits (with addresses).
  * **Specimen Check-In**: Marks items as `Sample_Collected`, inserts a record into the `samples` table, and assigns a unique barcode string.
  * **Sample Rejection**: Allows collectors to reject hemolyzed or insufficient samples with reason logging, triggering a notification for the patient.

### 5. `routes/technician.py` — Laboratory Analysis
* **Prefix / Scope**: `/technician/...` (Protected with `@role_required(3)`)
* **Functionality**:
  * **Active Lab Worklist**: Queries the `vw_technician_worklist` view for collected samples awaiting measurement.
  * **Biomarker Entry**: Provides dynamic parameter entry screens for each test (e.g., RBC, WBC, Platelets for CBC).
  * **Batch Submission**: Saves measured values to `test_results`. Database triggers immediately evaluate physiological ranges and assign `flag_status`.
  * **Revision Handling**: Displays samples that were rejected or returned by the pathologist with specific revision notes.

### 6. `routes/pathologist.py` — Clinical Verification & Sign-Off
* **Prefix / Scope**: `/pathologist/...` (Protected with `@role_required(6)`)
* **Functionality**:
  * **Verification Queue**: Lists all analyzed tests awaiting medical doctor approval.
  * **Abnormal Value Highlighting**: Distinctly highlights values flagged as `LOW` or `HIGH` with red warning badges.
  * **Approval / Sign-Off**: The pathologist approves the report, records doctor notes, and timestamps `released_at`. This unlocks the diagnostic report for the patient.
  * **Return for Revision**: Allows sending suspicious results back to the technician with mandatory feedback comments.

### 7. `routes/patient.py` — Patient Self-Service Portal
* **Prefix / Scope**: `/patient/...` (Protected with `@role_required(4)`)
* **Functionality**:
  * **Online Test Booking**: Patients select tests from the interactive catalog, pick home or lab collection, and choose an available time slot.
  * **Status Timeline**: Real-time visual progress tracker showing the current stage (`Booked` -> `Sample Collected` -> `In Analysis` -> `Pending Verification` -> `Completed`).
  * **Report Access**: Displays verified clinical reports and allows one-click printing or PDF downloading.

### 8. `routes/notifications.py` — In-App Alert System
* **Prefix / Scope**: `/notifications/...`
* **Functionality**:
  * Serves user notification feeds and provides an unread badge counter endpoint queried via lightweight JSON polling.

### 9. `routes/supabase_auth.py` — Cloud Identity Integration
* **Prefix / Scope**: `/auth/supabase/...`
* **Functionality**:
  * Handles OAuth token callbacks and synchronizes Supabase cloud identities with the local MySQL `users` table.

