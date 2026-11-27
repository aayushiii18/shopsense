# ShopSense UAT Execution Recording Template & Sign-Off Summary

> **Current UAT Status:** **PENDING STAKEHOLDER EXECUTION**  
> All status fields, participant details, defects, ratings, and final acceptance decisions below are intentionally blank pending actual evaluation by stakeholders.

---

## 1. Test Cycle & Environment Metadata

| Field | Entry |
| :--- | :--- |
| **UAT Cycle ID** | `UAT-M4-RC1` |
| **Application Version** | `ShopSense 1.0.0` (Git Commit / Tag: `________________`) |
| **Test Environment** | `[ ] Local Host` `[ ] Staging` `[ ] Docker Compose` (API URL: `________________`) |
| **Planned / Actual Dates** | Start: `____-__-__` \| End: `____-__-__` |
| **Facilitator / QA Coordinator** | `____________________` |

### Participating Stakeholders
| Role Represented | Participant Name | Account / Email Used | Session Completed? |
| :--- | :--- | :--- | :---: |
| **Administrator** | `____________________` | `____________________` | `[ ] Yes  [ ] Pending` |
| **Vendor Partner** | `____________________` | `____________________` | `[ ] Yes  [ ] Pending` |
| **Customer / Shopper** | `____________________` | `____________________` | `[ ] Yes  [ ] Pending` |

---

## 2. Scenario Execution Log

Instructions: Mark **Status** strictly as `PASS`, `PARTIAL`, `FAIL`, or `BLOCKED` based on [uat_test_plan.md](uat_test_plan.md). Record observed behavior or Defect IDs in **Notes / Feedback**.

| Scenario ID | Role | Area | Status (`PASS / PARTIAL / FAIL / BLOCKED`) | Severity if Failed (`P0–P3`) | Tester Initials | Observed Notes / Stakeholder Feedback |
| :--- | :--- | :--- | :---: | :---: | :---: | :--- |
| **UAT-01** | Prospective Vendor | Login Gate & Vendor Application Form | `PENDING` | — | — | |
| **UAT-02** | Pending Vendor | Pending Sign-In & Role Guardrails | `PENDING` | — | — | |
| **UAT-03** | Admin | Pending Queue Review & Approval Confirm | `PENDING` | — | — | |
| **UAT-04** | Admin / Vendor | Mandatory Rejection Notes & Feedback UI | `PENDING` | — | — | |
| **UAT-05** | Approved Vendor | Store Catalog & Stock Movement Entry | `PENDING` | — | — | |
| **UAT-06** | Approved Vendor | Settlements & Cross-Tenant 403 Block | `PENDING` | — | — | |
| **UAT-07** | Admin | Executive BI KPIs & COGS Honesty Labels | `PENDING` | — | — | |
| **UAT-08** | Admin | Executive BI Filters, Granularity & Empty State | `PENDING` | — | — | |
| **UAT-09** | Admin | Demand Forecasting & Inventory Replenishment | `PENDING` | — | — | |
| **UAT-10** | Admin | Customer Analytics & PDF/Excel Exports | `PENDING` | — | — | |
| **UAT-11** | Admin | Safe Refund Terminal & Input Guards | `PENDING` | — | — | |
| **UAT-12** | Admin | ETL Reconciliation & Daily Sales Mart | `PENDING` | — | — | |
| **UAT-13** | Customer | Registration, Role Menu & Storefront Filter | `PENDING` | — | — | |
| **UAT-14** | Customer | Hybrid/CF Recommendations & Order Ledger | `PENDING` | — | — | |
| **UAT-15** | Admin / Security | System Health Diagnostics & Logout Revocation | `PENDING` | — | — | |
| **UAT-16** | All Roles | Theme Consistency, Chart Clarity & UX | `PENDING` | — | — | |

---

## 3. Defect & Observation Log

| Defect ID | Linked UAT ID | Severity (`P0/P1/P2/P3`) | Summary of Observed Issue | Owner | Resolution Status |
| :--- | :--- | :---: | :--- | :--- | :---: |
| `DEF-___` | | | *No stakeholder defects logged yet (UAT pending).* | | |

---

## 4. Stakeholder Usability & Satisfaction Survey (`1 = Strongly Disagree` to `5 = Strongly Agree`)

| Evaluation Criterion | Admin Rating (1–5) | Vendor Rating (1–5) | Customer Rating (1–5) | Mean Score (Target >= 4.0) | Comments |
| :--- | :---: | :---: | :---: | :---: | :--- |
| Portal navigation & role clarity | `__` | `__` | `__` | `__` | |
| Visual clarity & chart readability | `__` | `__` | `__` | `__` | |
| Onboarding & approval workflow ease | `__` | `__` | `N/A` | `__` | |
| Financial / COGS KPI trustworthiness | `__` | `__` | `N/A` | `__` | |
| Perceived responsiveness & error clarity | `__` | `__` | `__` | `__` | |

---

## 5. Final Acceptance Calculation & Sign-Off Summary

### Acceptance Scorecard (Complete Only After UAT Execution)
- **Total Applicable Scenarios:** `16` (or `16 - N/A`)
- **Passed (`PASS`):** `Pending`
- **Partial (`PARTIAL`):** `Pending`
- **Failed (`FAIL`):** `Pending`
- **Open Critical/Major Defects (`P0` / `P1`):** `Pending`
- **Computed Stakeholder Acceptance Rate (%):** `Pending (Target: >= 85.0%)`

### Formal Disposition
- `[ ]` **ACCEPTED** (`>= 85%` pass rate and zero open `P0`/`P1` defects)
- `[ ]` **CONDITIONALLY ACCEPTED** (Minor `P2`/`P3` polish items tracked)
- `[ ]` **REJECTED** (Blocked by `P0`/`P1` defect or `< 85%` pass rate)
- `[x]` **PENDING STAKEHOLDER TESTING**

| Stakeholder Role | Printed Name | Signature / Initials | Decision (`Approve / Hold`) | Date |
| :--- | :--- | :--- | :--- | :--- |
| **Business / Admin Stakeholder** | `____________________` | `____________` | `PENDING` | `____-__-__` |
| **Vendor Operations Representative** | `____________________` | `____________` | `PENDING` | `____-__-__` |
| **Technical Lead / Delivery Owner** | `____________________` | `____________` | `PENDING` | `____-__-__` |
