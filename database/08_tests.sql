/* =====================================================================================
   08_tests.sql - executable specification of the business rules
   -------------------------------------------------------------------------------------
   Run on a database built with build.sql + 07_test_fixture.sql (see tools/run_tests.sh):
       psql -v ON_ERROR_STOP=1 -d ami_test -f 08_tests.sql
   Every test raises an exception on failure (the script stops) and prints PASS otherwise.
   Everything runs inside one transaction that is rolled back, so the demo data is unchanged.
   ===================================================================================== */

\set ON_ERROR_STOP 1
\set QUIET 1
\o /dev/null
begin;

create function pg_temp.check(p_ok boolean, p_name text) returns void language plpgsql as $$
begin
    if p_ok is distinct from true then raise exception 'FAIL  %', p_name; end if;
    raise notice 'PASS  %', p_name;
end $$;

-- Expect a statement to be rejected; p_pattern is matched against the error message.
create function pg_temp.must_fail(p_sql text, p_pattern text, p_name text) returns void language plpgsql as $$
begin
    begin
        execute p_sql;
    exception when others then
        if sqlerrm ilike '%' || p_pattern || '%' then
            raise notice 'PASS  % (rejected: %)', p_name, sqlerrm;
            return;
        end if;
        raise exception 'FAIL  % - wrong error: %', p_name, sqlerrm;
    end;
    raise exception 'FAIL  % - statement was accepted', p_name;
end $$;

/* ------------------------------------------------------------------ 1. Keys & generated codes */
select pg_temp.check((select bool_and(student_code ~ '^AMI[0-9]{4}$') from crm.student),
                     'T01 customer codes follow AMIxxxx (legacy Customer Database key)');
select pg_temp.check((select bool_and(enrollment_code ~ '^ENR[0-9]{5}$') from billing.enrollment),
                     'T02 enrolment codes follow ENRxxxxx (replaces the "AMIxx-Course-Class" text key)');

/* ------------------------------------------------------------------ 2. Pricing engine */
select pg_temp.check((select net_payable from rpt.v_enrollment_pricing where enrollment_code = 'ENR00003') = 3850000,
                     'T03 FULL plan: 4,500,000 - 10% early bird - 200,000 group discount = 3,850,000');
select pg_temp.check((select net_payable from rpt.v_enrollment_pricing where enrollment_code = 'ENR00002') = 4500000,
                     'T04 50/30/20 plan: list - group discount + 200,000 materials fee = 4,500,000');
select pg_temp.check(
    (select array_agg(amount_due::numeric order by seq) from billing.payment_schedule where enrollment_id = 2)
        = array[200000, 2150000, 1290000, 860000]::numeric[],
    'T05 50/30/20 schedule = materials 200,000 then 50/30/20 of 4,300,000');
select pg_temp.check(not exists (select 1 from ctl.v_chk_bil_02_schedule_mismatch),
                     'T06 every payment schedule sums to its net payable (control BIL-02 clean)');

select pg_temp.check(
    (select string_agg(control_code || '=' || exceptions, ',' order by control_code) from ctl.run_all_controls())
        = 'ACA-01=1,ACA-02=1,ACA-03=0,BIL-01=0,BIL-02=0,BIL-03=2,BIL-04=1,BIL-05=1,BIL-06=1,BIL-07=1,BIL-08=0,BIL-09=1,'
          'EXP-01=7,EXP-02=1,EXP-03=1,PAY-01=0,PAY-02=1,PAY-03=0,REP-01=0,SAL-01=1,SAL-02=1',
    'T07 every control runs and finds exactly the exceptions planted in the demo data');

/* ------------------------------------------------------------------ 3. Integrity constraints */
select pg_temp.must_fail(
    $$insert into ref.course_price (course_id, delivery_mode_code, price_basis, amount, effective_from)
      values (21, 'OFFLINE', 'FULL_COURSE', 7500000, '2025-06-01')$$,
    'conflicting key', 'T08 overlapping price-list periods are rejected (EXCLUDE constraint)');

select pg_temp.must_fail(
    $$insert into billing.enrollment (student_id, course_id, delivery_mode_code, class_id, enrolled_on, plan_code, list_price)
      values (11, 5, 'OFFLINE', 4, '2025-06-20', 'FULL', 4500000)$$,
    'foreign key', 'T09 an enrolment cannot point to a class of another course (composite FK)');

select pg_temp.must_fail(
    $$insert into academic.session_staff (session_id, employee_role_id, hours)
      select session_id, 3, 2 from academic.class_session where class_id = 1 limit 1$$,
    'not assigned', 'T10 only staff assigned to the class can be booked on its sessions');

select pg_temp.must_fail(
    $$update payroll.payslip set net_pay = net_pay + 1 where payslip_id = (select min(payslip_id) from payroll.payslip)$$,
    'check constraint', 'T11 payslip net pay must equal taxable + allowances - PIT - deductions');

select pg_temp.must_fail($$select payroll.calculate_run(1)$$, 'cannot be recalculated',
                         'T12 a PAID payroll run is frozen');

/* ------------------------------------------------------------------ 4. Period lock & journals */
insert into finance.payment_voucher (voucher_no, voucher_date, requested_by, payee_employee_id, funding_source, payment_method_code, has_invoice)
values ('PC9001', '2025-06-28', 1, 1, 'PETTY_CASH', 'CASH', false);

select pg_temp.must_fail(
    $$insert into finance.payment_voucher_line (voucher_id, line_no, description, amount_excl_vat, vat_code,
                                                recognition_period_id, cost_center_code, account_code)
      select voucher_id, 1, 'Back-dated stationery', 150000, 'i0', 202501, '921012', 'E2.002'
      from finance.payment_voucher where voucher_no = 'PC9001'$$,
    'closed', 'T13 a cost cannot be booked into a closed period (202501)');

insert into finance.payment_voucher_line (voucher_id, line_no, description, amount_excl_vat, vat_code,
                                          recognition_period_id, cost_center_code, account_code)
select voucher_id, 1, 'Stationery', 150000, 'i10', 202506, '921012', 'E2.002'
from finance.payment_voucher where voucher_no = 'PC9001';
select pg_temp.check((select vat_rate = 0.10 and vat_amount = 15000 and amount_incl_vat = 165000
                      from finance.payment_voucher_line l join finance.payment_voucher v using (voucher_id) where v.voucher_no = 'PC9001'),
                     'T14 VAT rate is snapshotted from the VAT group and amounts are derived');

do $$
begin
    insert into finance.journal_entry (entry_no, period_id, entry_date, basis, entry_type, description)
    values ('JE-TEST-UNBAL', 202506, '2025-06-30', 'BOTH', 'ADJUSTMENT', 'Unbalanced test entry');
    insert into finance.journal_line (journal_entry_id, line_no, account_code, debit)
    select journal_entry_id, 1, 'E2.002', 1000 from finance.journal_entry where entry_no = 'JE-TEST-UNBAL';
    set constraints finance.trg_journal_balanced immediate;      -- what COMMIT would do
    raise exception 'FAIL  T15 unbalanced journal was accepted';
exception when others then
    if sqlerrm like 'FAIL%' then raise; end if;
    raise notice 'PASS  T15 unbalanced journals are rejected at commit (rejected: %)', sqlerrm;
end $$;
set constraints all deferred;

/* ------------------------------------------------------------------ 5. Order-to-cash through the application API */
-- New learner C11 joins IE_PRO_010725 (PRO 7.0+, offline) on the 50/30/20 plan with the 10% early-bird discount.
select billing.enrol(11, 21::smallint, 'OFFLINE', 4, 'P50_30_20', '2025-06-20', 2, null, array['EARLY_BIRD_10']) as new_enr \gset
select pg_temp.check((select net_payable from rpt.v_enrollment_pricing where enrollment_id = :new_enr) = 6815000
                     and (select status_code from billing.enrollment where enrollment_id = :new_enr) = 'REGISTERED'
                     and (select approval_status from billing.enrollment_discount where enrollment_id = :new_enr) = 'NOT_REQUIRED',
                     'T16 enrol(): 7,350,000 - 735,000 + 200,000 materials = 6,815,000; class not started -> REGISTERED; discount within policy');
select pg_temp.check(
    (select array_agg(amount_due::numeric order by seq) || array_agg(extract(month from due_date)::numeric order by seq)
       from billing.payment_schedule where enrollment_id = :new_enr)
        = array[200000, 3308000, 1985000, 1322000, 7, 7, 8, 9]::numeric[],
    'T17 schedule: materials + 50/30/20 rounded to thousands, last line absorbs rounding, due monthly from class start');

select billing.record_receipt(11, :new_enr, '2025-06-28', 3508000, 'BANK_TRANSFER', 2) as rcpt \gset
select pg_temp.check((select receipt_no from billing.receipt where receipt_id = :rcpt) = 'PT0019'
                     and (select sum(amount) from billing.payment_allocation where receipt_id = :rcpt) = 3508000,
                     'T18 record_receipt(): next receipt number, whole amount applied (no unapplied cash)');
select pg_temp.check(
    (select array_agg(a.amount::numeric order by s.seq) from billing.payment_allocation a join billing.payment_schedule s using (schedule_line_id)
      where a.receipt_id = :rcpt) = array[200000, 3308000]::numeric[],
    'T19 FIFO: materials fee is settled first, then instalment 1');
select pg_temp.check(
    (select array_agg(period_id::text || ':' || line_type || ':' || round(amount)::text order by period_id, line_type)
       from billing.revenue_schedule where enrollment_id = :new_enr)
        = array['202507:MATERIALS:200000', '202507:TUITION:2205000', '202508:TUITION:2205000', '202509:TUITION:2205000'],
    'T20 revenue follows the contract, not the cash: net tuition 6,615,000 earned evenly July-September, materials at class start');
select pg_temp.check((select outstanding_receivable = 3307000 and deferred_revenue = 3508000 and recognised_to_date = 0
                        from rpt.v_enrollment_balance where enrollment_id = :new_enr),
                     'T21 at 30 June: 3,307,000 still receivable, all 3,508,000 collected is deferred (nothing taught yet)');

-- Over-allocation is impossible
insert into billing.receipt (receipt_no, receipt_date, student_id, amount, payment_method_code)
values ('PT9002', '2025-06-29', 11, 100000, 'CASH');
select pg_temp.must_fail(
    $$insert into billing.payment_allocation (receipt_id, schedule_line_id, amount)
      select (select receipt_id from billing.receipt where receipt_no = 'PT9002'), schedule_line_id, 200000
      from billing.payment_schedule where enrollment_id = (select max(enrollment_id) from billing.enrollment) and seq = 3$$,
    'over-allocation', 'T22 a receipt cannot be allocated beyond its amount');
select pg_temp.must_fail(
    $$insert into billing.payment_allocation (receipt_id, schedule_line_id, amount)
      select (select receipt_id from billing.receipt where receipt_no = 'PT9002'), schedule_line_id, 50000
      from billing.payment_schedule where enrollment_id = (select max(enrollment_id) from billing.enrollment) and seq = 1$$,
    'over-payment', 'T23 a schedule line cannot be paid twice');

-- The life cycle follows the class dates; every status change is logged by trigger
select billing.sync_enrollment_statuses('2025-07-02');
select pg_temp.check((select status_code from billing.enrollment where enrollment_id = :new_enr) = 'ACTIVE'
                     and (select count(*) from billing.enrollment_status_history where enrollment_id = :new_enr) = 2,
                     'T24 sync_enrollment_statuses(): REGISTERED -> ACTIVE when the class starts, history written by trigger');

/* ------------------------------------------------------------------ 6. Revenue, deferral, P&L */
select pg_temp.check(not exists (select 1 from ctl.v_chk_rep_01_revenue_completeness),
                     'T25 every finished enrolment has earned exactly its contract value (control REP-01 clean)');
select pg_temp.check(not exists (
        select 1
        from rpt.v_deferred_revenue_coverage d
        join finance.fiscal_period p using (period_id)
        where d.deferred_balance - d.earned_not_collected <>
              coalesce((select sum(a.amount) from billing.payment_allocation a join billing.receipt r using (receipt_id)
                         where r.status = 'ISSUED' and r.receipt_date <= p.period_end), 0)
            - coalesce((select sum(amount) from billing.refund where refund_date <= p.period_end), 0)
            - coalesce((select sum(rs.amount) from billing.revenue_schedule rs where rs.period_id <= d.period_id), 0)),
    'T26 every month: deferred revenue - earned-not-collected = cumulative cash kept - cumulative revenue earned');
select pg_temp.check(
    (select sum(revenue) filter (where basis = 'ACCRUAL') from rpt.v_pnl_summary where period_id = 202506)
        = (select sum(amount) from billing.revenue_schedule where period_id = 202506)
    and (select sum(revenue) filter (where basis = 'CASH') from rpt.v_pnl_summary where period_id = 202506)
        = (select sum(a.amount) from billing.payment_allocation a join billing.receipt r using (receipt_id)
            where r.status = 'ISSUED' and r.receipt_date between '2025-06-01' and '2025-06-30'),
    'T27 accrual revenue = revenue schedule of the month; cash revenue = receipts applied in the month (BR-08: no double count)');
select pg_temp.check(
    (select sum(cost_of_sales + total_indirect_costs) filter (where basis = 'ACCRUAL')
          - sum(cost_of_sales + total_indirect_costs) filter (where basis = 'CASH') from rpt.v_pnl_summary) = 1500000,
    'T28 cash and accrual costs differ only by the accrual-only audit fee journal (1,500,000)');
select pg_temp.check((select count(*) = 36 and sum(amount) = 9900000 and min(amount) = 275000
                        from finance.depreciation_schedule where asset_id = 1),
                     'T29 projector capitalised and depreciated 275,000 x 36 months (legacy expensed it)');

/* ------------------------------------------------------------------ 7. Payroll */
select pg_temp.check(not exists (
        select 1 from payroll.payslip s
        join payroll.payroll_run r using (run_id) join finance.fiscal_period p using (period_id)
        join hr.employee e using (employee_id)
        join payroll.pit_rule pr on pr.employment_type = e.employment_type
                                and p.period_end >= pr.effective_from and (pr.effective_to is null or p.period_end < pr.effective_to)
        where s.pit_withheld <> case when s.taxable_earnings > pr.threshold_amount then round(s.taxable_earnings * pr.rate, 0) else 0 end),
    'T30 PIT = 10% when monthly taxable income > 2,000,000, else 0 (legacy payslip rule)');
select pg_temp.check((select bool_and(balance_check = 'OK') from rpt.v_payroll_register),
                     'T31 payroll register components reconcile to net pay');
select pg_temp.check(
    (select sum(amount) from payroll.payroll_line l join payroll.payroll_run r using (run_id)
      where r.period_id = 202504 and l.employee_id = 5 and l.earning_type_code = 'TEACHING_PAY')
        = (select round(sum(ss.hours) * max(r.hourly_rate), 0)
             from academic.session_staff ss join academic.class_session s using (session_id)
             join hr.employee_role er using (employee_role_id) join ref.salary_rate r on r.salary_code = er.salary_code
            where ss.employee_role_id = 6 and ss.confirmed_at is not null and s.status in ('DELIVERED','MAKE_UP')
              and s.session_date between '2025-04-01' and '2025-04-30'),
    'T32 teaching pay = confirmed session hours x salary-code rate');
select pg_temp.check(
    (select count(*) from payroll.commission where enrollment_id <> 8) = 5
    and not exists (
        select 1 from payroll.commission c
        join rpt.v_enrollment_balance b using (enrollment_id)
        join (select enrollment_id, sum(amount) filter (where charge_type <> 'MATERIALS_FEE') as tuition
                from billing.enrollment_charge group by enrollment_id) t using (enrollment_id)
        where c.enrollment_id <> 8
          and (c.amount <> round(t.tuition * 0.03, -3) or c.earned_period_id <> finance.period_of(b.fully_paid_on))),
    'T32b commission = 3% of net tuition (configurable rule), earned in the month the enrolment becomes fully paid');

/* ------------------------------------------------------------------ 8. Status labels */
select pg_temp.check(
    (select array_agg(class_code || '=' || status_label order by class_code collate "C") from rpt.v_class_status)
        = array['AE_L1_150125=Finished', 'COM_A1_020625=Running', 'IE_PROGRESS_030325=Finished', 'IE_PRO_010725=Starts in 1 days'],
    'T33 class status labels match the legacy formula as of 2025-06-30');

/* ------------------------------------------------------------------ 9. Real-business workflows */
-- Everything below is done "as" named application users, so the audit trail can be checked at the end.
select set_config('ami.app_user', 'finance.manager', true), set_config('ami.app_role', 'FINANCE_MANAGER', true);

select pg_temp.must_fail(
    $$select billing.enrol(6, (select course_id from academic.class where class_id = 2), 'OFFLINE', 2, 'FULL', '2025-06-25', 2)$$,
    'enrollment_one_active_per_class', 'T34 BR-02: a learner cannot hold two active enrolments in the same class');

select billing.enrol(12, 21::smallint, 'OFFLINE', 4, 'FULL', '2025-06-25', 3, null, array['PARTNER_SCHOOL_30']) as sch_enr \gset
select pg_temp.check((select approval_status from billing.enrollment_discount where enrollment_id = :sch_enr) = 'PENDING'
                     and (select net_payable from rpt.v_enrollment_pricing where enrollment_id = :sch_enr) = 5145000
                     and exists (select 1 from ctl.v_chk_bil_05_discount_policy where entity_id = :sch_enr),
                     'T35 a discount that needs approval is priced provisionally (5,145,000) and queued for Finance (BIL-05)');
select billing.decide_discount(:sch_enr, 1::smallint, false, 1, 'Not a partner-school student');
select pg_temp.check((select net_payable from rpt.v_enrollment_pricing where enrollment_id = :sch_enr) = 7350000
                     and (select sum(amount_due) from billing.payment_schedule where enrollment_id = :sch_enr) = 7350000
                     and not exists (select 1 from billing.enrollment_discount where enrollment_id = :sch_enr),
                     'T36 a rejected discount is removed, the enrolment re-priced at list and its schedule rebuilt');
select billing.decide_discount(8, 1::smallint, true, 1, 'Partner school confirmed');
select ctl.run_control('BIL-05') as bil05 \gset
select pg_temp.check(:bil05 = 0
                     and (select status from ctl.control_exception where control_code = 'BIL-05' and entity_id = 8) = 'CLEARED',
                     'T37 an approved discount leaves the queue: the BIL-05 exception is cleared automatically');
select pg_temp.must_fail(
    $$select billing.enrol(1, 21::smallint, 'OFFLINE', 4, 'FULL', '2025-06-25', 2, null,
                           array['EARLY_BIRD_10','SALES_TACTIC_5','RETURNING_5','PARTNER_SCHOOL_30'])$$,
    'At most three', 'T38 at most three discounts can be stacked');
update academic.class set capacity = 3 where class_id = 4;
select pg_temp.must_fail($$select billing.enrol(1, 21::smallint, 'OFFLINE', 4, 'FULL', '2025-06-25', 2)$$,
                         'is full', 'T39 a full class cannot be sold (capacity check at enrolment)');

-- Receipts are never edited: staff request a void, Finance approves it
select pg_temp.must_fail(format('select billing.request_receipt_void(%s, 2, %L)', :rcpt, ''), 'reason is required',
                         'T40 a void request needs a reason');
select billing.request_receipt_void(:rcpt, 2, 'Keyed against the wrong instalment plan');
select billing.decide_receipt_void(:rcpt, true, 1);
select pg_temp.check((select status from billing.receipt where receipt_id = :rcpt) = 'VOID'
                     and not exists (select 1 from billing.payment_allocation where receipt_id = :rcpt)
                     and (select outstanding_receivable from rpt.v_enrollment_balance where enrollment_id = :new_enr) = 6815000,
                     'T41 an approved void keeps the receipt (status VOID), releases its allocations and restores the balance');
select billing.request_receipt_void((select receipt_id from billing.receipt where receipt_no = 'PT0002'), 2, 'Test');
select pg_temp.must_fail($$select billing.decide_receipt_void((select receipt_id from billing.receipt where receipt_no = 'PT0002'), true, 1)$$,
                         'closed period', 'T42 a receipt in a closed month cannot be voided (refund instead)');

-- Drop-out and cancellation
select billing.change_enrollment_status(7, 'DROPPED', '2025-06-30', 'Moved to another city');
select pg_temp.check((select recognised_total = 4200000 and deferred_revenue = 0 and outstanding_receivable = 0
                             and payment_status = 'Closed (dropped out)' from rpt.v_enrollment_balance where enrollment_id = 7)
                     and (select amount from billing.revenue_schedule where enrollment_id = 7 and line_type = 'FORFEIT') = 2800000,
                     'T43 drop-out after 1 of 3 months: 1,400,000 tuition earned, the other 2,800,000 kept is forfeited revenue');
select pg_temp.must_fail($$select billing.change_enrollment_status(10, 'DROPPED', '2025-06-30', 'Changed mind')$$,
                         'cancelled, not dropped', 'T44 a learner whose class has not started is cancelled, not dropped');
select billing.change_enrollment_status(10, 'CANCELLED', '2025-06-30', 'Changed mind');
select pg_temp.check((select recognised_total = 500000 and outstanding_receivable = 0 and payment_status = 'Cancelled'
                        from rpt.v_enrollment_balance where enrollment_id = 10),
                     'T45 cancellation before the start: the non-refundable deposit (500,000) is earned, nothing else is owed');

-- Write-off of earned tuition that will not be collected
select pg_temp.must_fail($$select billing.write_off_balance(5, '2025-06-30', 100000, 'x', 1)$$, 'Only balances of dropped-out',
                         'T46 only dropped-out or cancelled learners can be written off');
select pg_temp.must_fail($$select billing.write_off_balance(1, '2025-06-30', 400000, 'x', 1)$$, 'exceeds',
                         'T47 a write-off cannot exceed the outstanding balance');
select billing.write_off_balance(1, '2025-06-30', 300000, 'Family moved away; balance uncollectible', 1);
select pg_temp.check((select outstanding_receivable from rpt.v_enrollment_balance where enrollment_id = 1) = 0
                     and ctl.run_control('BIL-06') = 0
                     and (select array_agg(distinct basis) from rpt.v_pnl_ledger where source_type = 'WRITE_OFF') = array['ACCRUAL'],
                     'T48 write-off clears the receivable and BIL-06; it is bad debt in the accrual P&L only');

-- Daily cash close (compensating control for staff who handle cash)
select pg_temp.must_fail($$select app.close_cash('2025-06-25', 2, 250000, null)$$, 'explain the difference',
                         'T49 a cash close with a difference needs an explanation');
select app.close_cash('2025-06-25', 2, 250000, 'Short 50,000: change given twice') as cc \gset
select pg_temp.check(ctl.run_control('BIL-09') = 1, 'T50 an unreviewed cash difference stays on control BIL-09');
select app.review_cash_close(:cc, 1);
select pg_temp.check(ctl.run_control('BIL-09') = 0, 'T51 once Finance reviews the difference, BIL-09 is clean');

-- Exception queue
update crm.lead set owner_employee_id = 2, channel_code = 'WALK_IN' where legacy_ref = 'L-C11';
select ctl.run_control('SAL-01') as sal01 \gset
select pg_temp.check(:sal01 = 0
                     and (select status from ctl.control_exception where control_code = 'SAL-01') = 'CLEARED',
                     'T52 fixing the data clears the exception on the next control run');
select pg_temp.must_fail($$update ctl.control_exception set status = 'RISK_ACCEPTED' where control_code = 'EXP-01'$$,
                         'check constraint', 'T53 accepting a risk requires a written justification');

-- Month-end close gates
select pg_temp.must_fail($$select finance.close_period(202503, 1)$$, 'closed in order', 'T54 months are closed in order');
select finance.close_period(p, 1) from generate_series(202502, 202505) p;
select pg_temp.must_fail($$select finance.close_period(202506, 1)$$, 'not been approved', 'T55 a month cannot close before HR approves its payroll');
select pg_temp.must_fail($$select payroll.approve_run((select run_id from payroll.payroll_run where period_id = 202506), 4)$$,
                         'not confirmed', 'T56 HR cannot approve payroll while sessions of the month are unconfirmed');
select academic.confirm_session(s.session_id, true, 8)
  from academic.class_session s join academic.class c using (class_id)
 where c.class_code = 'COM_A1_020625' and s.session_date = '2025-06-20';
select payroll.calculate_run(run_id) from payroll.payroll_run where period_id = 202506;
select payroll.approve_run(run_id, 1) from payroll.payroll_run where period_id = 202506;
select pg_temp.must_fail(
    $$select academic.confirm_session((select s.session_id from academic.class_session s join academic.class c using (class_id)
                                        where c.class_code = 'COM_A1_020625' and s.session_date = '2025-06-23'), false, 8)$$,
    'already approved', 'T57 once payroll is approved, the month''s sessions are frozen');
select finance.close_period(202506, 1);
select pg_temp.must_fail($$select billing.record_receipt(10, 5, '2025-06-30', 100000, 'CASH', 2)$$, 'closed',
                         'T58 after the close nothing can be posted into June');
select pg_temp.check((select count(*) from app.audit_log where table_name = 'billing.receipt' and row_key = 'PT0019'
                        and app_user = 'finance.manager' and db_role = 'FINANCE_MANAGER'
                        and old_row ->> 'status' = 'ISSUED' and new_row ->> 'status' = 'VOID') = 1,
                     'T59 audit trail: who voided receipt PT0019, when, before and after values (BR-12)');
select pg_temp.check((select role_code from app.authenticate('la.ha', 'demo')) = 'LEARNING_ADVISOR'
                     and not exists (select 1 from app.authenticate('la.ha', 'wrong-password')),
                     'T60 sign-in checks the bcrypt hash and returns the application role');

/* ------------------------------------------------------------------ 10. Database privileges (defence in depth) */
set role ami_learning_advisor;
do $$
begin
    begin perform 1 from payroll.payslip limit 1; raise exception 'FAIL  T61 LA read payslips';
    exception when insufficient_privilege then raise notice 'PASS  T61 a Learning Advisor cannot read payroll'; end;
    begin update billing.receipt set amount = 1 where receipt_no = 'PT0001'; raise exception 'FAIL  T62 LA edited a receipt';
    exception when insufficient_privilege then raise notice 'PASS  T62 a Learning Advisor cannot edit a receipt directly'; end;
    begin perform billing.decide_receipt_void(1, true, 2); raise exception 'FAIL  T63 LA approved a void';
    exception when insufficient_privilege then raise notice 'PASS  T63 a Learning Advisor cannot approve voids or discounts'; end;
    insert into crm.student (full_name, first_contact_date) values ('Test Learner', '2025-07-01');
    perform billing.record_receipt(11, (select max(enrollment_id) from billing.enrollment where student_id = 11), '2025-07-01', 200000, 'CASH', 2);
    raise notice 'PASS  T64 a Learning Advisor can register a learner and record a receipt through the API';
    if exists (select 1 from ctl.control_exception where control_code like 'EXP%') then raise exception 'FAIL  T65 LA sees EXP exceptions'; end if;
    if not exists (select 1 from ctl.control_exception where control_code like 'BIL-03') then raise exception 'FAIL  T65 LA misses BIL-03'; end if;
    raise notice 'PASS  T65 row-level security: a Learning Advisor sees only the exceptions of sales controls';
end $$;
reset role;
set role ami_academic_manager;
do $$
begin
    begin perform 1 from payroll.payroll_line limit 1; raise exception 'FAIL  T66';
    exception when insufficient_privilege then raise notice 'PASS  T66 the Academic Manager cannot read pay'; end;
    begin perform 1 from billing.receipt limit 1; raise exception 'FAIL  T66b';
    exception when insufficient_privilege then raise notice 'PASS  T66b the Academic Manager cannot read receipts'; end;
end $$;
reset role;
set role ami_hr_manager;
do $$
begin
    begin perform billing.decide_discount(1, 1::smallint, true, 1); raise exception 'FAIL  T67';
    exception when insufficient_privilege then raise notice 'PASS  T67 HR cannot approve discounts'; end;
end $$;
reset role;
set role ami_director;
do $$
begin
    if (select count(*) from rpt.v_pnl_summary) = 0 then raise exception 'FAIL  T68 director cannot read P&L'; end if;
    begin insert into finance.vendor (vendor_name, vendor_type) values ('X', 'COMPANY'); raise exception 'FAIL  T68';
    exception when insufficient_privilege then raise notice 'PASS  T68 the Director reads everything and changes nothing'; end;
end $$;
reset role;

rollback;
\o
\echo 'All 70 tests passed - transaction rolled back, fixture unchanged.'
