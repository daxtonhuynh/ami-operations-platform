/* =====================================================================================
   03_views.sql - reporting views (rpt) and control check views (ctl)
   Every view reads ref.as_of_date() so the whole model can be evaluated "as of" any date.
   ===================================================================================== */

/* =====================================================================================
   ACADEMIC
   ===================================================================================== */

-- Class register with date-driven status (legacy 'Khoá học khai giảng' column 'Trạng thái').
create or replace view rpt.v_class_status as
with p as (select ref.as_of_date() as as_of,
                  coalesce((select setting_value::int from ref.app_setting where setting_key = 'class_notice_days'), 10) as notice_days,
                  coalesce((select setting_value::int from ref.app_setting where setting_key = 'class_ending_days'), 20) as ending_days)
select c.class_id, c.class_code, co.programme_code, co.name as course_name, c.delivery_mode_code,
       c.start_date, coalesce(c.actual_end_date, c.planned_end_date) as end_date,
       c.total_hours, c.hours_per_session, c.sessions_per_week, c.total_sessions, c.total_weeks,
       round(c.total_weeks / 4.0, 2) as total_months,
       (select count(*) from academic.class_session s where s.class_id = c.class_id and s.status in ('DELIVERED','MAKE_UP')) as sessions_delivered,
       (select count(*) from billing.enrollment e where e.class_id = c.class_id and e.status_code in ('REGISTERED','ACTIVE','COMPLETED')) as learners,
       c.capacity,
       (select string_agg(emp.name_code, ' & ' order by a.assignment_role, emp.name_code)
          from academic.class_staff_assignment a join hr.employee_role er using (employee_role_id) join hr.employee emp using (employee_id)
         where a.class_id = c.class_id and a.assignment_role in ('LEAD_TEACHER','CO_TEACHER')
           and (a.effective_to is null or a.effective_to > least(p.as_of, coalesce(c.actual_end_date, c.planned_end_date)))) as teachers,
       (select string_agg(emp.name_code, ' & ' order by emp.name_code)
          from academic.class_staff_assignment a join hr.employee_role er using (employee_role_id) join hr.employee emp using (employee_id)
         where a.class_id = c.class_id and a.assignment_role = 'TEACHING_ASSISTANT'
           and (a.effective_to is null or a.effective_to > least(p.as_of, coalesce(c.actual_end_date, c.planned_end_date)))) as assistants,
       case
           when c.lifecycle_status = 'CANCELLED' then 'Cancelled'
           when p.as_of < c.start_date - p.notice_days then 'Not started'
           when p.as_of < c.start_date then 'Starts in ' || (c.start_date - p.as_of) || ' days'
           when p.as_of < coalesce(c.actual_end_date, c.planned_end_date) - p.ending_days then 'Running'
           when p.as_of < coalesce(c.actual_end_date, c.planned_end_date) then 'Ends in ' || (coalesce(c.actual_end_date, c.planned_end_date) - p.as_of) || ' days'
           else 'Finished'
       end as status_label
from academic.class c join ref.course co using (course_id) cross join p;

-- Confirmed and unconfirmed teaching hours per staff role, month and programme (source of teaching payroll).
create or replace view rpt.v_teaching_hours as
with confirmed as (
    select finance.period_of(s.session_date) as period_id, ss.employee_role_id, c.class_id, co.programme_code, c.delivery_mode_code,
           ss.hours, 0::numeric as open_hours
    from academic.session_staff ss
    join academic.class_session s using (session_id)
    join academic.class c using (class_id)
    join ref.course co on co.course_id = c.course_id
    where s.status in ('DELIVERED','MAKE_UP') and ss.confirmed_at is not null),
pending as (   -- past sessions the Academic Manager has not confirmed yet: hours the assigned staff expect to be paid
    select finance.period_of(s.session_date), a.employee_role_id, c.class_id, co.programme_code, c.delivery_mode_code,
           0::numeric, s.planned_hours
    from academic.class_session s
    join academic.class c using (class_id)
    join ref.course co on co.course_id = c.course_id
    join academic.class_staff_assignment a on a.class_id = s.class_id and s.session_date >= a.effective_from
                                          and (a.effective_to is null or s.session_date < a.effective_to)
    where s.session_date <= ref.as_of_date() and c.lifecycle_status <> 'CANCELLED'
      and (s.status = 'SCHEDULED' or (s.status in ('DELIVERED','MAKE_UP')
           and not exists (select 1 from academic.session_staff x where x.session_id = s.session_id))))
select x.period_id, e.employee_code, e.full_name, er.hr_code, er.role_code, x.programme_code, x.delivery_mode_code,
       sum(x.hours) as confirmed_hours, sum(x.open_hours) as unconfirmed_hours, count(distinct x.class_id) as classes
from (select * from confirmed union all select * from pending) x
join hr.employee_role er on er.employee_role_id = x.employee_role_id
join hr.employee e on e.employee_id = er.employee_id
group by x.period_id, e.employee_code, e.full_name, er.hr_code, er.role_code, x.programme_code, x.delivery_mode_code;

/* =====================================================================================
   SALES FUNNEL
   ===================================================================================== */

-- One row per lead with funnel milestones (legacy CMD + Qualified Leads, now with timestamps).
create or replace view rpt.v_lead_funnel as
select l.lead_id, cu.student_code, cu.full_name as learner, l.lead_date, finance.period_of(l.lead_date) as lead_period_id,
       emp.name_code as owner, l.channel_code, ch.channel_group, l.programme_code, l.stage_code, l.qualification_code,
       (select min(h.entered_at) from crm.lead_stage_history h where h.lead_id = l.lead_id and h.stage_code = 'TEST_BOOKED')::date as test_booked_on,
       (select min(t.completed_at) from crm.placement_test t where t.lead_id = l.lead_id and t.status = 'COMPLETED')::date as tested_on,
       en.enrolled_on,
       (en.enrollment_id is not null) as converted,
       en.enrolled_on - l.lead_date as days_to_convert
from crm.lead l
join crm.student cu using (student_id)
left join hr.employee emp on emp.employee_id = l.owner_employee_id
left join ref.acquisition_channel ch using (channel_code)
left join lateral (select e.enrollment_id, e.enrolled_on from billing.enrollment e
                   where e.lead_id = l.lead_id order by e.enrolled_on limit 1) en on true;

-- Funnel conversion by lead month and channel group.
create or replace view rpt.v_funnel_summary as
select lead_period_id, channel_group, count(*) as leads,
       count(*) filter (where tested_on is not null) as tested,
       count(*) filter (where converted) as converted,
       round(count(*) filter (where converted)::numeric / nullif(count(*),0), 4) as conversion_rate,
       round(avg(days_to_convert) filter (where converted), 1) as avg_days_to_convert
from rpt.v_lead_funnel group by lead_period_id, channel_group;

/* =====================================================================================
   BILLING
   ===================================================================================== */

-- Pricing breakdown of each enrolment (legacy pricing engine columns L..X of 'Qualified Leads').
create or replace view rpt.v_enrollment_pricing as
select e.enrollment_id, e.enrollment_code, cu.student_code, cu.full_name as learner, co.name as course_name,
       cl.class_code, e.plan_code, e.status_code,
       coalesce(sum(ch.amount) filter (where ch.charge_type = 'TUITION'), 0)        as list_price,
       coalesce(sum(ch.amount) filter (where ch.charge_type = 'DISCOUNT'), 0)       as discounts,
       coalesce(sum(ch.amount) filter (where ch.charge_type = 'GROUP_DISCOUNT'), 0) as group_discount,
       coalesce(sum(ch.amount) filter (where ch.charge_type = 'MATERIALS_FEE'), 0)  as materials_fee,
       coalesce(sum(ch.amount) filter (where ch.charge_type = 'ADJUSTMENT'), 0)     as adjustments,
       coalesce(sum(ch.amount), 0)                                                   as net_payable
from billing.enrollment e
join crm.student cu using (student_id)
join ref.course co on co.course_id = e.course_id
left join academic.class cl on cl.class_id = e.class_id
left join billing.enrollment_charge ch on ch.enrollment_id = e.enrollment_id
group by e.enrollment_id, e.enrollment_code, cu.student_code, cu.full_name, co.name, cl.class_code, e.plan_code, e.status_code;

-- Status of every schedule line: paid, remaining, overdue days and ageing bucket.
create or replace view rpt.v_schedule_line_status as
with p as (select ref.as_of_date() as as_of),
paid as (
    select a.schedule_line_id, sum(a.amount) as paid, max(r.receipt_date) as last_paid_on
    from billing.payment_allocation a join billing.receipt r using (receipt_id)
    where r.status = 'ISSUED' and r.receipt_date <= (select as_of from p)
    group by a.schedule_line_id)
select s.schedule_line_id, s.enrollment_id, e.enrollment_code, s.seq, s.line_type, s.label, s.due_date, s.amount_due,
       coalesce(paid.paid, 0) as paid, s.amount_due - coalesce(paid.paid, 0) as remaining, paid.last_paid_on,
       st.is_billable,
       case when st.is_billable and s.amount_due > coalesce(paid.paid,0) and s.due_date < p.as_of then p.as_of - s.due_date else 0 end as days_overdue,
       case when not st.is_billable or s.amount_due <= coalesce(paid.paid,0) then 'Settled / closed'
            when s.due_date >= p.as_of then 'Not yet due'
            when p.as_of - s.due_date <= 30 then '1-30 days'
            when p.as_of - s.due_date <= 60 then '31-60 days'
            when p.as_of - s.due_date <= 90 then '61-90 days'
            else '90+ days' end as ageing_bucket
from billing.payment_schedule s
join billing.enrollment e using (enrollment_id)
join ref.enrollment_status st on st.status_code = e.status_code
cross join p
left join paid using (schedule_line_id);

-- Enrolment balance (BR-06): what the learner owes, what was collected, what is overdue (legacy 'Công nợ', 'Doanh thu',
-- 'Chi phí nợ xấu', 'Tiến độ chung'). For a dropped-out or cancelled learner the amount owed is what was earned up to the drop
-- (plus kept payments); the rest of the contract is no longer due.
create or replace view rpt.v_enrollment_balance as
with p as (select ref.as_of_date() as as_of),
coll as (
    select s.enrollment_id, sum(a.amount) as collected, max(r.receipt_date) as last_paid_on
    from billing.payment_allocation a join billing.receipt r using (receipt_id) join billing.payment_schedule s using (schedule_line_id)
    where r.status = 'ISSUED' group by s.enrollment_id),
rec as (
    select enrollment_id, sum(amount) as recognised_total,
           sum(amount) filter (where period_id <= finance.period_of((select as_of from p))) as recognised_to_date
    from billing.revenue_schedule group by enrollment_id),
ovd as (select enrollment_id, sum(remaining) filter (where days_overdue > 0) as overdue from rpt.v_schedule_line_status group by enrollment_id),
base as (
    select pr.*, e.student_id, e.class_id, e.sales_owner_employee_id, e.enrolled_on, e.status_changed_on, st.is_billable, st.closes_receivable,
           coalesce(c.collected, 0) as collected, c.last_paid_on,
           coalesce(rf.refunded, 0) as refunded, coalesce(wo.written_off, 0) as written_off,
           coalesce(rec.recognised_total, 0) as recognised_total, coalesce(rec.recognised_to_date, 0) as recognised_to_date,
           case when st.closes_receivable then coalesce(rec.recognised_total, 0) else pr.net_payable end as amount_owed,
           coalesce(ovd.overdue, 0) as schedule_overdue
    from rpt.v_enrollment_pricing pr
    join billing.enrollment e using (enrollment_id)
    join ref.enrollment_status st on st.status_code = e.status_code
    left join coll c using (enrollment_id)
    left join rec using (enrollment_id)
    left join ovd using (enrollment_id)
    left join (select enrollment_id, sum(amount) as refunded from billing.refund group by enrollment_id) rf using (enrollment_id)
    left join (select enrollment_id, sum(amount) as written_off from billing.write_off group by enrollment_id) wo using (enrollment_id))
select enrollment_id, enrollment_code, student_id, student_code, learner, course_name, class_id, class_code, plan_code, status_code,
       sales_owner_employee_id, enrolled_on, net_payable, amount_owed, collected, refunded, written_off,
       greatest(amount_owed - (collected - refunded) - written_off, 0) as outstanding_receivable,
       case when closes_receivable then greatest(amount_owed - (collected - refunded) - written_off, 0)
            when is_billable then schedule_overdue else 0 end as overdue_amount,
       case when closes_receivable then greatest(amount_owed - (collected - refunded) - written_off, 0) else 0 end as uncollectible_not_written_off,
       greatest((collected - refunded) - amount_owed, 0) as credit_balance,
       recognised_to_date, recognised_total,
       greatest((collected - refunded) - recognised_to_date, 0) as deferred_revenue,
       greatest(recognised_to_date - (collected - refunded), 0) as earned_not_collected,
       case when status_code = 'CANCELLED' then 'Cancelled'
            when status_code = 'DROPPED' and greatest(amount_owed - (collected - refunded) - written_off, 0) = 0 then 'Closed (dropped out)'
            when status_code = 'DROPPED' then 'Dropped out - balance due'
            when status_code = 'DEFERRED' then 'On hold (deferred)'
            when collected - refunded >= net_payable and net_payable > 0 then 'Fully paid'
            when schedule_overdue > 0 then 'Overdue'
            when collected > 0 then 'Partially paid'
            else 'Not paid yet' end as payment_status,
       case when collected - refunded >= amount_owed and amount_owed > 0 then last_paid_on end as fully_paid_on,
       last_paid_on
from base;

-- Revenue position of each enrolment at the business date (ERD: deferred_revenue): cash kept vs revenue earned.
create or replace view rpt.v_enrollment_revenue_position as
select enrollment_id, enrollment_code, student_code, learner, course_name, class_code, status_code, net_payable,
       collected - refunded as cash_kept, recognised_to_date, recognised_total - recognised_to_date as still_to_recognise,
       deferred_revenue, earned_not_collected
from rpt.v_enrollment_balance;

-- Class roster (ERD: class_rosters, BR-03): derived from enrolments, never typed twice.
create or replace view rpt.v_class_roster as
select c.class_id, c.class_code, e.enrollment_id, e.enrollment_code, s.student_id, s.student_code, s.full_name as learner,
       s.date_of_birth, s.grade_label, s.phone, e.status_code, e.enrolled_on, e.class_assigned_at,
       ab.name_code as assigned_by, so.name_code as learning_advisor, lvl.level_code as output_commitment
from billing.enrollment e
join academic.class c on c.class_id = e.class_id
join crm.student s on s.student_id = e.student_id
left join hr.employee ab on ab.employee_id = e.class_assigned_by
left join hr.employee so on so.employee_id = e.sales_owner_employee_id
left join ref.proficiency_level lvl on lvl.level_id = e.output_commitment_level_id
where e.status_code in ('WAITLISTED', 'REGISTERED', 'ACTIVE', 'COMPLETED');

/* =====================================================================================
   PAYROLL
   ===================================================================================== */

-- Payroll register: one row per run and employee, earnings by type (legacy 'Bảng lương' + 'Bảng lương_Breakdown').
create or replace view rpt.v_payroll_register as
select r.run_id, r.period_id, e.employee_code, e.full_name, e.name_code,
       coalesce(sum(l.amount) filter (where l.earning_type_code = 'LA_PAY'), 0)        as la_pay,
       coalesce(sum(l.amount) filter (where l.earning_type_code = 'TEACHING_PAY'), 0)  as teaching_pay,
       coalesce(sum(l.amount) filter (where l.earning_type_code in ('TA_PAY','AT_PAY')), 0) as assistant_pay,
       coalesce(sum(l.amount) filter (where l.earning_type_code = 'FIXED_SALARY'), 0)  as fixed_salary,
       coalesce(sum(l.amount) filter (where l.earning_type_code = 'COMMISSION'), 0)    as commission,
       coalesce(sum(l.amount) filter (where l.earning_type_code = 'OVERTIME'), 0)      as overtime,
       coalesce(sum(l.amount) filter (where l.earning_type_code in ('NON_TEACHING_ACTIVITY','OTHER_INCOME')), 0) as other_pay,
       coalesce(sum(l.amount) filter (where et.is_allowance), 0)                       as allowances,
       ps.taxable_earnings, ps.pit_withheld, ps.other_deductions, ps.net_pay,
       case when ps.taxable_earnings = coalesce(sum(l.amount) filter (where et.is_taxable), 0)
             and ps.allowances = coalesce(sum(l.amount) filter (where et.is_allowance), 0) then 'OK' else 'MISMATCH' end as balance_check
from payroll.payroll_run r
join payroll.payroll_line l using (run_id)
join ref.earning_type et using (earning_type_code)
join hr.employee e using (employee_id)
left join payroll.payslip ps on ps.run_id = r.run_id and ps.employee_id = e.employee_id
group by r.run_id, r.period_id, e.employee_code, e.full_name, e.name_code,
         ps.taxable_earnings, ps.pit_withheld, ps.other_deductions, ps.net_pay, ps.allowances;

/* =====================================================================================
   FINANCE - unified P&L ledger (cash and accrual bases)
   ===================================================================================== */

-- Every P&L posting derived from the operational tables (BR-08: each source is counted once). basis = CASH or ACCRUAL.
-- Revenue differs by basis (cash collected vs tuition earned over the service period); costs are the same in both, except
-- bad-debt write-offs (accrual only), refunds (cash only) and journals flagged ACCRUAL_ONLY / CASH_ONLY.
create or replace view rpt.v_pnl_ledger as
with bases(basis) as (values ('CASH'), ('ACCRUAL')),
rev_cc as (select programme_code, min(cost_center_code) as cost_center_code from finance.cost_center
           where programme_code is not null group by programme_code)
-- 1. Cash-basis tuition: allocated receipts in the month received
select 'CASH'::text as basis, finance.period_of(r.receipt_date) as period_id, m.account_code,
       coalesce(rc.cost_center_code, '921011') as cost_center_code, co.programme_code, e.class_id,
       'RECEIPT_ALLOCATION'::text as source_type, a.allocation_id as source_id, a.amount::numeric as amount
from billing.payment_allocation a
join billing.receipt r using (receipt_id)
join billing.payment_schedule s using (schedule_line_id)
join billing.enrollment e on e.enrollment_id = s.enrollment_id
join ref.course co on co.course_id = e.course_id
join finance.revenue_account_map m on m.programme_code = co.programme_code and m.delivery_mode_code = e.delivery_mode_code
left join rev_cc rc on rc.programme_code = co.programme_code
where r.status = 'ISSUED'
union all
-- 2. Accrual-basis tuition: revenue schedule
select 'ACCRUAL', rs.period_id, rs.account_code, coalesce(rc.cost_center_code, '921011'), co.programme_code, e.class_id,
       'REVENUE_SCHEDULE', rs.revenue_line_id, rs.amount
from billing.revenue_schedule rs
join billing.enrollment e using (enrollment_id)
join ref.course co on co.course_id = e.course_id
left join rev_cc rc on rc.programme_code = co.programme_code
union all
-- 3. Refunds: cash going back out (cash basis). In the accrual view the revenue schedule already excludes what is refunded.
select 'CASH', finance.period_of(f.refund_date), 'E0.001', coalesce(rc.cost_center_code, '921011'), co.programme_code, e.class_id,
       'REFUND', f.refund_id, f.amount
from billing.refund f
join billing.enrollment e using (enrollment_id)
join ref.course co on co.course_id = e.course_id
left join rev_cc rc on rc.programme_code = co.programme_code
union all
-- 3b. Write-offs of earned tuition that will not be collected: bad debt (accrual basis only - the cash view never counted it)
select 'ACCRUAL', finance.period_of(w.write_off_date), 'E6.001', '921010', co.programme_code, e.class_id,
       'WRITE_OFF', w.write_off_id, w.amount
from billing.write_off w
join billing.enrollment e using (enrollment_id)
join ref.course co on co.course_id = e.course_id
union all
-- 4. Operating expenses from payment vouchers (capex lines are capitalised, not expensed)
select b.basis, vl.recognition_period_id, vl.account_code, vl.cost_center_code, cc.programme_code, vl.class_id,
       'VOUCHER_LINE', vl.voucher_line_id, vl.amount_incl_vat
from finance.payment_voucher_line vl
join finance.payment_voucher v using (voucher_id)
join finance.gl_account g on g.account_code = vl.account_code
join finance.cost_center cc on cc.cost_center_code = vl.cost_center_code
cross join bases b
where v.status <> 'VOID' and not g.is_capex
union all
-- 5. Payroll cost (gross pay incl. allowances)
select b.basis, r.period_id, l.account_code, l.cost_center_code, l.programme_code, null::bigint,
       'PAYROLL_LINE', l.payroll_line_id, l.amount
from payroll.payroll_line l
join payroll.payroll_run r using (run_id)
cross join bases b
where r.status in ('CALCULATED','APPROVED','PAID')
union all
-- 6. Depreciation / allocation of fixed assets
select b.basis, d.period_id, fa.charge_account_code, fa.cost_center_code, null, null,
       'DEPRECIATION', d.asset_id, d.amount
from finance.depreciation_schedule d
join finance.fixed_asset fa using (asset_id)
cross join bases b
union all
-- 7. Manual journals on P&L accounts
select b.basis, je.period_id, jl.account_code, coalesce(jl.cost_center_code, '921011'), null, null,
       'JOURNAL_LINE', jl.journal_line_id,
       case when g.account_class = 'REVENUE' then jl.credit - jl.debit else jl.debit - jl.credit end
from finance.journal_line jl
join finance.journal_entry je using (journal_entry_id)
join finance.gl_account g on g.account_code = jl.account_code
cross join bases b
where je.status = 'POSTED' and g.account_class in ('REVENUE','CONTRA_REVENUE','EXPENSE')
  and (je.basis = 'BOTH' or (je.basis = 'ACCRUAL_ONLY' and b.basis = 'ACCRUAL') or (je.basis = 'CASH_ONLY' and b.basis = 'CASH'));

-- Ledger amounts mapped to P&L lines (shared accounts resolved by academic / non-academic cost centre).
create or replace view rpt.v_pnl_by_line as
select l.basis, l.period_id, pl.section, pl.subsection, pl.pnl_line_code, pl.name as pnl_line, pl.sort_order,
       g.is_depreciation, sum(l.amount) as amount
from rpt.v_pnl_ledger l
join finance.gl_account g on g.account_code = l.account_code
join finance.cost_center cc on cc.cost_center_code = l.cost_center_code
cross join lateral (
    select m.pnl_line_code from finance.pnl_line_mapping m
    where m.account_code = l.account_code
      and m.cost_center_scope in ('ANY', case when cc.is_academic then 'ACADEMIC' else 'NON_ACADEMIC' end)
    order by (m.cost_center_scope = 'ANY') limit 1) mp
join finance.pnl_line pl on pl.pnl_line_code = mp.pnl_line_code
group by l.basis, l.period_id, pl.section, pl.subsection, pl.pnl_line_code, pl.name, pl.sort_order, g.is_depreciation;

-- Monthly P&L summary per basis (legacy 'Profit and Loss_Cashflow' / '_Accrual' totals).
create or replace view rpt.v_pnl_summary as
with lines as (
    select basis, period_id,
           sum(amount) filter (where section = 'REVENUE')              as revenue,
           sum(amount) filter (where section = 'REVENUE_DEDUCTIONS')   as deductions,
           sum(amount) filter (where section = 'COST_OF_SALES')        as cost_of_sales,
           sum(amount) filter (where section = 'STAFF_COSTS')          as staff_costs,
           sum(amount) filter (where section = 'MARKETING_COSTS')      as marketing_costs,
           sum(amount) filter (where section = 'ESTABLISHMENT_COSTS')  as establishment_costs,
           sum(amount) filter (where section = 'ADMINISTRATION_COSTS') as administration_costs,
           sum(amount) filter (where is_depreciation)                  as depreciation
    from rpt.v_pnl_by_line group by basis, period_id),
grid as (select b.basis, p.period_id from finance.fiscal_period p cross join (values ('CASH'),('ACCRUAL')) b(basis)),
x as (
    select g.basis, g.period_id,
           coalesce(revenue,0) as revenue, coalesce(deductions,0) as deductions,
           coalesce(revenue,0) - coalesce(deductions,0) as net_revenue,
           coalesce(cost_of_sales,0) as cost_of_sales,
           coalesce(staff_costs,0) as staff_costs, coalesce(marketing_costs,0) as marketing_costs,
           coalesce(establishment_costs,0) as establishment_costs, coalesce(administration_costs,0) as administration_costs,
           coalesce(depreciation,0) as depreciation
    from grid g left join lines l using (basis, period_id))
select basis, period_id, revenue, deductions, net_revenue, cost_of_sales,
       net_revenue - cost_of_sales as gross_margin,
       round((net_revenue - cost_of_sales) / nullif(net_revenue, 0), 4) as gross_margin_pct,
       staff_costs, marketing_costs, establishment_costs, administration_costs,
       staff_costs + marketing_costs + establishment_costs + administration_costs as total_indirect_costs,
       net_revenue - cost_of_sales - (staff_costs + marketing_costs + establishment_costs + administration_costs) as ebit,
       round((net_revenue - cost_of_sales - (staff_costs + marketing_costs + establishment_costs + administration_costs)) / nullif(net_revenue, 0), 4) as ebit_pct,
       depreciation,
       net_revenue - cost_of_sales - (staff_costs + marketing_costs + establishment_costs + administration_costs) + depreciation as ebitda
from x;

-- Deferred tuition revenue per programme and month (legacy 'Deferred Revenue Balance', spec section 8 caution): a cumulative
-- position built per enrolment at each month end - cash kept to date minus revenue earned to date. A positive position is a
-- contract liability (deferred revenue: taught later); a negative one is tuition earned but not yet collected.
create or replace view rpt.v_deferred_revenue as
with cash as (
    select s.enrollment_id, finance.period_of(r.receipt_date) as period_id, sum(a.amount) as amount
    from billing.payment_allocation a join billing.receipt r using (receipt_id) join billing.payment_schedule s using (schedule_line_id)
    where r.status = 'ISSUED' group by 1, 2
    union all
    select enrollment_id, finance.period_of(refund_date), -sum(amount) from billing.refund group by 1, 2),
cash_m as (select enrollment_id, period_id, sum(amount) as cash from cash group by 1, 2),
rev_m as (select enrollment_id, period_id, sum(amount) as revenue from billing.revenue_schedule group by 1, 2),
grid as (
    select e.enrollment_id, co.programme_code, p.period_id
    from billing.enrollment e join ref.course co on co.course_id = e.course_id
    join finance.fiscal_period p on p.period_end >= date_trunc('month', e.enrolled_on)),
pos as (
    select g.programme_code, g.period_id, coalesce(c.cash, 0) as cash, coalesce(r.revenue, 0) as revenue,
           sum(coalesce(c.cash, 0) - coalesce(r.revenue, 0)) over (partition by g.enrollment_id order by g.period_id) as position
    from grid g left join cash_m c using (enrollment_id, period_id) left join rev_m r using (enrollment_id, period_id))
select period_id, programme_code,
       sum(cash) as cash_received, sum(revenue) as revenue_recognised, sum(cash) - sum(revenue) as deferred_movement,
       sum(greatest(position, 0)) as deferred_balance,
       sum(greatest(-position, 0)) as earned_not_collected,
       round(sum(revenue) / nullif(sum(cash), 0), 4) as accrual_to_cash_ratio
from pos group by period_id, programme_code;

-- Company-level deferred revenue and how many months of the cost base it pre-funds.
create or replace view rpt.v_deferred_revenue_coverage as
select d.period_id, sum(d.cash_received) as cash_received, sum(d.revenue_recognised) as revenue_recognised,
       sum(d.deferred_movement) as deferred_movement, sum(d.deferred_balance) as deferred_balance,
       sum(d.earned_not_collected) as earned_not_collected,
       s.cost_of_sales + s.total_indirect_costs as total_expenses,
       sum(d.deferred_movement) - (s.cost_of_sales + s.total_indirect_costs) as legacy_coverage_gap,
       round(sum(d.deferred_balance) / nullif(s.cost_of_sales + s.total_indirect_costs, 0), 2) as months_of_costs_prefunded
from rpt.v_deferred_revenue d
join rpt.v_pnl_summary s on s.period_id = d.period_id and s.basis = 'ACCRUAL'
group by d.period_id, s.cost_of_sales, s.total_indirect_costs;

-- Course-level contribution margin per class: earned revenue - teacher, assistant and direct class costs.
create or replace view rpt.v_class_contribution as
with rev as (
    select e.class_id, sum(rs.amount) as revenue_recognised
    from billing.revenue_schedule rs join billing.enrollment e using (enrollment_id)
    where rs.period_id <= finance.period_of(ref.as_of_date())
    group by e.class_id),
labour as (
    select s.class_id,
           sum(ss.hours * payroll.hourly_rate(ss.employee_role_id, s.session_date)) filter (where er.role_code like 'TEACHER%') as teacher_cost,
           sum(ss.hours * payroll.hourly_rate(ss.employee_role_id, s.session_date)) filter (where er.role_code not like 'TEACHER%') as assistant_cost,
           sum(ss.hours) filter (where er.role_code like 'TEACHER%') as teacher_hours
    from academic.session_staff ss
    join academic.class_session s using (session_id)
    join hr.employee_role er on er.employee_role_id = ss.employee_role_id
    where ss.confirmed_at is not null and s.session_date <= ref.as_of_date()
    group by s.class_id),
direct as (
    select vl.class_id, sum(vl.amount_incl_vat) as direct_costs
    from finance.payment_voucher_line vl join finance.payment_voucher v using (voucher_id)
    where vl.class_id is not null and v.status <> 'VOID' and vl.recognition_period_id <= finance.period_of(ref.as_of_date())
    group by vl.class_id)
select cs.class_code, cs.programme_code, cs.course_name, cs.status_label, cs.learners,
       coalesce(rev.revenue_recognised, 0) as revenue_recognised,
       round(coalesce(labour.teacher_cost, 0), 0) as teacher_cost,
       round(coalesce(labour.assistant_cost, 0), 0) as assistant_cost,
       coalesce(direct.direct_costs, 0) as direct_costs,
       coalesce(rev.revenue_recognised, 0) - round(coalesce(labour.teacher_cost,0),0) - round(coalesce(labour.assistant_cost,0),0) - coalesce(direct.direct_costs,0) as contribution,
       round((coalesce(rev.revenue_recognised, 0) - coalesce(labour.teacher_cost,0) - coalesce(labour.assistant_cost,0) - coalesce(direct.direct_costs,0))
             / nullif(rev.revenue_recognised, 0), 4) as contribution_margin_pct,
       round(coalesce(rev.revenue_recognised, 0) / nullif(labour.teacher_hours, 0), 0) as revenue_per_teaching_hour
from rpt.v_class_status cs
left join rev using (class_id)
left join labour using (class_id)
left join direct using (class_id);

-- Executive KPIs per month.
create or replace view rpt.v_kpi_monthly as
select p.period_id,
       f.leads, f.converted,
       round(f.converted::numeric / nullif(f.leads, 0), 4) as enrollment_conversion,
       coll.due_to_date, coll.collected_to_date,
       round(coll.collected_to_date / nullif(coll.due_to_date, 0), 4) as tuition_collection_rate,
       coll.overdue_receivables,
       coalesce(acc.revenue, 0) as recognised_revenue,
       coalesce(dr.deferred_balance, 0) as deferred_revenue_balance,
       acc.gross_margin, acc.ebit
from finance.fiscal_period p
left join lateral (select count(*) as leads, count(*) filter (where converted) as converted
                   from rpt.v_lead_funnel lf where lf.lead_period_id = p.period_id) f on true
left join lateral (
    select sum(s.amount_due) as due_to_date,
           sum(coalesce(pd.paid, 0)) as collected_to_date,
           sum(greatest(s.amount_due - coalesce(pd.paid, 0), 0)) filter (where st.is_billable) as overdue_receivables
    from billing.payment_schedule s
    join billing.enrollment e using (enrollment_id)
    join ref.enrollment_status st on st.status_code = e.status_code
    left join lateral (select sum(a.amount) as paid from billing.payment_allocation a join billing.receipt r using (receipt_id)
                       where a.schedule_line_id = s.schedule_line_id and r.status = 'ISSUED' and r.receipt_date <= p.period_end) pd on true
    where s.due_date <= p.period_end) coll on true
left join rpt.v_pnl_summary acc on acc.period_id = p.period_id and acc.basis = 'ACCRUAL'
left join (select period_id, sum(deferred_balance) as deferred_balance from rpt.v_deferred_revenue group by period_id) dr
       on dr.period_id = p.period_id;

/* =====================================================================================
   CONTROL CHECK VIEWS - each returns (entity_type, entity_id, entity_ref, detail) per exception
   ===================================================================================== */

-- SAL-01 Open leads without an owner or acquisition channel.
create or replace view ctl.v_chk_sal_01_lead_incomplete (entity_type, entity_id, entity_ref, detail) as
select 'LEAD'::text, l.lead_id, c.student_code,
       jsonb_build_object('owner_missing', l.owner_employee_id is null, 'channel_missing', l.channel_code is null)
from crm.lead l join crm.student c using (student_id) join ref.lead_stage st using (stage_code)
where l.closed_on is null and (l.owner_employee_id is null or l.channel_code is null);

-- SAL-02 Enrolments from a lead without a completed placement test.
create or replace view ctl.v_chk_sal_02_enrolled_without_test (entity_type, entity_id, entity_ref, detail) as
select 'ENROLLMENT'::text, e.enrollment_id, e.enrollment_code, jsonb_build_object('lead_id', e.lead_id)
from billing.enrollment e
where e.lead_id is not null
  and not exists (select 1 from crm.placement_test t where t.lead_id = e.lead_id and t.status = 'COMPLETED');

-- BIL-01 Billable enrolments without a payment schedule.
create or replace view ctl.v_chk_bil_01_no_schedule (entity_type, entity_id, entity_ref, detail) as
select 'ENROLLMENT'::text, e.enrollment_id, e.enrollment_code, jsonb_build_object('status', e.status_code, 'enrolled_on', e.enrolled_on)
from billing.enrollment e join ref.enrollment_status st using (status_code)
where st.is_billable and not exists (select 1 from billing.payment_schedule s where s.enrollment_id = e.enrollment_id);

-- BIL-02 Payment schedule total differs from the net price. A refund that reduced the contract was billed and paid before it was
-- given back, so it stays on the schedule.
create or replace view ctl.v_chk_bil_02_schedule_mismatch (entity_type, entity_id, entity_ref, detail) as
select 'ENROLLMENT'::text, p.enrollment_id, p.enrollment_code,
       jsonb_build_object('net_payable', p.net_payable, 'scheduled', s.scheduled, 'contract_refunds', coalesce(rf.amount, 0))
from rpt.v_enrollment_pricing p
join (select enrollment_id, sum(amount_due) as scheduled from billing.payment_schedule group by enrollment_id) s using (enrollment_id)
left join (select enrollment_id, sum(amount) as amount from billing.refund where reduces_contract group by enrollment_id) rf using (enrollment_id)
where s.scheduled <> p.net_payable + coalesce(rf.amount, 0);

-- BIL-03 Instalments overdue by more than 30 days.
create or replace view ctl.v_chk_bil_03_overdue (entity_type, entity_id, entity_ref, detail) as
select 'SCHEDULE_LINE'::text, schedule_line_id, enrollment_code || '/' || seq,
       jsonb_build_object('label', label, 'due_date', due_date, 'remaining', remaining, 'days_overdue', days_overdue)
from rpt.v_schedule_line_status where days_overdue > 30;

-- BIL-04 Receipts not fully allocated to a schedule line (unapplied cash).
create or replace view ctl.v_chk_bil_04_unapplied_cash (entity_type, entity_id, entity_ref, detail) as
select 'RECEIPT'::text, r.receipt_id, r.receipt_no,
       jsonb_build_object('amount', r.amount, 'allocated', coalesce(sum(a.amount), 0))
from billing.receipt r left join billing.payment_allocation a using (receipt_id)
where r.status = 'ISSUED'
group by r.receipt_id, r.receipt_no, r.amount
having coalesce(sum(a.amount), 0) < r.amount;

-- BIL-05 Discounts outside policy still waiting for the Finance Manager's decision.
create or replace view ctl.v_chk_bil_05_discount_policy (entity_type, entity_id, entity_ref, detail) as
select 'ENROLLMENT'::text, p.enrollment_id, p.enrollment_code,
       jsonb_build_object('list_price', p.list_price, 'discount_total', -(p.discounts + p.group_discount),
                          'discount_pct', round(-(p.discounts + p.group_discount) / nullif(p.list_price, 0), 4),
                          'pending', (select string_agg(d.discount_code, ', ') from billing.enrollment_discount d
                                       where d.enrollment_id = p.enrollment_id and d.approval_status = 'PENDING'))
from rpt.v_enrollment_pricing p
where exists (select 1 from billing.enrollment_discount d where d.enrollment_id = p.enrollment_id and d.approval_status = 'PENDING');

-- BIL-06 Dropped-out or cancelled learners with earned tuition neither collected nor written off.
create or replace view ctl.v_chk_bil_06_uncollectible (entity_type, entity_id, entity_ref, detail) as
select 'ENROLLMENT'::text, enrollment_id, enrollment_code,
       jsonb_build_object('status', status_code, 'amount', uncollectible_not_written_off)
from rpt.v_enrollment_balance where uncollectible_not_written_off > 0;

-- BIL-07 Paid learners still on the waiting list after 30 days (revenue cannot be recognised). Deferred learners are on hold by
-- their own choice and are not counted.
create or replace view ctl.v_chk_bil_07_paid_without_class (entity_type, entity_id, entity_ref, detail) as
select 'ENROLLMENT'::text, e.enrollment_id, e.enrollment_code,
       jsonb_build_object('enrolled_on', e.enrolled_on, 'paid', b.collected)
from billing.enrollment e join rpt.v_enrollment_balance b using (enrollment_id)
where e.class_id is null and b.collected > 0 and e.enrolled_on < ref.as_of_date() - 30
  and e.status_code = 'WAITLISTED';

-- BIL-08 Partial payments: a schedule line paid with a different amount than due (receipt does not match tuition).
create or replace view ctl.v_chk_bil_08_partial_payment (entity_type, entity_id, entity_ref, detail) as
select 'SCHEDULE_LINE'::text, schedule_line_id, enrollment_code || '/' || seq,
       jsonb_build_object('amount_due', amount_due, 'paid', paid, 'last_paid_on', last_paid_on)
from rpt.v_schedule_line_status
where paid > 0 and paid < amount_due and is_billable and last_paid_on < ref.as_of_date() - 7;

-- ACA-01 Classes over capacity.
create or replace view ctl.v_chk_aca_01_over_capacity (entity_type, entity_id, entity_ref, detail) as
select 'CLASS'::text, class_id, class_code, jsonb_build_object('learners', learners, 'capacity', capacity)
from rpt.v_class_status where learners > capacity;

-- ACA-02 Delivered sessions older than 3 days without confirmed teaching hours.
create or replace view ctl.v_chk_aca_02_unconfirmed_hours (entity_type, entity_id, entity_ref, detail) as
select 'SESSION'::text, s.session_id, c.class_code || '#' || s.session_no,
       jsonb_build_object('session_date', s.session_date, 'status', s.status)
from academic.class_session s join academic.class c using (class_id)
where s.session_date < ref.as_of_date() - 3 and c.lifecycle_status <> 'CANCELLED'
  and (s.status = 'SCHEDULED'
       or (s.status in ('DELIVERED','MAKE_UP')
           and not exists (select 1 from academic.session_staff ss where ss.session_id = s.session_id and ss.confirmed_at is not null)));

-- PAY-01 Confirmed hours for a role with no valid hourly rate.
create or replace view ctl.v_chk_pay_01_missing_rate (entity_type, entity_id, entity_ref, detail) as
select 'EMPLOYEE_ROLE'::text, er.employee_role_id, er.hr_code,
       jsonb_build_object('first_unrated_date', min(s.session_date))
from academic.session_staff ss
join academic.class_session s using (session_id)
join hr.employee_role er on er.employee_role_id = ss.employee_role_id
where ss.confirmed_at is not null and payroll.hourly_rate(er.employee_role_id, s.session_date) is null
group by er.employee_role_id, er.hr_code;

-- PAY-02 Commission on enrolments that were cancelled, dropped or never fully paid.
create or replace view ctl.v_chk_pay_02_commission_at_risk (entity_type, entity_id, entity_ref, detail) as
select 'COMMISSION'::text, cm.commission_id, b.enrollment_code,
       jsonb_build_object('status', b.status_code, 'payment_status', b.payment_status, 'commission', cm.amount)
from payroll.commission cm join rpt.v_enrollment_balance b using (enrollment_id)
where cm.status <> 'CANCELLED' and (b.status_code in ('CANCELLED','DROPPED') or b.payment_status <> 'Fully paid');

-- PAY-03 Payslip totals that do not match their payroll lines.
create or replace view ctl.v_chk_pay_03_payslip_mismatch (entity_type, entity_id, entity_ref, detail) as
select 'PAYSLIP'::text, ps.payslip_id, e.employee_code || '/' || r.period_id,
       jsonb_build_object('payslip_taxable', ps.taxable_earnings, 'lines_taxable', x.taxable)
from payroll.payslip ps
join payroll.payroll_run r using (run_id)
join hr.employee e using (employee_id)
join (select l.run_id, l.employee_id, sum(l.amount) filter (where et.is_taxable) as taxable
      from payroll.payroll_line l join ref.earning_type et using (earning_type_code) group by 1, 2) x
  on x.run_id = ps.run_id and x.employee_id = ps.employee_id
where ps.taxable_earnings <> coalesce(x.taxable, 0);

-- EXP-01 Payments without a VAT invoice above the threshold (setting 'no_invoice_threshold').
create or replace view ctl.v_chk_exp_01_no_invoice (entity_type, entity_id, entity_ref, detail) as
select 'VOUCHER'::text, v.voucher_id, v.voucher_no,
       jsonb_build_object('amount', sum(vl.amount_incl_vat), 'payee', coalesce(vd.vendor_name, 'employee'))
from finance.payment_voucher v
join finance.payment_voucher_line vl using (voucher_id)
left join finance.vendor vd on vd.vendor_id = v.payee_vendor_id
where not v.has_invoice and v.status <> 'VOID'
group by v.voucher_id, v.voucher_no, vd.vendor_name
having sum(vl.amount_incl_vat) >= coalesce((select setting_value::numeric from ref.app_setting where setting_key = 'no_invoice_threshold'), 200000);

-- EXP-02 Capex lines that were not capitalised as a fixed asset.
create or replace view ctl.v_chk_exp_02_capex_without_asset (entity_type, entity_id, entity_ref, detail) as
select 'VOUCHER_LINE'::text, vl.voucher_line_id, v.voucher_no || '/' || vl.line_no,
       jsonb_build_object('account', vl.account_code, 'amount', vl.amount_incl_vat)
from finance.payment_voucher_line vl
join finance.payment_voucher v using (voucher_id)
join finance.gl_account g on g.account_code = vl.account_code
where g.is_capex and v.status <> 'VOID'
  and not exists (select 1 from finance.fixed_asset fa where fa.voucher_line_id = vl.voucher_line_id);

-- EXP-03 Expense lines coded to header / non-expense accounts or inactive cost centres (unclassified spend).
create or replace view ctl.v_chk_exp_03_miscoded (entity_type, entity_id, entity_ref, detail) as
select 'VOUCHER_LINE'::text, vl.voucher_line_id, v.voucher_no || '/' || vl.line_no,
       jsonb_build_object('account', vl.account_code, 'account_class', g.account_class, 'postable', g.is_postable,
                          'cost_center', vl.cost_center_code, 'cost_center_active', cc.is_active)
from finance.payment_voucher_line vl
join finance.payment_voucher v using (voucher_id)
join finance.gl_account g on g.account_code = vl.account_code
join finance.cost_center cc on cc.cost_center_code = vl.cost_center_code
where v.status <> 'VOID'
  and (not g.is_postable or g.account_class not in ('EXPENSE','CONTRA_REVENUE') or not cc.is_active);

-- REP-01 Revenue completeness (BR-10): a finished enrolment has earned exactly its contract value.
create or replace view ctl.v_chk_rep_01_revenue_completeness (entity_type, entity_id, entity_ref, detail) as
select 'ENROLLMENT'::text, b.enrollment_id, b.enrollment_code,
       jsonb_build_object('contract_value', b.net_payable, 'recognised', b.recognised_total)
from rpt.v_enrollment_balance b
join academic.class c on c.class_id = b.class_id
where b.status_code = 'COMPLETED' and coalesce(c.actual_end_date, c.planned_end_date) < ref.as_of_date()
  and b.recognised_total <> b.net_payable;

-- ACA-03 Open or running classes without a lead teacher (BR-11: inconsistent assignments).
create or replace view ctl.v_chk_aca_03_no_teacher (entity_type, entity_id, entity_ref, detail) as
select 'CLASS'::text, c.class_id, c.class_code, jsonb_build_object('start_date', c.start_date, 'status', c.lifecycle_status)
from academic.class c
where c.lifecycle_status in ('PLANNED', 'OPEN', 'RUNNING')
  and coalesce(c.actual_end_date, c.planned_end_date) >= ref.as_of_date()
  and not exists (select 1 from academic.class_staff_assignment a where a.class_id = c.class_id and a.assignment_role = 'LEAD_TEACHER'
                    and (a.effective_to is null or a.effective_to > ref.as_of_date()));

-- BIL-09 Daily cash close: days with cash receipts and no close, and closes with an unexplained difference.
create or replace view ctl.v_chk_bil_09_cash_close (entity_type, entity_id, entity_ref, detail) as
select 'COLLECTOR_DAY'::text, (r.collected_by * 100000000 + to_char(r.receipt_date, 'YYYYMMDD')::bigint), e.name_code || ' ' || r.receipt_date,
       jsonb_build_object('receipt_date', r.receipt_date, 'cash_receipts', sum(r.amount), 'issue', 'Day not closed')
from billing.receipt r join hr.employee e on e.employee_id = r.collected_by
where r.status = 'ISSUED' and r.payment_method_code = 'CASH' and r.receipt_date < ref.as_of_date()
  and r.receipt_date >= ref.as_of_date() - 30
  and not exists (select 1 from app.cash_close k where k.close_date = r.receipt_date and k.collector_id = r.collected_by)
group by r.collected_by, r.receipt_date, e.name_code
union all
select 'CASH_CLOSE', k.cash_close_id, e.name_code || ' ' || k.close_date,
       jsonb_build_object('receipt_date', k.close_date, 'expected_cash', k.expected_cash, 'counted_cash', k.counted_cash,
                          'difference', k.difference, 'issue', 'Difference not reviewed')
from app.cash_close k join hr.employee e on e.employee_id = k.collector_id
where k.difference <> 0 and k.reviewed_at is null;
