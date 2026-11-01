# Who does what: the operating routine by role

AMI Operations follows how the centre actually runs. **Learning Advisors** are the only staff who enter data, and only for
sales and receipts. Every other area belongs to a manager. The database enforces this, so the application cannot be used to
bypass it.

| Role | Owns | Cannot |
|---|---|---|
| **Learning Advisor** (staff) | Leads, placement tests, enrolments, receipts, the daily cash close | Edit or delete a receipt, approve a discount or a void, see payroll or the P&L |
| **Academic Manager** | Courses, closure days, classes, timetables, teacher assignment, session confirmation | Read receipts or pay |
| **HR Manager** | Staff and HR codes, pay rates, advisor shifts, payroll runs, payslips, the commission rule | Approve discounts, see receipts |
| **Finance Manager** | Prices and discounts, approvals, receivables, refunds, write-offs, vouchers, fixed assets, accruals, the month-end close, settings | Approve payroll (HR does) |
| **Director** (optional) | Reads everything | Change anything |

Demo accounts: `la.nhi`, `la.khoa`, `academic.manager`, `hr.manager`, `finance.manager`, `director` (password shown on the sign-in page).

---

## Learning Advisor - the front desk

**Every day**
1. *My day*: call the follow-ups due, take any unassigned website lead (control SAL-01), check tomorrow's placement tests.
2. *Leads*: log every contact (outcome and next follow-up date), book tests, close lost leads **with a reason** - the reason feeds the funnel report.
3. *Placement tests*: enter the result from the marked paper (level, recommended course).
4. *New enrolment*: pick the tested lead, the course and a class with seats, the plan and discounts → **Preview** (price, instalments and the months the revenue is earned, computed by the database) → **Confirm**. A discount outside policy is saved but waits for Finance.
5. *Students & balances*: take payments. The amount defaults to the next instalment; the receipt is applied oldest-first and can be downloaded as a PDF. Drop-outs, deferrals and cancellations are recorded here with a reason.
6. *Daily cash close*: before leaving, count the drawer. The system knows what should be there; a difference needs an explanation and goes to Finance.

**When something is wrong**: a receipt is never edited. *Receipt register* → **Request void** with a reason; once Finance approves, issue the correct receipt.

**Weekly**: *My exceptions* - overdue instalments (BIL-03, mark "I'm on it" with the parent's promise), partial payments (BIL-08), enrolments without a test (SAL-02).

## Academic Manager

**Every week (Monday)**: *Confirm sessions* - tick what was taught last week; a session the centre cancelled pays nobody, so add a make-up session in *Classes & rosters*. Sessions older than three days raise ACA-02, and HR cannot approve payroll until the month is confirmed.

**Before each intake**: *Open a class* - course, start date, weekdays and time, room, teacher and assistant. The code, the sessions and the end date (public holidays and Tet skipped) are previewed before saving; from then on the advisors can sell it. The *Academic overview* shows waiting-list demand (BIL-07) and classes still without a teacher (ACA-03).

**When needed**: replace a teacher from a date (*Classes & rosters* → Teachers), cancel a class that will not reach the minimum size before it starts (its learners return to the waiting list), add closure days (*Courses & calendar*).

## HR Manager

**Every week**: *Advisor shifts* - mark absences and late arrivals, then confirm the week.

**Month-end calendar**

| Day | Task |
|---|---|
| last day | *Payroll runs*: create the month's run and add manual lines (allowances, bonuses, non-teaching activities) |
| 1st | Academic confirms the last sessions of the month |
| 2nd | **Calculate**: confirmed hours × the rate valid on each date, advisor shifts, fixed pay, commission from the rule, PIT and deductions |
| 3rd | **Approve** (refused while any session of the month is unconfirmed). The month's sessions are frozen. |
| 5th | Finance pays; the run becomes PAID. Payslips (PDF) are in the run. |

**When people change**: *Staff & HR codes* - a new contract stage starts a new HR code from a date (past months keep their rate); ending employment ends every role and shows the classes to reassign. *Pay rates* - new rates start on a date.

**Controls**: PAY-02 commission on a learner who left - cancel it before the run is paid, or accept the risk (already paid, no claw-back).

## Finance Manager

**Every day**: *Approvals* - discounts outside policy, receipt voids (open months only; afterwards it is a refund), cash differences, expense claims.

**Every week**: *Receivables & collections* (ageing, overdue learners, dropped-out balances to write off), *Expenses & vouchers* (every payment out, with VAT, account, cost centre and the month the cost belongs to), *Fixed assets* (capitalise capital purchases - EXP-02).

**Month-end close (around the 9th)**: *Month-end close* shows the checklist for the oldest open month - previous month closed, payroll approved, sessions confirmed, voids and discounts decided, cash differences reviewed, dropped-out balances written off. Post accruals (accrual basis only), then **Close**. The database refuses a month out of order or before payroll approval, and once closed nothing dated in that month can change.

**Reporting**: *Finance dashboard*, *P&L: cash vs accrual* (statement, one-month comparison with the reasons for the differences, class contribution), *Revenue & deferred* (what is owed as teaching), *Control centre* (all 21 controls; accept risks with a written justification), *Audit trail*.

## Director

Read-only access to the dashboard, the P&L, revenue and receivables, classes and rosters, the control centre and the audit trail.
