# MedLab System — Implementation Plan
**Status: PENDING USER APPROVAL**
Date: 2026-11-05

---

## PHASE 0 — Remove Sample Collector Role Entirely

This is done first because it affects every other phase. All remaining work will be built on a collector-free codebase.

### 0.1 — Database Migration (SQL)
Run a migration script that does the following, in order:

1. **Reassign existing collector user** (MUHAMMAD ESSA, role 5) to role `receptionist` (role_id = 2), so the account is not orphaned. His 32 collected samples in the `samples` table have `collected_by` pointing to him — these stay intact (historical data). We just change his role.
2. **Update `vw_staff_directory`** view — remove `role_id IN (2,3,5,6)` → change to `role_id IN (2,3,6)`.
3. **Update `vw_technician_worklist`** view — no changes needed (already works with the technician as collector, no role_id filter inside).
4. **Update `trg_enforce_role_creation`** trigger — remove the check for `role_id IN (2,3)` and replace with `role_id IN (2,3,6)` (staff roles that require admin creation). Remove any role 5 references.
5. **Update `time_slots`** `max_capacity` default from 20 to 10 (for new slots; existing slots updated via SQL).
6. **Keep the `roles` table row for role_id=5** to avoid FK constraint issues (historical samples). We just stop using it in the application.

### 0.2 — Remove Collector Backend Files
- Delete `routes/collector.py` entirely.
- Remove registration of `collector_bp` from `app.py`.
- Update `ROLE_REDIRECTS` dict in `auth.py` — remove entry `5: "collector.dashboard"`.
- Update `models.py` — remove `is_collector` property (or keep silently, it won't be used).

### 0.3 — Remove Collector Frontend Templates
- Delete `templates/collector/` folder and all its contents.

### 0.4 — Update Navigation & References
- Update `templates/base.html` — remove any sidebar link that leads to `/collector/...`.
- Update `templates/landing.html` — remove "Home Collection / Home Visit" feature mention.
- Update `templates/notifications/detail.html` — remove `role 5: collector.dashboard` from `role_map`.
- Update `routes/notifications.py` — remove `5: url_for("collector.dashboard")` from role_map.

---

## PHASE 1 — Walk-In Booking: Add New Customer Inline

### Problem
Currently, receptionist walk-in form only allows selecting from existing patient users. If a new patient walks in, the receptionist cannot create their account on the spot.

### Solution

**Backend (`routes/receptionist.py` — `walk_in` route):**
- Add a `patient_mode` field (values: `existing` or `new`) read from the POST body.
- If `patient_mode == "new"`:
  - Read `new_full_name`, `new_phone`, `new_email`, `new_gender`, `new_dob` from the form.
  - Validate: check that email and phone don't already exist in `users`.
  - Create a new user with `role_id=4` (patient), `auth_provider='local'`, a random secure temporary password, and `email_verified=1` (since receptionist is verifying in-person).
  - Insert a row into `patient_profiles` with gender/dob if provided.
  - Use this new `user_id` as the `patient_id` for the booking.
  - Fire a notification to Admin about the new walk-in patient registration.
- If `patient_mode == "existing"`: keep existing behavior.

**Frontend (`templates/receptionist/walk_in.html`):**
- Add a toggle/radio: **"Select Existing Patient"** vs **"Register New Patient"**.
- When "Register New Patient" is selected (via Alpine.js), show a small inline form:
  - Full Name (required)
  - Phone Number (required)
  - Email (required)
  - Date of Birth (optional)
  - Gender (optional dropdown)
- When "Select Existing Patient" is selected, show the existing dropdown.

---

## PHASE 2 — Admin Panel: User Management Panel

### Problem
Admin can only manage staff. There is no way to view or manage regular patient users (role_id=4).

### Solution

**Backend (`routes/admin.py`):**
- Add new route `/admin/users` (GET) — lists all patient users with: name, email, phone, registration date, total bookings, is_active status.
- Add new route `/admin/users/<user_id>/toggle` (POST) — toggles `is_active` for patient accounts.
- Add new route `/admin/users/<user_id>` (GET) — detail view showing patient profile, booking history, total invoiced amount.

**Frontend:**
- Create `templates/admin/users.html` — a table page showing all patients with search, status badges, and a "Suspend/Reactivate" action button.
- Add a **"Users"** link to the Admin sidebar in `templates/base.html`.

---

## PHASE 3 — Admin Staff Panel: Fix Role Display Bug

### Problem
In the staff list table, a Pathologist/Doctor shows as "Lab Technician" because the view `vw_staff_directory` is correct but the template hardcodes a label instead of reading `role_name` from the database.

### Solution
**Frontend (`templates/admin/staff.html`):**
- Replace any hardcoded role label (e.g., `"Lab Technician"`) in the staff table with `{{ member.role_name | title }}` or a mapping dict that correctly maps role names:
  - `admin` → Admin
  - `receptionist` → Receptionist
  - `technician` → Lab Technician
  - `pathologist` → Pathologist / Doctor
- Also fix the "Add Staff" tab UI — the tabs should correctly show Receptionist, Lab Technician, and Pathologist (removing any Collector tab).

---

## PHASE 4 — Test Pricing Edit & Availability in Admin Catalog

### Problem
Admin can toggle test on/off but cannot edit the price. Patients/receptionists don't see slot availability.

### Solution

**Backend (`routes/admin.py`):**
- Add route `/admin/catalog/update-test/<test_id>` (POST) — receives `price` (and optionally `turnaround_hours`, `pre_test_instructions`) and updates `lab_tests` accordingly.

**Frontend (`templates/admin/catalog.html`):**
- In each test card row, add an **"Edit Price"** button that opens an inline modal/form.
- The form has a price input (pre-filled with current price) and a Save button that POSTs to the update route.

---

## PHASE 5 — Slot Capacity: 10 Per Test Per Slot (Patient & Receptionist Booking)

### Problem
No capacity enforcement exists. Users should see "Available" or "Unavailable" but NOT the internal count.

### Solution

**Database:**
- Update all existing `time_slots` rows: `UPDATE time_slots SET max_capacity = 10`.
- Note: `time_slots.booked_count` already exists and tracks capacity.
- However, the current booking flow doesn't insert/update `time_slots` at all — bookings are created without touching the slot table. We need to fix this.

**Backend (`routes/patient.py` — `book_test` and `routes/receptionist.py` — `walk_in`):**
- When a booking is submitted:
  1. Find or create the `time_slots` row for `(appointment_date, appointment_slot)`.
  2. Check `booked_count < max_capacity`. If full, reject with a clear message.
  3. If ok: `UPDATE time_slots SET booked_count = booked_count + 1 WHERE slot_id = ...` atomically inside the same transaction.
- Add a new API endpoint (or inline into the booking page data) that returns slot availability for a given date.

**Frontend (`templates/patient/book_test.html` and `templates/receptionist/walk_in.html`):**
- After the user picks a date, the slot selector dynamically shows each time window as:
  - ✅ **Available** (green) — slot has capacity
  - ❌ **Unavailable** (grey/red) — slot is full; radio button disabled
- Internal count numbers are NEVER shown to the user.

---

## PHASE 6 — Test Selection UI: Reduce Scrolling with Compact Accordion

### Problem
Both patient booking and receptionist walk-in show a full scrolling list of tests that is very long.

### Solution

**Frontend (both `templates/patient/book_test.html` and `templates/receptionist/walk_in.html`):**
- Replace the long flat scrolling list with a **compact category accordion** (tabs or collapsible sections):
  - By default, all categories are collapsed. User clicks a category name to expand and see only tests within that category.
  - Each category shows a small badge: "3 tests" or "5 tests".
  - A live search box at the top lets users type a test name and auto-expands matching categories.
- Selected tests show in a compact sticky summary box on the right side (or bottom on mobile) showing count and total PKR.
- This reduces page height from ~2000px to ~300px before any expansion.

---

## PHASE 7 — Workflow Fix: Move Sample Collection to Lab Technician

### Problem
"Sample Collected" button is on the Receptionist booking detail page — it doesn't belong there and doesn't fire notifications properly.

### Solution

**Backend changes:**
- **Remove** the `collect_sample` route from `routes/receptionist.py` and its URL endpoint.
- **Remove** the "Mark Sample Collected" button from `templates/receptionist/booking_detail.html`.
- **Add** a new "Confirm Sample Received" action to `routes/technician.py`:
  - New route `/technician/booking/<booking_id>/confirm-sample` (POST).
  - This does what `collect_sample` used to do: inserts a row into `samples`, generates a barcode, updates `booking_items.item_status = 'Sample_Collected'`, updates `booking_status = 'Sample_Collected'`.
  - Fires a notification to Admin and Receptionist: "Sample for booking BK-XXXX confirmed received by Lab Technician."

**Frontend:**
- Update `templates/technician/dashboard.html` to show **all bookings in `Booked` or `Confirmed` status** (not just those already in `vw_technician_worklist` which requires a sample to exist).
- The technician dashboard will have TWO sections:
  1. **"Awaiting Sample Confirmation"** — bookings that are `Booked` and have no sample yet. Technician clicks "Confirm Sample Received" here.
  2. **"Enter Results"** — the existing worklist from `vw_technician_worklist` (bookings with collected samples awaiting measurement entry).

---

## PHASE 8 — Fix Booking Notifications & Technician Visibility

### Problem
- After a patient books a test, no notification fires for Receptionist/Admin/Technician.
- The booking never appears in the technician panel because `vw_technician_worklist` requires a `samples` row to exist first — which it doesn't until someone collects it.

### Solution

**Backend (`routes/patient.py` — `book_test`):**
After the booking + invoice are committed, add:
```python
# Notify Admin and Receptionist about new booking
INSERT INTO notifications (user_id, type, title, message, booking_id)
SELECT user_id, 'booking', 'New Patient Booking', '...', {booking_id}
FROM users WHERE role_id IN (1, 2) AND is_active = 1

# Notify all active Technicians too
INSERT INTO notifications (user_id, type, title, message, booking_id)
SELECT user_id, 'booking', 'New Test Booking', '...', {booking_id}
FROM users WHERE role_id = 3 AND is_active = 1
```

Same for walk-in bookings in `routes/receptionist.py`.

**Technician Visibility Fix (covered in Phase 7 above):** The technician dashboard will query bookings directly (not through the view that requires a sample) so newly booked tests appear immediately.

---

## PHASE 9 — Notification Read State Fix

### Problem
Notifications don't clear when the panel is opened. Count stays at 15 even after viewing.

### Solution

**Backend (`routes/notifications.py`):**
- Add a new POST endpoint `/notifications/mark-panel-read` — called automatically when the notification dropdown is opened. Marks all current unread notifications as read.

**Frontend (`templates/base.html` — notification bell dropdown):**
- Add an `x-init` or `@click` Alpine.js handler on the notification bell that fires a lightweight `fetch('/notifications/mark-panel-read', {method:'POST'})` call when the dropdown opens.
- After marking as read, the badge count resets to 0.
- Future new notifications (arriving after the panel was opened) will re-trigger the counter.

---

## PHASE 10 — Lab Technician Management Panel

### Problem
Lab technician has no "Manage" view to track the full process for a booking.

### Solution

**Backend (`routes/technician.py`):**
- Add route `/technician/booking/<booking_id>` (GET) — shows a compact detail panel for a booking:
  - Patient name, phone, booking reference.
  - Each test item, its status, and barcode (if collected).
  - Current booking status with a visual progress indicator.
  - Action buttons based on status:
    - `Booked` → "Confirm Sample Received" button.
    - `Sample_Collected` → "Enter Results" link.
    - `In_Analysis` → "Continue Results Entry" link.
    - `Pending_Verification` → Read-only "Awaiting Pathologist".

**Frontend (`templates/technician/manage.html`):**
- Create a new compact manage page linked from both sections of the technician dashboard.

---

## PHASE 11 — Landing Page Cleanup

**Frontend (`templates/landing.html`):**
- Remove all references to "Home Collection", "Home Visit", "Home Sample Pickup", "Phlebotomist visit", or similar text.
- Remove the sample_collector feature card/section if one exists.
- Keep all other sections intact (test catalog, packages, appointment booking CTA).

---

## Summary Table

| Phase | Area | Type | Difficulty |
| :--- | :--- | :--- | :--- |
| 0 | Remove Sample Collector | DB + Backend + Frontend | High |
| 1 | Walk-In New Patient Registration | Backend + Frontend | Medium |
| 2 | Admin User Management Panel | Backend + Frontend | Medium |
| 3 | Staff Role Display Bug | Frontend only | Low |
| 4 | Test Price Edit in Admin | Backend + Frontend | Low |
| 5 | Slot Capacity (10 per slot) | DB + Backend + Frontend | Medium |
| 6 | Test Selection Compact Accordion UI | Frontend only | Medium |
| 7 | Move Sample Collection to Technician | Backend + Frontend | High |
| 8 | Booking Notifications & Visibility | Backend only | Medium |
| 9 | Notification Read State Fix | Backend + Frontend | Low |
| 10 | Technician Manage Panel | Backend + Frontend | Medium |
| 11 | Landing Page Cleanup | Frontend only | Low |

---

## Execution Order

Phases will be implemented in this order to avoid regressions:

**0 → 7 → 8 → 3 → 1 → 2 → 4 → 5 → 6 → 9 → 10 → 11**

Rationale:
- Phase 0 (remove collector) must come first — it changes auth flow, routes, and DB.
- Phase 7 (workflow fix) depends on Phase 0 being done.
- Phase 8 (notifications) depends on Phase 7's new booking flow.
- All UI phases come after the backend is stabilized.

---

## What Will NOT Be Changed
- Database schema for `roles` table row `role_id=5` (kept for historical FK integrity on `samples.collected_by`).
- All existing patient bookings and their data.
- Test catalog data, pricing data, and all existing invoices.
- Login credentials and password hashing.
- The visual design system (green clinical theme, Tailwind, Lucide icons).

