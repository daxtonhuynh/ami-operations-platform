# Business rules: where each one is enforced, shown and tested

The *Master System Logic Specification* lists twelve rules for Phase 2 (BR-01 … BR-12). This table traces each one to the database
object that enforces it, the screen where people meet it, and the test that proves it.

| Rule | Enforced in the database | Seen in the application | Tests |
|---|---|---|---|
| **BR-01 Class identity** - unique class code referencing a valid course | `academic.class.class_code` UNIQUE + pattern check; FK to `ref.course`; `academic.make_class_code()` builds `<PROGRAMME>_<COURSE>_<DDMMYY>`; composite FK `enrollment(class_id, course_id)` | *Open a class* shows the code before saving | T09, app test `open_class` page |
| **BR-02 Enrolment integrity** - no duplicate active enrolment of a learner in a class | FKs to `crm.student` and `academic.class`; partial unique index `enrollment_one_active_per_class`; capacity check in `billing.enrol()` / `assign_class()` | *New enrolment* refuses with a plain message | T34, T39 |
| **BR-03 Roster consistency** - roster = active enrolments, respecting cancellations and transfers | The roster is a view, `rpt.v_class_roster`; `billing.change_enrollment_status()` and `assign_class()` move learners; `academic.cancel_class()` returns them to the waiting list; control ACA-01 (capacity) | *Classes & rosters* → Roster tab | T24, T43-T45 |
| **BR-04 Tuition arithmetic** - net tuition from base fee, approved discounts and charges | `billing.price_enrollment()` (list price snapshot, discounts as rows, group discount, materials fee, adjustments); at most three discounts; approval workflow `billing.decide_discount()` with threshold setting; controls BIL-01, BIL-02, BIL-05 | *New enrolment* preview; *Approvals* → Discounts; *Prices & settings* | T03-T06, T16, T17, T35-T38 |
| **BR-05 Receipt integrity** - unique reference, no over-allocation, explicit refund/reversal rules | `receipt_no` UNIQUE (`PTxxxx`, numbered by `record_receipt()`); constraint trigger `billing.check_allocation`; receipts never edited (grants), voided only through `request_receipt_void` / `decide_receipt_void` (Finance, open months only); `billing.record_refund()`; daily `app.close_cash()`; controls BIL-04, BIL-09 | *Students & balances* (take a payment, PDF receipt); *Receipt register* (request void); *Approvals*; *Daily cash close* | T18-T23, T40-T42, T49-T51, T62 |
| **BR-06 Accounts receivable** - unpaid = contract due − allocated receipts/credits; overdue by instalment due dates | `rpt.v_schedule_line_status` (ageing per instalment), `rpt.v_enrollment_balance` (amount owed after drop-outs, credits, write-offs); `billing.write_off_balance()`; controls BIL-03, BIL-06, BIL-08 | Advisor *My day* (collections); *Receivables & collections* (ageing, write-offs, refunds) | T21, T41, T46-T48 |
| **BR-07 Role-specific compensation** - the role/rate valid for the work period | dated `hr.employee_role`, `ref.salary_rate`, `hr.employee_rate_override` (exclusion constraints); `payroll.hourly_rate(role, date)`; hours only from confirmed sessions / shifts; `payroll.commission_rule`; controls PAY-01..03, ACA-02 | *Pay rates*; *Staff & HR codes*; *Confirm sessions*; *Payroll runs* (register, payslip PDF) | T10-T12, T30-T32b, T56, T57 |
| **BR-08 No double counting** - payroll in the P&L once | One ledger, `rpt.v_pnl_ledger`: payroll lines come only from payroll runs; vouchers carry no payroll; refund vouchers carry no lines (the refund itself is posted once) | *P&L: cash vs accrual* → "where the two bases differ" | T27, T28 |
| **BR-09 Period integrity** - cash by collection period, accrual by service period | Cash basis from receipt dates, accrual basis from `billing.revenue_schedule` (service months); `finance.close_period()` (in order, after payroll approval); trigger `finance.assert_period_open` on every dated financial table | *P&L* (basis switch); *Month-end close* checklist | T13, T20, T27, T54-T58 |
| **BR-10 Revenue completeness** - recognised revenue over the service period = tuition after adjustments | `billing.build_revenue_schedule()` (contract spread, drop-out share, forfeits, closed months final); control REP-01 | *Revenue & deferred* (per enrolment schedule) | T20, T25, T26, T43, T45 |
| **BR-11 Operational controls** - expose missing codes, orphans, inconsistent assignments, missing rates, unclassified spend, unreconciled records | 21 check views `ctl.v_chk_*`, `ctl.run_all_controls()`, persistent queue `ctl.control_exception` with owner role, status and justification; row-level security per role | *My exceptions* (each role), *Control centre* (Finance, Director); to-do panels on each home page | T07, T37, T52, T53, T65 |
| **BR-12 Traceability** - who created/changed financially significant records, and when | Trigger `app.audit_row()` on ~25 tables → `app.audit_log` (user, role, time, before/after); status histories; `created_at` / `updated_at` | *Audit trail* (Finance, Director) | T24, T59 |

## Rules added for real operations (beyond the twelve)

| Rule | Where |
|---|---|
| Staff enter sales and receipts; managers decide (Academic, HR, Finance) | `06_security.sql` - five roles, grants, `SECURITY DEFINER` actions, RLS (T61-T68) |
| A discount above the approval threshold, or a scholarship, waits for Finance | `billing.enrol()` / `decide_discount()` (T35-T37) |
| Drop-out vs cancellation vs deferral have different money consequences | `billing.change_enrollment_status()` + revenue rebuild (T43-T45) |
| Kept payments of learners who leave are earned (non-refundable policy), configurable | setting `dropout_payment_policy` |
| Payroll cannot be approved before every session of the month is confirmed; sessions freeze after approval | `payroll.approve_run()`, `academic.confirm_session()` (T56, T57) |
| Every collector closes the cash drawer daily; differences need an explanation and a review | `app.close_cash()`, `app.review_cash_close()`, BIL-09 (T49-T51) |
| A teacher who leaves must be replaced on their classes | HR ends the role; control ACA-03 shows classes left without a teacher |
| Classes too small are cancelled before the start; learners return to the waiting list | `academic.cancel_class()` |
