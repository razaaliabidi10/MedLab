# MedLab Management System — Document 1: Overall Project Explanation

---

## 1. Executive Summary & Project Purpose

The **MedLab Management System** is an enterprise-grade, full-stack Hospital & Clinical Diagnostic Laboratory Management System. It was engineered to automate and digitize the end-to-end operational lifecycle of clinical pathology laboratories, diagnostic clinics, and hospital testing departments.

In a traditional clinical laboratory, paper slips, disconnected spreadsheets, and manual registers cause dangerous communication gaps: samples get misplaced, results are transcribed with human error, billing reconciliations fail, and turnaround times are prolonged. MedLab replaces this with a unified, role-governed digital platform.

### Core Objectives
1. **Clinical Precision & Quality Control**: Prevent diagnostic errors by enforcing automated reference range validation (flagging `LOW`, `NORMAL`, or `HIGH` biomarker levels) and requiring mandatory pathologist sign-off before releasing reports to patients.
2. **Chain-of-Custody Sample Tracking**: Track specimens from the moment of phlebotomy (sample collection) through unique barcode identifiers, eliminating mix-ups between lab samples and patients.
3. **Multi-Role Clinical Collaboration**: Provide dedicated, secure interfaces for six distinct stakeholders: System Administrators, Receptionists, Sample Collectors (phlebotomists), Lab Technicians, Consultant Pathologists (Doctors), and Patients.
4. **Financial Transparency & Counter Operations**: Support walk-in booking, invoice generation, payment tracking (cash, credit/debit card, online), and discount health packages in Pakistani Rupees (PKR).
5. **Localization & Compliance**: Real-time appointment scheduling tailored to the Asia/Karachi (PKT, UTC+5) timezone, strict role-based access control (RBAC), and immutable database audit trails.

---

## 2. End-to-End Operational Workflow

The system coordinates the complete medical diagnostic pipeline through eight sequential phases:

```
[Patient / Receptionist] ──> 1. Booking & Slot Selection (Karachi PKT)
                                      │
                                      ▼
[Counter / Receptionist] ──> 2. Invoice Generation & Payment (PKR)
                                      │
                                      ▼
[Sample Collector]       ──> 3. Phlebotomy & Barcode Assignment (Lab / Home)
                                      │
                                      ▼
[Lab Technician]         ──> 4. Biomarker Measurement & Result Entry
                                      │
                                      ▼
[Database Engine]        ──> 5. Automated Reference Range Checking (Triggers)
                                      │
                                      ▼
[Consultant Pathologist] ──> 6. Clinical Verification & Medical Sign-Off
                                      │
                                      ▼
[System Engine]          ──> 7. Report Release & Patient Notification
                                      │
                                      ▼
[Patient Portal]         ──> 8. Diagnostic Report View & PDF Download
```

1. **Test Selection & Booking**: Patients browse categorized diagnostic tests (e.g., Complete Blood Count, Liver Function Test, Lipid Profile) or bundled packages online, or receptionists register walk-in patients. Bookings specify collection type (In-Lab Visit or Home Phlebotomy Visit) and an appointment slot.
2. **Billing & Invoicing**: An official invoice with a unique invoice number (e.g., `INV-202611-0001`) is generated with status `Unpaid` or `Paid`.
3. **Specimen Collection (Phlebotomy)**: A collector marks samples collected and generates a unique barcode (e.g., `MED-2026-0001-CBC`). If a specimen is hemolyzed or insufficient, the collector can reject it with an auditable reason.
4. **Laboratory Analysis**: Lab technicians access the pending worklist, input measured biomarker values into parameter forms, and record analytical findings.
5. **Automated Quality Checks**: MySQL database triggers immediately compare each numerical value against defined physiological reference ranges (e.g., Hemoglobin `13.00 - 17.00 g/dL`) and calculate flag statuses (`LOW`, `NORMAL`, `HIGH`) without relying on error-prone frontend math.
6. **Pathologist Sign-Off**: A consultant pathologist reviews all flagged values. If abnormal, the doctor either signs off and attaches clinical recommendations or sends the sample back to the technician for re-testing with revision comments.
7. **Report Release**: Upon pathologist approval, the report status transitions to `Completed` and unlocks for the patient.
8. **Patient Delivery**: The patient receives an in-app notification, views the clinical report online, or prints an official laboratory report.

---

## 3. Technology Stack & Framework Selection

### Backend Framework: Flask 3.1.3 (Python 3.14)
The application is built on **Flask**, a lightweight, robust, and extensible Python Web Server Gateway Interface (WSGI) framework. 

**Why Flask was chosen over Django or FastAPI:**
* **Full Architectural Control**: Unlike Django's heavy ORM and rigid conventions, Flask enables direct, high-performance SQL integration with MySQL, allowing complex database triggers, stored procedures, and strict relational integrity to be leveraged natively.
* **Modular Blueprint Architecture**: Flask Blueprints (`flask.Blueprint`) allow clean segregation of business logic by role (`admin`, `receptionist`, `technician`, `pathologist`, `collector`, `patient`, `auth`).
* **Lightweight Footprint**: Minimal memory and CPU consumption, providing rapid server spin-up and low response latencies.
* **Security Extensibility**: Seamless integration with enterprise security middleware for CSRF protection, brute-force rate limiting, and HTTP security headers.

---

## 4. Installed Libraries, Modules & Their Roles

The system utilizes specialized open-source libraries, each serving a critical function in the architecture:

| Library / Module | Version | Architectural Role & Functionality |
| :--- | :--- | :--- |
| **Flask** | `3.1.3` | **Core Web Framework**: Handles HTTP routing, request/response lifecycle, template rendering, and application context. |
| **Flask-Login** | `0.6.3` | **Session & Authentication Management**: Manages user login states, session serialization (`user_loader`), persistent cookies, and `@login_required` decorators. |
| **Flask-WTF** | `1.3.0` | **Form Security & CSRF Defense**: Bridges WTForms into Flask, automatically injecting and validating cryptographic Cross-Site Request Forgery (CSRF) tokens for all POST/PUT requests. |
| **WTForms** | `3.2.2` | **Data Validation & Sanitization**: Validates form inputs (lengths, regex constraints, numerical bounds) before reaching database execution. |
| **Flask-Limiter** | `3.8.0` | **Brute-Force & DoS Mitigation**: Implements rate limiting on sensitive routes (e.g., login, password reset) to prevent automated credential stuffing. |
| **mysql-connector-python** | `26.7.0` | **Official Oracle MySQL Driver**: Connects Python directly to MySQL 8.x over TCP/IP without heavy ORM overhead. Supports connection pooling, transactions, and UTF-8 multibyte encoding (`utf8mb4`). |
| **Werkzeug** | `3.1.9` | **Security & Utilities**: Provides secure password hashing (`generate_password_hash`, `check_password_hash`), secure filename sanitization (`secure_filename`), and HTTP exceptions. |
| **python-dotenv** | `1.2.4` | **Configuration Management**: Loads sensitive credentials (database passwords, secret keys) from an external `.env` file following Twelve-Factor App principles. |
| **reportlab** | `5.1.0` | **PDF Document Generation**: Programmatically constructs pixel-perfect, printable clinical laboratory reports, invoices, and diagnostic summaries. |
| **Pillow (PIL)** | `13.0.0` | **Imaging Library**: Processes, resizes, and validates uploaded user avatars and hospital logos. |
| **cryptography** | `50.0.2` | **Cryptographic Primitives**: Provides underlying mathematical support for secure tokens, password hashing algorithms, and SSL/TLS communication. |
| **supabase** | `2.33.0` | **Third-Party Auth Bridge**: Optional OAuth / Supabase authentication bridge for multi-provider identity federation. |

---

## 5. Role-Based Access Control (RBAC) Matrix

MedLab enforces strict principle-of-least-privilege RBAC. Each user belongs to exactly one role:

| Role ID | Role Name | System Access & Responsibilities |
| :---: | :--- | :--- |
| **1** | **Admin** | Master System Administrator. Full access to system logs, financial KPIs, staff onboarding, user suspension, and diagnostic test catalog management. |
| **2** | **Receptionist** | Front-desk operator. Handles patient check-in, walk-in bookings, invoice printing, counter cash/card collection, and specimen routing. |
| **3** | **Technician** | Medical Laboratory Technologist. Accesses the pending sample worklist, enters biochemical and hematological parameter values, and submits batches. |
| **4** | **Patient** | Registered Client. Views available diagnostic tests, books appointments with slot selection, tracks sample statuses in real time, and views released reports. |
| **5** | **Sample Collector** | Phlebotomist / Field Worker. Manages home visits and lab counter collection, confirms specimen collection, assigns barcodes, and logs sample rejections. |
| **6** | **Pathologist** | Medical Doctor / Consultant Pathologist. Reviews technician findings, checks abnormal flags, sends back samples with revision notes, and officially approves reports. |

---

## 6. Summary of Architectural Strengths

* **Zero Data Loss & ACID Compliance**: Relational MySQL database using InnoDB engine with foreign keys, transactional rollbacks, and unique business constraints.
* **Separation of Concerns**: Clean Model-View-Controller (MVC) organization where the database handles business rules and data consistency, Flask coordinates flow control and security, and the frontend handles presentation.
* **Defense-in-Depth Security**: Multi-layer security including CSRF protection, rate limiting, SQL parameterization, HTTP security headers (`nosniff`, `X-Frame-Options: DENY`, `Strict-Transport-Security`), and password lockout policies.

