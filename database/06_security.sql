/* =====================================================================================
   06_security.sql - who may do what, enforced by the database itself
   -------------------------------------------------------------------------------------
   The application signs people in and shows each role its own workspace. The database does not trust the application for
   that: every transaction runs under one of five NOLOGIN group roles, and the grants below decide what each can read,
   which tables it may write directly, and which business actions (functions) it may execute.

     ami_learning_advisor   staff - sales and receipts (leads, placement tests, enrolments, receipts, daily cash close)
     ami_academic_manager   courses, classes, timetables, teacher assignment, session confirmation
     ami_hr_manager         staff, pay rates, shifts, payroll runs and payslips
     ami_finance_manager    prices, discounts and voids approval, refunds, write-offs, expenses, assets, period close
     ami_director           read-only access to everything (optional)

   The application logs in as ami_app (NOINHERIT: it has no rights of its own) and switches with
       SET LOCAL ROLE ami_<role>;  SELECT set_config('ami.app_user', '<username>', true), set_config('ami.app_role', '<ROLE>', true);
   at the start of each transaction. Business actions are SECURITY DEFINER functions with a pinned search_path, so a role can
   perform an action (e.g. record a receipt) without being able to write the underlying tables directly (e.g. edit a receipt).
   The password of ami_app is set at deployment time (deploy/supabase_setup.sql), never in this repository.
   ===================================================================================== */

/* ------------------------------------------------------------------ 1. roles */
do $$
declare r text;
begin
    foreach r in array array['ami_learning_advisor','ami_academic_manager','ami_hr_manager','ami_finance_manager','ami_director'] loop
        if not exists (select 1 from pg_roles where rolname = r) then
            execute format('create role %I nologin', r);
        end if;
    end loop;
    if not exists (select 1 from pg_roles where rolname = 'ami_app') then
        create role ami_app nologin noinherit;
    end if;
end $$;
grant ami_learning_advisor, ami_academic_manager, ami_hr_manager, ami_finance_manager, ami_director to ami_app;

/* ------------------------------------------------------------------ 2. start from nothing */
do $$
declare s text;
begin
    foreach s in array array['ref','crm','academic','billing','hr','payroll','finance','rpt','ctl','app'] loop
        execute format('revoke all on schema %I from public', s);
        execute format('revoke all on all tables in schema %I from public', s);
        execute format('revoke all on all functions in schema %I from public', s);
        execute format('alter default privileges in schema %I revoke execute on functions from public', s);
        -- Supabase API roles never see the operating data
        if exists (select 1 from pg_roles where rolname = 'anon') then
            execute format('revoke all on schema %I from anon, authenticated', s);
            execute format('revoke all on all tables in schema %I from anon, authenticated', s);
        end if;
    end loop;
end $$;

/* ------------------------------------------------------------------ 3. business actions run with the owner's rights */
-- Every function that writes data becomes SECURITY DEFINER with a pinned search_path. Read-only helpers stay invoker.
do $$
declare f record;
begin
    for f in
        select p.oid::regprocedure as sig
        from pg_proc p join pg_namespace n on n.oid = p.pronamespace
        where n.nspname in ('crm','academic','billing','hr','payroll','finance','ctl','app','ref')
          and p.prokind = 'f'
          and (n.nspname || '.' || p.proname) not in (
              'ref.as_of_date', 'finance.period_of', 'finance.months_inclusive', 'billing.current_price', 'billing.fee_amount',
              'finance.earning_account', 'payroll.hourly_rate', 'academic.make_class_code', 'app.current_app_role', 'app.can_see_control')
    loop
        execute format('alter function %s security definer set search_path = pg_catalog, pg_temp', f.sig);
    end loop;
end $$;

/* ------------------------------------------------------------------ 4. what every role can see */
grant usage on schema ref, crm, academic, billing, hr, payroll, finance, rpt, ctl, app
   to ami_learning_advisor, ami_academic_manager, ami_hr_manager, ami_finance_manager, ami_director;
grant select on all tables in schema ref to ami_learning_advisor, ami_academic_manager, ami_hr_manager, ami_finance_manager, ami_director;
grant select on finance.fiscal_period, hr.employee, hr.employee_role
   to ami_learning_advisor, ami_academic_manager, ami_hr_manager, ami_finance_manager, ami_director;
grant select on ctl.control, ctl.control_run to ami_learning_advisor, ami_academic_manager, ami_hr_manager, ami_finance_manager, ami_director;
grant select on ctl.control_exception to ami_learning_advisor, ami_academic_manager, ami_hr_manager, ami_finance_manager, ami_director;
grant update (status, assigned_to, resolved_at, resolution_note) on ctl.control_exception
   to ami_learning_advisor, ami_academic_manager, ami_hr_manager, ami_finance_manager;
grant execute on function ref.as_of_date(), finance.period_of(date), finance.months_inclusive(date, date),
      billing.current_price(smallint, text, text, date), billing.fee_amount(text, date), academic.make_class_code(smallint, date),
      payroll.hourly_rate(bigint, date), finance.earning_account(text, text, text, text),   -- read-only helpers used inside views
      ctl.run_control(text, bigint), ctl.run_all_controls(), app.run_daily_jobs(date)
   to ami_learning_advisor, ami_academic_manager, ami_hr_manager, ami_finance_manager, ami_director;
grant usage on schema app, ref to ami_app;                                     -- before sign-in: business date + password check
grant execute on function app.authenticate(text, text), ref.as_of_date() to ami_app;
grant select (setting_key, setting_value) on ref.app_setting to ami_app;

/* ------------------------------------------------------------------ 5. Learning Advisor (staff: sales + receipts) */
grant select on all tables in schema crm to ami_learning_advisor;
grant insert, update on crm.student, crm.guardian, crm.student_guardian, crm.student_availability, crm.lead, crm.lead_activity,
      crm.placement_test, crm.placement_test_score to ami_learning_advisor;
grant delete on crm.student_availability, crm.student_guardian, crm.placement_test_score to ami_learning_advisor;
grant select on academic.class, academic.class_meeting_pattern, academic.class_session, academic.room,
      academic.class_staff_assignment to ami_learning_advisor;
grant select on all tables in schema billing to ami_learning_advisor;          -- read only: writes go through the functions below
grant insert on billing.group_registration to ami_learning_advisor;            -- siblings / friends registering together
grant select on app.cash_close to ami_learning_advisor;
grant select on rpt.v_class_status, rpt.v_lead_funnel, rpt.v_funnel_summary, rpt.v_enrollment_pricing, rpt.v_schedule_line_status,
      rpt.v_enrollment_balance, rpt.v_class_roster to ami_learning_advisor;
grant execute on function
      billing.enrol(bigint, smallint, text, bigint, text, date, bigint, bigint, text[], bigint, numeric, smallint, text, text),
      billing.assign_class(bigint, bigint, bigint, date),
      billing.change_enrollment_status(bigint, text, date, text),
      billing.record_receipt(bigint, bigint, date, numeric, text, bigint, text, bigint, text),
      billing.request_receipt_void(bigint, bigint, text),
      billing.apply_receipt(bigint, bigint),
      app.close_cash(date, bigint, numeric, text)
   to ami_learning_advisor;

/* ------------------------------------------------------------------ 6. Academic Manager */
grant select on all tables in schema crm to ami_academic_manager;
grant select on billing.enrollment, billing.enrollment_status_history to ami_academic_manager;
grant select, insert, update, delete on all tables in schema academic to ami_academic_manager;
grant insert, update on ref.course, ref.proficiency_level to ami_academic_manager;
grant select on rpt.v_class_status, rpt.v_teaching_hours, rpt.v_class_roster to ami_academic_manager;
grant execute on function
      academic.open_class(smallint, text, date, smallint, smallint, jsonb, bigint, bigint, smallint, numeric, text),
      academic.confirm_session(bigint, boolean, bigint, numeric),
      academic.generate_sessions(bigint),
      academic.add_make_up_session(bigint, date, time, time, smallint),
      academic.cancel_class(bigint, text),
      academic.sync_class_statuses(date),
      billing.assign_class(bigint, bigint, bigint, date),
      billing.sync_enrollment_statuses(date)
   to ami_academic_manager;

/* ------------------------------------------------------------------ 7. HR Manager */
grant select, insert, update, delete on all tables in schema hr to ami_hr_manager;
grant select, insert, update, delete on payroll.payroll_line, payroll.payroll_run to ami_hr_manager;
grant select on all tables in schema payroll to ami_hr_manager;
grant insert, update on payroll.commission_rule, payroll.pit_rule, payroll.statutory_deduction_rule to ami_hr_manager;
grant insert, update on ref.salary_code, ref.salary_rate to ami_hr_manager;
grant select on academic.class, academic.class_session, academic.session_staff, academic.class_staff_assignment, academic.room
   to ami_hr_manager;
grant select on billing.enrollment, finance.cost_center, finance.earning_account_map to ami_hr_manager;
grant select on rpt.v_payroll_register, rpt.v_teaching_hours to ami_hr_manager;
grant execute on function payroll.hourly_rate(bigint, date), finance.earning_account(text, text, text, text),
      payroll.calculate_run(bigint), payroll.approve_run(bigint, bigint), payroll.mark_run_paid(bigint, date)
   to ami_hr_manager;

/* ------------------------------------------------------------------ 8. Finance Manager (everything else) */
grant select on all tables in schema ref, crm, academic, billing, hr, payroll, finance, rpt, ctl, app to ami_finance_manager;
grant insert, update, delete on all tables in schema finance to ami_finance_manager;
grant insert, update on ref.course_price, ref.discount_programme, ref.fee, ref.app_setting, ref.payment_plan, ref.payment_plan_line,
      ref.group_discount_tier, ref.vat_group to ami_finance_manager;
grant insert, update on billing.group_registration to ami_finance_manager;
grant execute on all functions in schema billing, finance, app to ami_finance_manager;
revoke execute on function app.set_password(text, text) from ami_finance_manager;
grant execute on function payroll.hourly_rate(bigint, date), payroll.mark_run_paid(bigint, date) to ami_finance_manager;   -- Finance pays salaries

/* ------------------------------------------------------------------ 9. Director (read only) */
grant select on all tables in schema ref, crm, academic, billing, hr, payroll, finance, rpt, ctl, app to ami_director;

/* ------------------------------------------------------------------ 10. control exceptions: each role works its own queue */
create or replace function app.current_app_role() returns text language sql stable as $$
    select case current_user::text
                when 'ami_learning_advisor' then 'LEARNING_ADVISOR'
                when 'ami_academic_manager' then 'ACADEMIC_MANAGER'
                when 'ami_hr_manager'       then 'HR_MANAGER'
                when 'ami_finance_manager'  then 'FINANCE_MANAGER'
                when 'ami_director'         then 'DIRECTOR'
                else 'OWNER' end                    -- database owner, migrations, scheduled jobs
$$;
create or replace function app.can_see_control(p_control_code text) returns boolean language sql stable as $$
    select app.current_app_role() in ('FINANCE_MANAGER', 'DIRECTOR', 'OWNER')
        or exists (select 1 from ctl.control c where c.control_code = p_control_code and c.app_role_code = app.current_app_role())
$$;
grant execute on function app.current_app_role(), app.can_see_control(text)
   to ami_learning_advisor, ami_academic_manager, ami_hr_manager, ami_finance_manager, ami_director;
alter table ctl.control_exception enable row level security;
drop policy if exists exception_by_role on ctl.control_exception;
create policy exception_by_role on ctl.control_exception for all
    using (app.can_see_control(control_code)) with check (app.can_see_control(control_code));
