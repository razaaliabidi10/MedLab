<div align="center">

# 🔬 MedLab Diagnostics
### *Clinical Pathology & Diagnostic Laboratory Management System*

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![MySQL](https://img.shields.io/badge/MySQL-8.0_InnoDB-4479A1?style=for-the-badge&logo=mysql&logoColor=white)](https://mysql.com)
[![TailwindCSS](https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)
[![Alpine.js](https://img.shields.io/badge/Alpine.js-8BC0D0?style=for-the-badge&logo=alpinedotjs&logoColor=black)](https://alpinejs.dev/)

<p align="center">
  A production-ready, full-stack laboratory information management system built with <b>Flask</b> and <b>MySQL 8.0</b>. MedLab automates end-to-end clinical pathology workflows — eliminating manual transcription errors, managing specimen custody with barcoding, automatically flagging abnormal biomarkers via database triggers, and accelerating pathologist verification.
</p>

---

</div>

## 📌 Overview

Clinical pathology laboratories operate under strict diagnostic deadlines and stringent accuracy requirements. Traditional workflows frequently suffer from fragmented record-keeping, transcription mistakes during result entry, untracked specimen handoffs, and communication delays between laboratory technicians and verifying pathologists.

**MedLab Diagnostics** solves these operational challenges by unifying patient management, counter billing, phlebotomy, diagnostic analysis, and medical review into a single, role-based platform.

### 🔄 End-to-End Operational Workflow

```
   ┌──────────────┐       ┌───────────────┐       ┌──────────────────────┐
   │  1. Booking  │ ────► │  2. Invoicing │ ────► │ 3. Sample Collection │
   │  & Schedule  │       │   & Payment   │       │     & Barcoding      │
   └──────────────┘       └───────────────┘       └──────────────────────┘
                                                             │
                                                             ▼
   ┌──────────────┐       ┌───────────────┐       ┌──────────────────────┐
   │  6. Release  │ ◄──── │ 5. Pathologist│ ◄──── │  4. Result Entry &   │
   │  & Freezing  │       │  Verification │       │  Automated Flagging  │
   └──────────────┘       └───────────────┘       └──────────────────────┘
```
---

## 🛠️ Technology Stack

| Domain | Technologies & Libraries | Highlights & Purpose |
| :--- | :--- | :--- |
| **Backend Core** | `Python 3.11+`, `Flask 3.0`, `Werkzeug` | Lightweight, modular WSGI application structure |
| **Database Architecture** | `MySQL 8.0`, `InnoDB Engine` | 3NF normalized schema, foreign keys, cascade safety |
| **Database Drivers** | `mysql-connector-python` | Native parameterized DB-API integration |
| **Frontend Framework** | `Jinja2`, `Tailwind CSS`, `Alpine.js` | Responsive clinical dashboard UI with reactive state |
| **Iconography & Fonts** | `Lucide Icons`, `Inter`, `JetBrains Mono` | High-legibility clinical typography and interface icons |
| **Form Management** | `Flask-WTF`, `WTForms` | Server-side validation, sanitization, CSRF token handling |
| **Authentication & RBAC** | `Flask-Login`, `PBKDF2-SHA256` | Secure session tracking, password hashing, 6 user tiers |
| **Third-Party Auth** | `Supabase Auth Client` | Google OAuth sign-in and email verification token flows |
| **Security & Hardening** | `Flask-Limiter`, HTTP Security Headers | Brute-force throttling, timing-attack defense, CSP Report-Only |

---

## ⚡ Key Features & System Architecture

### 📊 Relational Database Design (3NF)
MedLab's data model is strictly organized to **Third Normal Form (3NF)** across 17 interrelated tables, guaranteeing zero redundant non-key dependencies and rock-solid referential integrity:
- **Core Entities**: `roles`, `users`, `patient_profiles`, `staff_profiles`
- **Diagnostic Catalog**: `test_categories`, `lab_tests`, `test_parameters`, `packages`, `package_tests`
- **Clinical Lifecycle**: `bookings`, `booking_items`, `samples`, `test_results`, `time_slots`
- **Finance & Governance**: `invoices`, `notifications`, `audit_log`, `login_audit`

### 🔄 Booking State Machine
Bookings progress through an explicit, auditable seven-state lifecycle:

$$\mathbf{Booked} \longrightarrow \mathbf{Confirmed} \longrightarrow \mathbf{Sample\_Collected} \longrightarrow \mathbf{In\_Analysis} \longrightarrow \mathbf{Pending\_Verification} \longrightarrow \mathbf{Completed}$$

*(Bookings may also transition to $\mathbf{Cancelled}$ prior to sample collection).*

Every transition is strictly enforced: sample collection cannot occur before appointment confirmation, result entry requires barcoded specimens, and report publication requires explicit pathologist sign-off.

### 🛡️ Database-Enforced Business Rules & Integrity Triggers
MedLab pushes core clinical invariants directly into the database engine:
- **⚡ Automated Biomarker Flagging (`trg_calc_test_result_flag_insert`, `trg_calc_test_result_flag_update`)**: Immediately evaluates patient measurements against healthy reference ranges to determine `LOW`, `NORMAL`, or `HIGH` status and set `is_abnormal = TRUE`.
- **👑 Master Administrator Guardrail (`trg_enforce_role_creation`)**: Restricts the system to a single Master Administrator and requires administrative authority to provision clinical staff accounts.
- **🔒 Immutable Audit Trail Triggers (`trg_audit_log_prevent_update`, `trg_audit_log_prevent_delete`)**: Intercepts and blocks any `UPDATE` or `DELETE` queries on `audit_log` with an explicit SQLSTATE exception, ensuring non-repudiable audit trails.
- **❄️ Completed Result Freezing (`trg_freeze_results_completed_insert`, `trg_freeze_results_completed_update`, `trg_freeze_results_completed_delete`)**: Disallows any alteration of diagnostic values once a booking has reached `Completed` status.

### 🔔 Real-Time Notification & Polling Engine
- **Top-Bar Notification Center**: Reactive bell badge with live unread counts updated via background polling.
- **Contextual Redirection**: Clicking a notification opens the relevant clinical record (e.g., technician re-analysis alerts route directly to the specific specimen).
- **Toast Alerts**: Non-intrusive UI toasts notify users of lifecycle transitions and newly assigned work.

### 🖨️ Clinical Artifacts & Reporting
- **Specimen Tube Barcodes**: Printable barcode label strips formatted for standard specimen container tubes.
- **Standardized Diagnostic Reports**: Clean, printable pathology reports including patient demographics, laboratory references, flagged abnormal biomarkers, and pathologist digital approval.

---

## 👥 User Roles & Access Control

MedLab implements a **Role-Based Access Control (RBAC)** hierarchy with dedicated dashboards, scoped permissions, and isolated workflows:

| Role ID | Role | Portal / Workspace | Operational Responsibilities |
| :---: | :--- | :--- | :--- |
| **`1`** | **👑 Administrator** | Executive Board | System configuration, staff onboarding (technicians, receptionists, pathologists), user status toggles (suspend/reactivate), diagnostic catalog pricing, and parameter reference range maintenance. |
| **`2`** | **🏢 Receptionist** | Reception Desk | Walk-in patient registration, appointment scheduling, billing invoices, counter payment collection (Cash/Card), sample barcode generation, and booking status coordination. |
| **`3`** | **🔬 Lab Technician** | Laboratory Worklist | Specimen accessioning via barcode worklists, draft test parameter measurement entry, abnormal reading review, and submission for pathologist verification. |
| **`4`** | **👤 Patient** | Patient Portal | Self-service diagnostic catalog browsing, online appointment booking, personal booking history, real-time status tracking, and diagnostic report viewing/printing. |
| **`5`** | **💉 Sample Collector** | Phlebotomy Queue | Phlebotomy collection task queue, specimen collection timestamping, barcode verification, and specimen rejection recording with clinical rationale. |
| **`6`** | **🩺 Pathologist** | Verification Queue | Medical verification queue review, critical and abnormal result analysis, re-analysis rejection back to technicians with corrective remarks, digital sign-off, and diagnostic report release. |

---

<div align="center">
  <sub>MedLab Diagnostics &bull; Engineered for Clinical Precision & Data Integrity</sub>
</div>
