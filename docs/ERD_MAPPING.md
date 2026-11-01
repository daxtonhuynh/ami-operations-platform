# From the simplified logical model to the physical database

The *Simplified Logical Data Model* (communication diagram: 5 areas, 25 entities, 3 logic chains) is implemented by the
93-table PostgreSQL model in [`database/`](../database). The physical model is larger because it keeps history (dated prices,
rates and roles), splits money into its parts (charges, schedule lines, allocations) and adds what the application needs
(approvals, controls, audit, sign-in). Every logical entity still has one clear home.

## Entity by entity

| Logical entity | Physical table(s) / view | Notes |
|---|---|---|
| **Customer & sales** | | |
| students | `crm.student` | One row per learner for life (`AMIxxxx`). Grade, school, date of birth. |
| guardians | `crm.guardian` + `crm.student_guardian` | Many-to-many: siblings share a parent; one guardian is the payer. |
| leads | `crm.lead` (+ `lead_activity`, `lead_stage_history`, `placement_test`, `placement_test_score`) | `advisor_id` = `owner_employee_id`; status = stage + qualification + outcome + lost reason. |
| enrollments | `billing.enrollment` (+ `enrollment_discount`, `enrollment_charge`, `enrollment_status_history`) | `tuition_fee` and `discount_amount` are not typed: list price, discounts and materials fee are charge lines, summed in `rpt.v_enrollment_pricing`. |
| receipts | `billing.receipt` + `billing.payment_allocation` + `billing.payment_schedule` | A receipt is applied to instalments oldest-first (`billing.record_receipt`); voids keep the row. |
| **Academic operations** | | |
| programs | `ref.programme` | AE, COMM, IELTS, PE. |
| courses | `ref.course` (+ `ref.course_price`, dated) | `planned_sessions` = standard hours / hours per session. |
| class_cohorts | `academic.class` (+ `class_meeting_pattern`, `class_staff_assignment`) | `teacher_id` / `ta_id` become dated assignments, so a teacher can be replaced mid-course. |
| class_sessions | `academic.class_session` (+ `academic.closure_day`) | Generated from the timetable, skipping public holidays and Tet. |
| class_rosters | `rpt.v_class_roster` (a **view**) | Logic chain 1 made literal: the roster is derived from enrolments, never typed. `assigned_by` = `enrollment.class_assigned_by`. |
| **Payroll & HR** | | |
| staff | `hr.employee` | |
| staff_roles | `hr.employee_role` (+ `ref.staff_role`, `ref.salary_code`, `ref.salary_rate`, `hr.employee_rate_override`, `hr.employee_fixed_pay`) | Dated HR codes: one person can teach IELTS and manage the academic team at different rates. |
| work_logs | `academic.session_staff` (teaching hours) + `hr.work_shift` (advisor shifts) | Teaching hours exist only when the Academic Manager confirms a delivered session. |
| payroll_lines | `payroll.payroll_line` (+ `payroll.commission`, `payroll.commission_rule`) | `component_type` = earning type; `category_code` = GL account resolved by role, programme and delivery mode. |
| payroll_runs | `payroll.payroll_run` + `payroll.payslip` (+ `payslip_deduction`, `pit_rule`) | DRAFT → CALCULATED → APPROVED (HR) → PAID (Finance). |
| **Expenses management** | | |
| vendors | `finance.vendor` | |
| expense_categories | `finance.gl_account` | The workbook's expense codes (E1.xxx … E8.xxx), with a capex flag. |
| cost_centers | `finance.cost_center` | Academic / non-academic scope decides the P&L line of shared accounts. |
| expenses | `finance.payment_voucher` + `payment_voucher_line` (+ `expense_claim`, `fixed_asset`, `depreciation_schedule`, `journal_entry`) | `recognition_date` = the line's cost month; capex is depreciated, not expensed. |
| **Financial reporting** | | |
| revenue_recognitions | `billing.revenue_schedule` | One row per enrolment, month and line type (tuition, materials, forfeit). Service-period allocation of the contract, not of the cash. |
| deferred_revenue | `rpt.v_enrollment_revenue_position` (per enrolment) and `rpt.v_deferred_revenue` (per month) | *Deferred = cash received − revenue recognised*, computed, never stored. |
| cash_pl | `rpt.v_pnl_summary` where `basis = 'CASH'` | Receipts by collection month, refunds, costs. |
| accrual_pl | `rpt.v_pnl_summary` where `basis = 'ACCRUAL'` | Revenue schedule, write-offs, accruals, costs. Both bases come from one ledger view, `rpt.v_pnl_ledger` - nothing is counted twice (BR-08). |

## The three logic chains

| Chain | In the database | In the application |
|---|---|---|
| **1 · Class opening & enrolment**: courses → class_cohorts → enrollments → class_rosters | `academic.open_class()` creates the class, timetable, staff and sessions; `billing.enrol()` prices and schedules the enrolment; `rpt.v_class_roster` lists it | Academic Manager → *Open a class*; Learning Advisor → *New enrolment*; both → *Classes & rosters* |
| **2 · Weekly work & payroll**: class_cohorts / sessions → work_logs → payroll_lines → payroll_runs | `academic.confirm_session()` writes the hours; `payroll.calculate_run()` turns hours, shifts, fixed pay, commission and allowances into lines and payslips; `payroll.approve_run()` refuses while sessions are unconfirmed | Academic Manager → *Confirm sessions*; HR Manager → *Advisor shifts*, *Payroll runs* |
| **3 · Financial consolidation**: receipts → cash_pl, revenue_recognitions → accrual_pl, → deferred_revenue | `billing.build_revenue_schedule()` on every life-cycle event; `rpt.v_pnl_ledger` → `v_pnl_by_line` → `v_pnl_summary`; `rpt.v_deferred_revenue`; `finance.close_period()` | Finance Manager → *P&L: cash vs accrual*, *Revenue & deferred*, *Month-end close* |

## Added beyond the logical model

| Need | Tables |
|---|---|
| Who may do what, sign-in | `app.app_user` + database roles (`06_security.sql`) |
| Who did what (BR-12) | `app.audit_log` |
| Cash handled by staff | `app.cash_close` |
| Problems as a work queue (BR-11) | `ctl.control`, `ctl.control_run`, `ctl.control_exception` |
| Month-end lock | `finance.fiscal_period` |
| Business settings | `ref.app_setting` (approval threshold, drop-out policy, business date …) |
