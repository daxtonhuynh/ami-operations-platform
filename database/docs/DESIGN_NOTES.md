# Design notes: from five workbooks to one relational model

This note explains **why** the model looks the way it does. The *what* is in [ERD.md](ERD.md) (diagrams) and
[DATA_DICTIONARY.md](DATA_DICTIONARY.md) (every column, generated from the catalog). The *proof* is
[`08_tests.sql`](../08_tests.sql): 70 executable tests that pin each business rule to the object that enforces it.

The starting point was the Excel/SharePoint system described in the [repository README](../../README.md): five linked
workbooks that ran AMI Education's sales, academic, payroll, expense and P&L processes. It worked because of one principle,
*enter once, reuse everywhere*. The relational model keeps that principle and moves the rules that lived in formulas,
colours and staff habits into keys, constraints, triggers and functions, where they cannot be bypassed.

---

## 1. Workbook-to-model lineage

| Legacy workbook / sheet | Replaced by | Notes |
|---|---|---|
| 01 · `Customer Management Database` | `crm.student`, `crm.guardian`, `crm.student_guardian`, `crm.student_availability`, `crm.lead`, `crm.lead_activity`, `crm.placement_test`, `crm.placement_test_score` | One row per learner instead of one row per contact event; parents become guardians shared between siblings. |
| 01 · status / outcome drop-downs | `ref.lead_stage`, `ref.qualification_status`, `ref.consultation_outcome`, `ref.lost_reason`, `ref.acquisition_channel` | Data-validation lists become code tables with foreign keys. |
| 01 · `Qualified Leads` (pricing columns) | `billing.enrollment`, `billing.enrollment_discount`, `billing.enrollment_charge`, `billing.group_registration` | The pricing formula becomes `billing.price_enrollment()`; every component is an itemised charge. |
| 01 · `Qualified Leads` (instalment columns) | `billing.payment_schedule` built by `billing.generate_payment_schedule()` from `ref.payment_plan_line` | Plans FULL, 50/30/20, MONTHLY_3, MONTHLY_5 are data, not formulas. |
| 01 · `Receipts Management` + `Receipt` | `billing.receipt`, `billing.payment_allocation`, `billing.refund`, `billing.write_off` | The composite text key is replaced by allocations (see D1). |
| 02 · `Khoá học khai giảng` + class rosters | `academic.class`, `academic.class_meeting_pattern`, `academic.class_session`, `academic.class_staff_assignment`, `academic.attendance` | Sessions are generated from the weekly pattern by `academic.generate_sessions()`. |
| 02 · hidden `SW`, `Library` | `academic.course_lesson`, `academic.learning_resource` | Syllabus and materials library. |
| 03 · `Salary Pipeline` (HR codes, rates) | `hr.employee`, `hr.employee_role`, `ref.salary_code`, `ref.salary_rate`, `hr.employee_rate_override`, `hr.employee_fixed_pay` | Rates are dated; personal overrides are explicit rows. |
| 03 · `Working Schedule_<month>` | `academic.session_staff` (teachers, TAs), `hr.work_shift` (Learning Advisors) | Hours are confirmed per session / shift, with who confirmed them. |
| 03 · `Pipeline`, `Bảng lương_Breakdown`, `Bảng lương`, payslips | `payroll.payroll_run`, `payroll.payroll_line`, `payroll.payslip`, `payroll.payslip_deduction`, `payroll.commission`, `payroll.pit_rule`, `payroll.statutory_deduction_rule` | `payroll.calculate_run()` replaces the month's copy of the workbook. |
| 04 · `Payment Management` | `finance.payment_voucher`, `finance.payment_voucher_line`, `finance.vendor` | Header/line split; VAT per line. |
| 04 · `Expense Reimbursement Form` | `finance.expense_claim`, `finance.expense_claim_line` | A paid claim links to its voucher. |
| 05 · `Expense Category`, `Revenue Category` | `finance.gl_account` (157 accounts), `finance.revenue_account_map`, `finance.earning_account_map` | Generated from the workbook's own code lists; balance-sheet accounts added for journals. |
| 05 · P&L layout rows | `finance.pnl_line`, `finance.pnl_line_mapping` | The legacy line codes (DC/SA/DA/EC/AC…) are kept in `legacy_line_code`. |
| 05 · cost-centre codes 9210xx | `finance.cost_center` | Each cost centre is flagged academic / non-academic (see D9). |
| 05 · `Receipt Control` monthly columns | `billing.revenue_schedule` built by `billing.build_revenue_schedule()` | Recognition is stored, not recomputed in thousands of cells. |
| 05 · `Profit and Loss_Cashflow`, `Profit and Loss_Accrual` | `rpt.v_pnl_ledger` → `rpt.v_pnl_by_line` → `rpt.v_pnl_summary` | One ledger with a `basis` column instead of two parallel sheets. |
| 05 · `Deferred Revenue Balance` | `rpt.v_deferred_revenue`, `rpt.v_deferred_revenue_coverage` | Including the legacy "coverage gap" check. |
| *(new)* | `finance.fiscal_period`, `finance.journal_entry`, `finance.journal_line`, `finance.fixed_asset`, `finance.depreciation_schedule` | Period locking, adjustments, capitalised equipment. |
| *(new)* | `ctl.control`, `ctl.control_run`, `ctl.control_exception` + 19 `ctl.v_chk_*` views | Controls that were visual cues in Excel become a queue (see D14). |

Field-level lineage (which Excel column each database column replaces) is listed at the end of the
[data dictionary](DATA_DICTIONARY.md#legacy-field-lineage).

---

## 2. Design decisions

### D1 · Receipts are allocated to schedule lines, not matched by a text key
**Excel:** each receipt carried a key such as `AMI15-Hoàn thành học phí theo lộ trình-Giai đoạn 1` (customer + payment type +
instalment) and the billing sheet looked it up with `XLOOKUP`. A typo, a renamed course or a learner paying two instalments
with one transfer broke the link silently.
**Model:** `billing.receipt` (cash in) and `billing.payment_schedule` (amounts due) are separate entities joined by
`billing.payment_allocation` (many-to-many with an amount). `billing.allocate_receipt()` applies cash oldest-due-first (FIFO).
A constraint trigger rejects any allocation that exceeds the receipt or the line due (T22, T23); cash left unapplied surfaces in
control BIL-04.

### D2 · Prices are a dated price list; the enrolment keeps a snapshot
**Excel:** the list price was looked up from the class code at the moment of typing, so a price change rewrote history.
**Model:** `ref.course_price` has `effective_from / effective_to` and an **exclusion constraint** (`btree_gist`) that forbids
two overlapping prices for the same course, mode and basis (T08). The enrolment stores `course_price_id` *and* the `list_price`
it was sold at. The same pattern (validity range + exclusion constraint) is used for salary rates, fees, PIT rules and
statutory deductions, HR role tenures and fixed pay - 8 exclusion constraints in total.

### D3 · Discounts are rows, and the price is the sum of its parts
**Excel:** three discount columns (`Chương trình giảm giá 1/2/3`), a group-discount column and a materials-fee column feeding
one formula: `(1 − d1 − d2 − d3) × list − group + materials`.
**Model:** `billing.enrollment_discount` (max three, enforced by `seq between 1 and 3`) snapshots the discount kind and value;
`billing.price_enrollment()` writes itemised `billing.enrollment_charge` rows, and **net payable = SUM(charges)** (T03, T04, T16).
Scholarships and partner-school discounts carry `requires_approval`; using one without an approver, or discounting more than 30 % of list price without one, is control BIL-05.

### D4 · Payment schedules come from plan templates
`ref.payment_plan_line` holds each plan's shares and month offsets. `billing.generate_payment_schedule()` rounds each instalment
to the nearest 1,000 VND, lets the last line absorb rounding, and dates instalments from the class start (T05, T17).
Control BIL-02 proves that every schedule still sums to its price (T06).

### D5 · Class status is a view with a fixed "as-of" date
**Excel:** `TODAY()` labelled classes *Starts in N days / Running / Ends in N days / Finished*, so last month's report could not be
reproduced. **Model:** `rpt.v_class_status` computes the same labels from `ref.as_of_date()`, which reads
`ref.app_setting('as_of_date')` and falls back to today. The notice windows (10 and 20 days) are settings too (T33).

### D6 · Sessions are rows, and teaching hours are confirmed per session
**Excel:** the timetable was text (`Mon & Wed 18:00-19:30`) and hours were re-typed into the monthly working schedule.
**Model:** `academic.class_meeting_pattern` → `academic.generate_sessions()` → `academic.class_session`. Staff log hours in
`academic.session_staff`; a trigger only accepts staff assigned to that class on that date (T10). Unconfirmed hours on delivered
sessions are control ACA-02, and only confirmed hours reach payroll (T32).

### D7 · The HR code becomes a composite foreign key
**Excel:** an HR code concatenated person + role + contract stage, and the rate was looked up from a salary code.
**Model:** `hr.employee_role` (one person can hold several roles) references `ref.salary_code (salary_code, role_code,
contract_stage_code)` with a **composite foreign key**, so a teacher can never be paid on an admin salary code. Rates live in
`ref.salary_rate` with validity dates; `hr.employee_rate_override` handles negotiated personal rates. `payroll.hourly_rate()`
picks override → salary-code rate.

### D8 · Payroll is calculated, then frozen
`payroll.calculate_run()` builds lines from confirmed session hours, LA shifts, fixed pay and accrued commission, then payslips with
PIT and statutory deductions from rule tables (legacy rule: 10 % when monthly taxable income exceeds 2,000,000 VND; T30).
A `CHECK` makes every payslip balance (`net = taxable + allowances − PIT − deductions`, T11) - the legacy *Balance Check*
column as a constraint. Runs move CALCULATED → APPROVED → PAID; a paid run cannot be recalculated (T12).

### D9 · One account can sit on two P&L lines - resolved by cost-centre scope
The legacy P&L reused some expense accounts in both *Cost of sales* and the indirect-cost sections (for example, materials for
classes vs. for the office). Each cost centre is flagged academic or not (`finance.cost_center.is_academic`) and
`finance.pnl_line_mapping` maps `(account_code, cost_center_scope)` → P&L line, where the scope is ACADEMIC, NON_ACADEMIC, or `ANY`
for accounts that appear once. The layout itself (`finance.pnl_line`,
102 lines) is generated from the workbook so the database P&L reads like the one management already knew.

### D10 · Revenue follows the contract, not the cash
`billing.build_revenue_schedule(enrollment_id)` writes the months in which each **enrolment** is earned - the accrual view a training
centre needs once it sells instalment plans:

| Situation | Rule |
|---|---|
| Learner in a class | net tuition (after discounts and adjustments) spread evenly from the class start month - or the enrolment month for a late joiner - to the class end month; the materials fee in the start month |
| Waiting list, deferred (on hold) | nothing is earned; any cash stays deferred (paid waiting-list learners after 30 days: control BIL-07) |
| Dropped out | tuition earned up to and including the drop month; payments kept beyond that are earned at once as **FORFEIT** revenue (setting `dropout_payment_policy` = FORFEIT, the non-refundable rule) unless Finance refunds them |
| Cancelled before the start | nothing is earned except kept payments (the seat deposit), forfeited the same way |
| Refund that reduces the contract (sessions the centre cancelled) | an ADJUSTMENT charge lowers the contract, so less is earned |

Closed months are final: a rebuild (drop-out, transfer, refund, rejected discount) deletes and re-spreads only the open months, with the
catch-up in the first open month. T20 shows a June enrolment for a July-September class earning 2,205,000 a month July-September whatever
was paid in June; T43 and T45 show forfeits. Control REP-01 proves every finished enrolment earned exactly its contract (BR-10).

*Earlier version:* revenue was scheduled per payment allocation (each receipt spread over the remaining class months). That reproduced
the workbook, but made revenue depend on the payment plan - a monthly payer and a full payer of the same class earned differently.

### D11 · Deferred revenue is derived, never typed
For each enrolment and month: cumulative cash kept (allocated receipts − refunds) − cumulative revenue recognised. A positive position is
**deferred revenue** (a contract liability: lessons owed); a negative one is **earned, not collected** (instalment plans). `rpt.v_deferred_revenue`
sums both per programme and month (T26 proves the identity every month); `rpt.v_deferred_revenue_coverage` keeps the workbook's management
check and adds *months of costs pre-funded*.

### D12 · Write-offs are bad debt in the accrual view only
Under contract-based recognition, unpaid tuition of a learner who left **was** revenue (it was taught). Writing it off (`billing.write_off_balance`,
legacy *Chi phí nợ xấu*) clears the receivable and posts account E6.001 *Bad debts* in the **accrual** P&L; the cash P&L never counted it (T48).
Refunds are the mirror image: cash going out in the cash P&L; in the accrual P&L the revenue schedule already excludes what is refunded.
Balances of dropped-out learners neither collected nor written off are control BIL-06.

### D13 · Capital expenditure is capitalised and depreciated
**Excel:** equipment was expensed in the month it was paid, which made the P&L lumpy. **Model:** voucher lines on capex accounts
(`gl_account.is_capex`) are excluded from the expense ledger and must have a `finance.fixed_asset` (control EXP-02);
`finance.generate_depreciation()` spreads cost straight-line (the test fixture's projector: 9,900,000 → 275,000 × 36 months, T29).

### D14 · Periods close; journals balance
`finance.fiscal_period.status` = OPEN / CLOSED. A trigger rejects voucher lines, journals, payroll runs, revenue-schedule lines, depreciation,
receipts, refunds and write-offs dated in a closed period (T13, T58). `finance.close_period()` closes months **in order** and only after HR
approved the month's payroll (T54, T55); HR can only approve once every session of the month is confirmed (T56), and after approval the
month's sessions are frozen (T57). Manual adjustments go through `finance.journal_entry/journal_line`, checked by a **deferred constraint trigger** so lines can
be inserted one by one but the entry must balance at commit (T15). A journal can apply to both bases or only to ACCRUAL / CASH,
which is how an audit-fee accrual appears only in the accrual P&L (T28).

### D15 · Controls become a queue, not a colour
In Excel, problems were spotted by conditional formatting and by the person who knew where to look. The model has a control
catalogue (`ctl.control`: domain, risk, rule, business rule, owning application role, frequency, severity), one check view per control,
and `ctl.run_all_controls()`. Exceptions are **persistent**: a record that still fails keeps its exception (with its assignee, status and
notes); one that passes again is CLEARED automatically; a RESOLVED one that fails again is reopened. Accepting a risk requires a written
justification (T53). Each role sees and works only its own controls (row-level security).

| Domain | Controls (owner) |
|---|---|
| Sales | SAL-01 lead without owner or channel · SAL-02 enrolment without placement test · BIL-03 overdue instalments · BIL-08 partial payment (Learning Advisor) |
| Billing | BIL-01 no schedule · BIL-02 schedule ≠ price · BIL-04 unapplied cash · BIL-05 discount waiting for approval · BIL-06 uncollectible not written off · BIL-09 cash not closed / difference not reviewed (Finance) |
| Academic | ACA-01 over capacity · ACA-02 session not confirmed · ACA-03 class without a teacher · BIL-07 paid learner waiting for a class (Academic Manager) |
| Payroll | PAY-01 hours without a pay rate · PAY-02 commission on a learner who left · PAY-03 payslip ≠ payroll lines (HR) |
| Expenses | EXP-01 payment without invoice · EXP-02 capex not capitalised · EXP-03 mis-coded spend (Finance) |
| Reporting | REP-01 revenue not fully recognised (Finance) |

### D16 · History is kept automatically
Triggers write `crm.lead_stage_history` and `billing.enrollment_status_history` on every change (T24), so funnel timing
(`rpt.v_lead_funnel`: test date, enrolment date, days to convert) comes from facts rather than from re-typed dates. Transactional tables carry
`created_at / updated_at`, and `legacy_ref` keeps the original Excel identifier for migrated rows.

### D17 · Staff enter, managers decide - enforced by the database
Sales and receipts are entered by Learning Advisors (staff); everything else belongs to a manager: Academic Manager (courses, classes,
sessions), HR Manager (staff, rates, shifts, payroll), Finance Manager (prices, approvals, refunds, write-offs, spend, close). The database,
not the application, enforces it (`06_security.sql`):
- five NOLOGIN group roles; the application logs in as `ami_app` (NOINHERIT: no rights of its own) and runs every transaction under
  `SET LOCAL ROLE` of the signed-in user's role;
- business actions are `SECURITY DEFINER` functions with a pinned `search_path`; a role is granted `EXECUTE` on its actions and `SELECT`
  on what it needs, so an advisor can *record* a receipt but cannot *edit* one (T62), and cannot approve a void or a discount (T63);
- row-level security on `ctl.control_exception` (T65); the Director reads everything and changes nothing (T68).

Compensating controls behind staff data entry: receipts are never edited (a void needs the Finance Manager and keeps the receipt marked
VOID, T40-T42); discounts outside policy wait for approval (T35-T37); every collector closes the cash drawer daily against the receipts
issued and differences stay open until Finance reviews them (BIL-09, T49-T51).

### D18 · One API for the application and the data generator
Each business action is one function call: `billing.enrol`, `assign_class`, `change_enrollment_status`, `record_receipt`, `apply_receipt`,
`request_receipt_void` / `decide_receipt_void`, `decide_discount`, `record_refund`, `write_off_balance`, `academic.open_class`,
`confirm_session`, `add_make_up_session`, `cancel_class`, `payroll.calculate_run` / `approve_run` / `mark_run_paid`, `app.close_cash`,
`finance.close_period`. The Streamlit application and the synthetic-data generator call the same functions, so the demo data was produced
by the rules it demonstrates.

### D19 · Who did what (BR-12)
`app.audit_row()` writes `app.audit_log` (user, role, time, table, key, before/after as JSON) for about 25 financially significant tables.
It runs as a trigger, so no screen and no script can skip it. The application identifies the user with transaction-local settings
(`ami.app_user`, `ami.app_role`); T59 traces who voided a receipt.

---

## 3. Business rule → enforcement

| Business rule | Enforced by | Test |
|---|---|---|
| One code per learner (`AMIxxxx`) and per enrolment (`ENRxxxxx`) | generated columns + `UNIQUE` | T01, T02 |
| Net price = list − % discounts − group discount + materials fee | `billing.price_enrollment()` | T03, T04, T16 |
| Schedule follows the plan and sums to the price | `billing.generate_payment_schedule()`, control BIL-02 | T05, T06, T17 |
| No overlapping prices / rates / tax rules | `EXCLUDE USING gist (… daterange …)` | T08 |
| An enrolment's class must be of the enrolled course | composite FK `(class_id, course_id)` | T09 |
| Only assigned staff log hours on a class | trigger `academic.check_session_staff` | T10 |
| Payslip balances | `CHECK` on `payroll.payslip` | T11 |
| Paid payroll is immutable | `payroll.calculate_run()` guard | T12 |
| Closed periods reject postings | trigger `finance.assert_period_open` | T13 |
| VAT rate captured at posting time | trigger `finance.snapshot_vat_rate` + generated VAT columns | T14 |
| Journals balance | deferred constraint trigger `finance.check_journal_balanced` | T15 |
| Cash applied oldest-due-first, never over-applied | `billing.allocate_receipt()` + constraint trigger `billing.check_allocation` | T18, T19, T22, T23 |
| Revenue earned from class start to class end, independent of cash | `billing.build_revenue_schedule()`, control REP-01 | T20, T25 |
| Deferred revenue − earned-not-collected = cash kept − revenue | `rpt.v_deferred_revenue` | T26 |
| Cash and accrual P&L from one ledger, nothing counted twice | `rpt.v_pnl_ledger` | T27, T28 |
| One active enrolment per learner and class (BR-02) | partial unique index `enrollment_one_active_per_class` | T34 |
| Discounts outside policy need approval | `billing.enrol()`, `billing.decide_discount()`, control BIL-05 | T35-T37 |
| Capacity, at most three discounts | `billing.enrol()` | T38, T39 |
| Receipts are voided, never edited | `request_receipt_void` / `decide_receipt_void`, grants | T40-T42, T62 |
| Drop-out / cancellation earn what was served or kept | `change_enrollment_status()`, `build_revenue_schedule()` | T43-T45 |
| Write-offs limited to balances of learners who left | `billing.write_off_balance()` | T46-T48 |
| Daily cash close | `app.close_cash()`, control BIL-09 | T49-T51 |
| Month-end gates and lock | `finance.close_period()`, `payroll.approve_run()`, `academic.confirm_session()` | T54-T58 |
| Audit trail and sign-in | `app.audit_row()`, `app.authenticate()` | T59, T60 |
| Role-based access | `06_security.sql` | T61-T68 |
| Status changes are audited | triggers on `crm.lead`, `billing.enrollment` | T24 |
| PIT 10 % above 2,000,000 VND | `payroll.pit_rule` + `payroll.calculate_run()` | T30 |
| Teaching pay = confirmed hours × rate | `payroll.calculate_run()`, `payroll.hourly_rate()` | T32 |
| Commission from a configurable rule | `payroll.commission_rule`, `payroll.accrue_commissions()` | T32b |
| Class status labels | `rpt.v_class_status` + `ref.as_of_date()` | T33 |
| Every operational control runs and reports | `ctl.run_all_controls()` | T07 |

---

## 4. Modelling conventions

- **Keys.** Surrogate identity keys (`<entity>_id`) for transactional tables; readable codes as primary keys for enumerations
  (`plan_code = 'P50_30_20'`); business identifiers (`class_code`, `receipt_no`, `voucher_no`) are `UNIQUE` and pattern-checked
  (`^PT[0-9]{3,}$`, `^PC[0-9]{3,}$`).
- **Normal form.** The transactional core is in 3NF. Denormalisation is deliberate and limited to **snapshots** that must not change
  when master data changes later (`list_price`, discount value, `vat_rate`) and to **derived columns** computed by PostgreSQL
  (`student_code`, `enrollment_code`, `vat_amount`, `planned_hours`, `total_sessions`, shift `hours`).
- **Money.** `numeric(16,2)` in VND through domains (`ref.money_vnd`, `ref.money_vnd_pos`); percentages through `ref.pct` (0-1).
- **Schemas by business domain** (`crm`, `academic`, `billing`, `hr`, `payroll`, `finance`, `ctl`) so permissions can follow
  responsibilities - for example, teachers could be granted `academic` only.
- **Documentation lives with the DDL.** Every table and all 650 columns carry a comment in `01_schema.sql`;
  `tools/build_comments.py` turns them into `COMMENT ON` statements and `tools/generate_docs.py` builds the dictionary and diagrams
  from the catalog.

## 5. Scope and assumptions

- Prices, salary rates and fees in `05_seed_reference.sql` are **illustrative**, and every person and amount in `07_test_fixture.sql`
  and `seed/demo_dataset.sql` is synthetic. The chart of accounts, P&L layout and cost centres are taken from the workbook structure.
- Personal income tax follows the workbook's flat withholding rule; progressive PIT and social-insurance employer contributions are
  out of scope (rule tables are ready for them).
- The model produces a management P&L, not statutory financial statements; balance-sheet accounts exist only to make journals
  balance.
- Single currency (VND), single legal entity, single centre. A `centre` dimension would be the first extension for a second branch.
