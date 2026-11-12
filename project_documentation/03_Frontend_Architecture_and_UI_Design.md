# MedLab Management System — Document 3: Frontend Architecture & UI Design

---

## 1. Frontend Philosophy: Modern, Fast & Build-Free

The frontend of MedLab is engineered around the principle of **High-Performance Simplicity**. 

Rather than adopting complex single-page application (SPA) frameworks (like React, Angular, or Vue) that require Node.js, Webpack/Vite bundlers, and massive `node_modules` dependencies, MedLab implements a modern **Server-Rendered Architecture with Islands of Client-Side Reactivity**.

### Core Stack
1. **HTML5 & Jinja2**: Server-side template rendering with modular inheritance.
2. **Tailwind CSS**: Utility-first CSS engine loaded via CDN for rapid, consistent layout styling.
3. **Custom Clinical Theme (`static/css/custom.css`)**: Medical design system with standardized cards, tables, badges, and print stylesheets.
4. **Alpine.js**: Ultra-lightweight reactive JavaScript engine for dynamic interactivity (live filtering, calculators, dropdowns).
5. **Lucide Icons**: SVG icon library providing sharp medical, laboratory, and navigation glyphs.

```
┌────────────────────────────────────────────────────────────────────────┐
│                              base.html                                 │
│  ┌───────────────────────┬──────────────────────────────────────────┐  │
│  │   Sidebar Navigation  │            Topbar Header                 │  │
│  │   • Role-specific nav │   • Title & Subtitle   • User Avatar     │  │
│  │   • Brand badge       │   • Notification Bell  • Quick actions   │  │
│  ├───────────────────────┴──────────────────────────────────────────┤  │
│  │                     Flash Messages Alert Area                    │  │
│  ├──────────────────────────────────────────────────────────────────┤  │
│  │                   {% block content %} ...                        │  │
│  │             (Injected Role Dashboard / Form / Report)            │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Design System & Brand Palette

The user interface implements an authentic, clinical-grade color palette designed for high legibility, trust, and diagnostic clarity:

### Color Palette
* **Primary Emerald (`#166534`, `#15803D`, `#DCFCE7`)**: Represents clinical precision, health, and verified status. Used on primary buttons, verified badges, active links, and report headers.
* **Neutral Slate (`#0F172A`, `#334155`, `#64748B`, `#F8FAFC`)**: Used for high-contrast typography, subtle borders (`#E2E8F0`), card backgrounds, and secondary metadata.
* **Amber Warning (`#D97706`, `#FEF3C7`)**: Indicates pending operations (`Sample_Collected`, `Pending_Verification`, unpaid bills).
* **Rose / Red Alert (`#DC2626`, `#FEE2E2`)**: Explicitly reserved for abnormal clinical values (`HIGH`, `LOW` flags), rejected specimens, or cancelled bookings.

### Custom Component Classes (`static/css/custom.css`)
* `.card` & `.card-header`: Standardized medical information containers with soft rounded corners, crisp 1px borders, and clean title headers.
* `.btn`, `.btn-primary`, `.btn-outline`, `.btn-ghost`: Ergonomic button styles with smooth hover transitions.
* `.badge`: Visual status pills (`.badge-green`, `.badge-amber`, `.badge-red`, `.badge-slate`).
* `.table-wrap`: Horizontally scrolling, responsive table containers with fixed header support and hover row highlights.
* `.status-steps`: 5-node visual progress bar showing a booking's path from reservation to final sign-off.
* `@media print`: Specialized CSS styles that hide navigation bars, topbars, buttons, and backgrounds during physical printing, formatting reports directly for A4 paper.

---

## 3. Reactive Client-Side Interactivity with Alpine.js

Alpine.js provides reactivity directly within the HTML without overhead. Key patterns implemented across MedLab include:

### 1. Zero-Leak Table Filtering Pattern
To prevent JavaScript code from leaking into the HTML when handling large server datasets, MedLab uses a strict separation pattern:
* Data is rendered into an isolated JSON script block:
  ```html
  <script id="recent-bookings-json" type="application/json">
    [ {{ bookings | tojson }} ]
  </script>
  ```
* Alpine.js initializes from a clean JavaScript function:
  ```javascript
  function recentBookingsData() {
    var raw = JSON.parse(document.getElementById('recent-bookings-json').textContent);
    return {
      expanded: false,
      search: '',
      bookings: raw,
      get filtered() {
        var q = this.search.toLowerCase().trim();
        return this.bookings.filter(b => b.ref.toLowerCase().includes(q));
      }
    };
  }
  ```
* The HTML card binds cleanly: `<div class="card" x-data="recentBookingsData()">`. This guarantees 100% clean rendering with zero stray code on screen.

### 2. Real-Time Price & Test Selection Calculator
On walk-in registration (`templates/receptionist/walk_in.html`) and patient booking (`templates/patient/book_test.html`), Alpine.js maintains an array of selected test IDs and dynamically computes the total price:
* Checking a test checkbox pushes the ID to `selected` and adds the test price to `total`.
* Unchecking automatically removes the ID and deducts the price.
* Total amount in PKR updates instantaneously on screen without requiring a round-trip server reload.

### 3. Password Strength Validator
On user signup and profile password changes (`templates/auth/signup.html`), Alpine.js checks password rules in real time (length >= 8, uppercase letter, lowercase letter, digit, special character), displaying checkmarks dynamically as the user types.

---

## 4. Template Architecture (`templates/` Directory)

The application templates are structured hierarchically:

```
templates/
├── base.html                  # Master root layout with sidebar and topbar
├── landing.html               # Public catalog & marketing landing page
├── admin/                     # System administrator views
│   ├── dashboard.html         # Revenue analytics & recent bookings
│   ├── catalog.html           # Diagnostic test catalog manager
│   └── staff.html             # Staff onboarding & directory
├── receptionist/              # Front-desk counter views
│   ├── dashboard.html         # Today's queue & quick check-in
│   ├── walk_in.html           # Walk-in registration & test selector
│   ├── tests.html             # Test lookup & preparation guides
│   ├── booking_detail.html    # Invoice generation & payment collection
│   └── barcode_print.html     # Specimen vial barcode labels
├── collector/                 # Phlebotomy views
│   └── dashboard.html         # Home visits & in-lab collection queue
├── technician/                # Lab technologist views
│   ├── dashboard.html         # Pending specimen worklist
│   ├── enter_results.html     # Biomarker parameter entry screen
│   └── report_print.html      # Internal lab worksheet
├── pathologist/               # Doctor verification views
│   ├── dashboard.html         # Review queue & sign-off counter
│   └── review.html            # Medical approval & revision comments
├── patient/                   # Patient portal views
│   ├── dashboard.html         # Active bookings & report ready notices
│   ├── book_test.html         # Online appointment booking & slot picker
│   ├── booking_detail.html    # Booking status tracker & timeline
│   ├── reports.html           # Released reports archive
│   └── report_view.html       # Official clinical diagnostic report
├── auth/                      # Authentication views
│   ├── login.html             # Role login form
│   ├── signup.html            # Patient self-registration
│   ├── profile.html           # Account settings & avatar upload
│   └── change_password.html   # Password update form
├── notifications/             # Notification center
│   ├── index.html             # All user alerts
│   └── detail.html            # Single notification view
└── errors/                    # Custom error pages
    ├── 403.html               # Unauthorized access forbidden
    ├── 404.html               # Page not found
    └── 500.html               # Internal server error
```

---

## 5. Official Diagnostic Report Presentation

When a patient views or prints a completed report (`templates/patient/report_view.html`), the layout mirrors an accredited physical laboratory report:
1. **Hospital Header**: Laboratory name, accreditation details, contact phone, and logo.
2. **Patient Demographics Box**: Patient Name, Age/Gender, Patient Phone, Booking Reference, Collection Date, and Report Date.
3. **Biomarker Results Table**:
   * **Test Parameter Name** (e.g., Hemoglobin, Fasting Glucose).
   * **Observed Value** (bolded for clarity).
   * **Flag Indicator**: Highlighted in red (`HIGH` or `LOW`) if outside reference bounds.
   * **Reference Normal Range** (e.g., `13.00 - 17.00`).
   * **Units of Measurement** (e.g., `g/dL`, `mg/dL`).
4. **Pathologist Clinical Remarks**: Medical observations written by the pathologist.
5. **Digital Signature & Stamp**: Name of the Consultant Pathologist, verification timestamp, and official sign-off badge.

