# MedLab Diagnostics

## Overview

MedLab Diagnostics is a web-based clinical laboratory management system designed to streamline diagnostic workflows, enforce clinical data integrity, and eliminate manual errors in pathology operations. Diagnostic laboratories frequently struggle with fragmented record-keeping, transcription mistakes during result entry, untracked specimen handoffs, and delays between verification and patient delivery. MedLab addresses these operational bottlenecks by providing an integrated, role-based platform that unifies patient management, appointment scheduling, phlebotomy tracking, laboratory analysis, and pathologist verification.

The end-to-end operational workflow proceeds through the following stages:

1. **Booking & Scheduling**: A patient schedules an appointment online through the test catalog or a receptionist registers a walk-in patient, selecting required tests or test packages and assigning an available date and time slot.
2. **Invoicing & Payment**: An invoice is generated for the booking. Payments are recorded at the reception counter (Cash or Card) or marked for online processing, updating billing records.
3. **Sample Collection & Barcoding**: A sample collector or receptionist collects the required specimen (e.g., EDTA blood, serum, urine, swab). The system generates a unique barcode identifier (`SMP-...`) and attaches it to the specimen tube for custody tracking.
4. **Result Entry & Processing**: A laboratory technician retrieves the barcoded specimen in the worklist, records individual parameter readings, and submits draft results.
5. **Automated Clinical Flagging**: Database triggers evaluate measured biomarker values against defined biological reference ranges (`min_range` and `max_range`) in real time, automatically setting `LOW`, `NORMAL`, or `HIGH` flags and identifying abnormal values.
6. **Pathologist Verification**: A pathologist inspects flagged results, reviews abnormal parameters, and either approves the findings or returns them to the technician with clinical notes for re-analysis.
7. **Report Release**: Upon pathologist approval, the booking transitions to completed status, digital signatures are applied, results are permanently frozen against modification, and the patient receives real-time notification with access to view and print the diagnostic report.

## Technology Stack

| Layer | Technologies & Tools |
| :--- | :--- |
| **Backend** | Flask 3, Flask-Login, Flask-WTF / CSRFProtect, Flask-Limiter, WTForms, Werkzeug |
| **Database** | MySQL 8, InnoDB storage engine, 3NF normalized schema, triggers, views, stored procedures, `mysql-connector-python` |
| **Frontend** | Jinja2 templates, Tailwind CSS, Alpine.js, Lucide icons, Inter and JetBrains Mono typography |
| **Authentication** | Flask-Login session management, PBKDF2-SHA256 password hashing, Supabase authentication (Google OAuth sign-in and email verification) |
| **Security** | CSRF protection, endpoint rate limiting, HTTP security headers (`nosniff`, `DENY` clickjacking protection, Referrer-Policy, CSP Report-Only), parameterized SQL queries, magic-byte image upload validation, immutable audit log triggers |

## Description

MedLab Diagnostics is structured around a modular, blueprint-driven architecture backed by a relational database schema designed to Third Normal Form (3NF).
 
 ### Booking State Machine
Bookings progress through an explicit seven-state lifecycle:
`Booked` $\to$ `Confirmed` $\to$ `Sample_Collected` $\to$ `In_Analysis` $\to$ `Pending_Verification` $\to$ `Completed` (or `Cancelled`). State transitions are gated by business rules, ensuring specimen collection cannot precede appointment confirmation, result entry requires barcoded specimens, and report publication requires explicit pathologist sign-off.

### Database-Enforced Business Rules & Security Triggers
- **Biomarker Flag Triggers (`trg_calc_test_result_flag_insert`, `trg_calc_test_result_flag_update`)**: Automatically compute biomarker flag statuses (`LOW`, `NORMAL`, `HIGH`) and toggle the `is_abnormal` boolean flag by checking measured values against `min_range` and `max_range` in `test_parameters`.
- **Role Provisioning Guardrail (`trg_enforce_role_creation`)**: Restricts system architecture to a single Master Administrator and requires that all administrative and laboratory staff accounts be provisioned by the Admin.
- **Audit Log Immutability Triggers (`trg_audit_log_prevent_update`, `trg_audit_log_prevent_delete`)**: Intercept and abort any `UPDATE` or `DELETE` statement directed at `audit_log` with an explicit SQLSTATE exception, ensuring tamper-evident audit records.
- **Completed Result Freeze Triggers (`trg_freeze_results_completed_insert`, `trg_freeze_results_completed_update`, `trg_freeze_results_completed_delete`)**: Prevent insertion, modification, or deletion of test result records once the parent booking has reached `Completed` status.

 
### Notifications & Printable Reports
The system features an in-app notification engine with polling badge indicators and event tracking across every lifecycle transition. Clinical documents—including barcode label strips for specimen tubes and standardized diagnostic reports with reference ranges, patient demographics, abnormal indicator flags, and pathologist verifications—are generated as clean, printable outputs.

## User Roles

| Role ID | Role Name | System Access & Responsibilities |
| :---: | :--- | :--- |
| **1** | **Admin** | System administration, staff onboarding (receptionists, technicians, pathologists), user status management (suspend/reactivate), diagnostic catalog pricing, and parameter configuration. |
| **2** | **Receptionist** | Walk-in patient registration, appointment scheduling, billing and invoice payment recording, sample barcode generation, and booking status coordination. |
| **3** | **Lab Technician** | Specimen accessioning via barcode worklists, draft test parameter measurement entry, abnormal reading review, and submission for pathologist verification. |
| **4** | **Patient** | Self-service diagnostic catalog browsing, online appointment booking, personal booking history, real-time status tracking, and diagnostic report viewing/printing. |
| **5** | **Sample Collector** | Phlebotomy collection task queue, specimen collection timestamping, barcode verification, and specimen rejection recording with clinical rationale. |
| **6** | **Pathologist** | Medical verification queue review, critical and abnormal result analysis, re-analysis rejection back to technicians with corrective remarks, digital sign-off, and diagnostic report release. |
