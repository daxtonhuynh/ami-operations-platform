/* =====================================================================================
   02_functions.sql - business rules of the legacy workbooks, implemented once in the database
   ===================================================================================== */

/* ------------------------------------------------------------------ helpers */

-- Reporting reference date: ref.app_setting('as_of_date') or today (legacy: TODAY()).
create or replace function ref.as_of_date() returns date language sql stable as $$
    select coalesce((select nullif(setting_value, '')::date from ref.app_setting where setting_key = 'as_of_date'), current_date)
$$;

-- YYYYMM period id of a date.
create or replace function finance.period_of(p_date date) returns integer language sql immutable as $$
    select extract(year from p_date)::int * 100 + extract(month from p_date)::int
$$;

-- Create the monthly periods between two dates if they do not exist yet.
create or replace function finance.ensure_periods(p_from date, p_to date) returns integer language plpgsql security definer
set search_path = pg_catalog, pg_temp as $$
declare d date := date_trunc('month', p_from)::date; n integer := 0;
begin
    while d <= p_to loop
        insert into finance.fiscal_period (period_id, period_start, period_end, fiscal_year)
        values (finance.period_of(d), d, (d + interval '1 month - 1 day')::date, extract(year from d)::smallint)
        on conflict (period_id) do nothing;
        n := n + 1;
        d := (d + interval '1 month')::date;
    end loop;
    return n;
end $$;

-- Months between two dates, counting both end months (legacy: DATEDIF(...,"m")+1).
create or replace function finance.months_inclusive(p_from date, p_to date) returns integer language sql immutable as $$
    select (extract(year from p_to)::int * 12 + extract(month from p_to)::int)
         - (extract(year from p_from)::int * 12 + extract(month from p_from)::int) + 1
$$;

/* ------------------------------------------------------------------ academic */

-- Generate the class sessions from the weekly meeting pattern, starting on start_date (legacy: schedule written by hand).
create or replace function academic.generate_sessions(p_class_id bigint) returns integer language plpgsql as $$
declare
    c academic.class%rowtype; d date; n integer := 0; p record;
begin
    select * into c from academic.class where class_id = p_class_id;
    if not found then raise exception 'Class % not found', p_class_id; end if;
    if exists (select 1 from academic.session_staff ss join academic.class_session s using (session_id) where s.class_id = p_class_id) then
        raise exception 'Class % already has confirmed hours; sessions cannot be regenerated', c.class_code;
    end if;
    delete from academic.class_session where class_id = p_class_id;
    d := c.start_date;
    while n < c.total_sessions loop
        if not exists (select 1 from academic.closure_day where closure_date = d) then      -- public holidays, Tet
            for p in select * from academic.class_meeting_pattern
                     where class_id = p_class_id and weekday = extract(isodow from d) order by start_time loop
                exit when n >= c.total_sessions;
                n := n + 1;
                insert into academic.class_session (class_id, session_no, session_date, start_time, end_time, room_id)
                values (p_class_id, n, d, p.start_time, p.end_time, c.room_id);
            end loop;
        end if;
        d := d + 1;
        if d > c.start_date + 730 then raise exception 'Class % has no meeting pattern', c.class_code; end if;
    end loop;
    update academic.class set planned_end_date = (select max(session_date) from academic.class_session where class_id = p_class_id)
    where class_id = p_class_id;
    return n;
end $$;

/* ------------------------------------------------------------------ billing: pricing engine */

-- Price-list row valid for a course, delivery mode and date.
create or replace function billing.current_price(p_course_id smallint, p_mode text, p_basis text, p_on date)
returns ref.course_price language sql stable as $$
    select * from ref.course_price
    where course_id = p_course_id and delivery_mode_code = p_mode and price_basis = p_basis
      and p_on >= effective_from and (effective_to is null or p_on < effective_to)
$$;

-- Fee amount valid on a date.
create or replace function billing.fee_amount(p_fee_code text, p_on date) returns numeric language sql stable as $$
    select coalesce((select amount from ref.fee where fee_code = p_fee_code and p_on >= effective_from
                     and (effective_to is null or p_on < effective_to)), 0)
$$;

-- Rebuild the itemised charges of an enrolment and return the net amount payable.
-- Legacy rule (Qualified Leads): Total = (1 - disc1% - disc2% - disc3%) x list price - group discount (+ materials fee for instalment plans).
create or replace function billing.price_enrollment(p_enrollment_id bigint) returns numeric language plpgsql as $$
declare e billing.enrollment%rowtype; v_materials numeric; v_net numeric; d record; t record;
begin
    select * into e from billing.enrollment where enrollment_id = p_enrollment_id;
    if not found then raise exception 'Enrolment % not found', p_enrollment_id; end if;
    delete from billing.enrollment_charge where enrollment_id = p_enrollment_id and charge_type <> 'ADJUSTMENT';  -- manual adjustments survive re-pricing

    insert into billing.enrollment_charge (enrollment_id, charge_type, description, amount)
    values (p_enrollment_id, 'TUITION', 'List price', e.list_price);

    for d in select * from billing.enrollment_discount where enrollment_id = p_enrollment_id order by seq loop
        insert into billing.enrollment_charge (enrollment_id, charge_type, description, amount)
        values (p_enrollment_id, 'DISCOUNT', 'Discount ' || d.seq || ': ' || d.discount_code,
                -case d.discount_kind when 'PERCENT' then round(e.list_price * d.discount_value, 0) else d.discount_value end);
    end loop;

    if e.group_id is not null then
        select t2.* into t from billing.group_registration g join ref.group_discount_tier t2 using (tier_code) where g.group_id = e.group_id;
        insert into billing.enrollment_charge (enrollment_id, charge_type, description, amount)
        values (p_enrollment_id, 'GROUP_DISCOUNT', 'Group registration (' || t.tier_code || ')', -t.discount_amount);
    end if;

    if (select materials_fee_applies from ref.payment_plan where plan_code = e.plan_code) then
        v_materials := billing.fee_amount('MATERIALS', e.enrolled_on);
        if v_materials > 0 then
            insert into billing.enrollment_charge (enrollment_id, charge_type, description, amount)
            values (p_enrollment_id, 'MATERIALS_FEE', 'Learning materials', v_materials);
        end if;
    end if;

    select sum(amount) into v_net from billing.enrollment_charge where enrollment_id = p_enrollment_id;
    if v_net < 0 then raise exception 'Enrolment % would have a negative price (%)', p_enrollment_id, v_net; end if;
    return v_net;
end $$;

-- Build the payment schedule from the plan template:
--   seq 0 DEPOSIT (optional) -> MATERIALS_FEE (if charged) -> FULL_PAYMENT or INSTALMENT lines splitting the tuition balance.
create or replace function billing.generate_payment_schedule(p_enrollment_id bigint, p_deposit numeric default null)
returns integer language plpgsql as $$
declare
    e billing.enrollment%rowtype; v_base date; v_net numeric; v_materials numeric; v_balance numeric;
    v_seq smallint := 0; v_remaining numeric; v_amount numeric; v_count integer; v_i integer := 0; l record;
begin
    select * into e from billing.enrollment where enrollment_id = p_enrollment_id;
    if exists (select 1 from billing.payment_allocation a join billing.payment_schedule s using (schedule_line_id)
               where s.enrollment_id = p_enrollment_id) then
        raise exception 'Enrolment % already has payments allocated; adjust the schedule manually', p_enrollment_id;
    end if;
    delete from billing.payment_schedule where enrollment_id = p_enrollment_id;

    select coalesce(sum(amount),0) into v_net from billing.enrollment_charge where enrollment_id = p_enrollment_id;
    if v_net = 0 then v_net := billing.price_enrollment(p_enrollment_id); end if;
    select coalesce(sum(amount),0) into v_materials from billing.enrollment_charge
    where enrollment_id = p_enrollment_id and charge_type = 'MATERIALS_FEE';
    v_base := coalesce((select start_date from academic.class where class_id = e.class_id), e.enrolled_on);
    v_balance := v_net - v_materials - coalesce(p_deposit, 0);
    if v_balance < 0 then raise exception 'Deposit exceeds the tuition payable for enrolment %', p_enrollment_id; end if;

    if coalesce(p_deposit, 0) > 0 then
        insert into billing.payment_schedule (enrollment_id, seq, line_type, label, due_date, amount_due)
        values (p_enrollment_id, v_seq, 'DEPOSIT', 'Seat deposit', e.enrolled_on, p_deposit);
    end if;
    if v_materials > 0 then
        v_seq := v_seq + 1;
        insert into billing.payment_schedule (enrollment_id, seq, line_type, label, due_date, amount_due)
        values (p_enrollment_id, v_seq, 'MATERIALS_FEE', 'Learning materials', v_base, v_materials);
    end if;

    select count(*) into v_count from ref.payment_plan_line where plan_code = e.plan_code;
    v_remaining := v_balance;
    for l in select * from ref.payment_plan_line where plan_code = e.plan_code order by seq loop
        v_i := v_i + 1;
        v_amount := case when v_i = v_count then v_remaining else round(v_balance * l.share_pct, -3) end;  -- last line absorbs rounding
        v_remaining := v_remaining - v_amount;
        if v_amount > 0 then
            v_seq := v_seq + 1;
            insert into billing.payment_schedule (enrollment_id, seq, line_type, label, due_date, amount_due)
            values (p_enrollment_id, v_seq, case when e.plan_code = 'FULL' then 'FULL_PAYMENT' else 'INSTALMENT' end,
                    l.label, (v_base + make_interval(months => l.due_offset_months))::date, v_amount);
        end if;
    end loop;
    return v_seq;
end $$;

-- Allocate a receipt to the open schedule lines of an enrolment, oldest due first (FIFO).
create or replace function billing.allocate_receipt(p_receipt_id bigint, p_enrollment_id bigint) returns numeric language plpgsql as $$
declare v_left numeric; l record; v_open numeric; v_take numeric;
begin
    select r.amount - coalesce((select sum(amount) from billing.payment_allocation a where a.receipt_id = r.receipt_id), 0)
      into v_left from billing.receipt r where r.receipt_id = p_receipt_id;
    for l in select s.schedule_line_id, s.amount_due - coalesce(sum(a.amount),0) as open_amount
             from billing.payment_schedule s left join billing.payment_allocation a using (schedule_line_id)
             where s.enrollment_id = p_enrollment_id
             group by s.schedule_line_id, s.amount_due, s.due_date, s.seq
             having s.amount_due - coalesce(sum(a.amount),0) > 0
             order by s.due_date, s.seq loop
        exit when v_left <= 0;
        v_take := least(v_left, l.open_amount);
        insert into billing.payment_allocation (receipt_id, schedule_line_id, amount) values (p_receipt_id, l.schedule_line_id, v_take);
        v_left := v_left - v_take;
    end loop;
    return v_left;   -- unapplied cash (should be 0; otherwise caught by control BIL-04)
end $$;

/* ------------------------------------------------------------------ billing: revenue recognition */

-- Revenue recognition of one enrolment (spec section 8, BR-09, BR-10). The contract value - net tuition after discounts and
-- adjustments - is earned in equal monthly amounts from the class start month (or the enrolment month for a learner who joins a
-- running class) to the class end month, whatever the payment
-- plan and whenever the cash arrives. The materials fee is earned in the class start month. Months already closed are final:
-- a rebuild only rewrites open months and spreads whatever is left over them.
--   * no class yet, waiting list, deferred: nothing new is earned (cash stays deferred);
--   * dropped out: earned up to and including the drop month; payments kept beyond that are FORFEIT revenue in the drop month
--     (app setting 'dropout_payment_policy' = FORFEIT, the centre's non-refundable rule) unless Finance refunds them;
--   * cancelled before the start: nothing is earned; kept payments (e.g. the seat deposit) are forfeited the same way.
create or replace function billing.build_revenue_schedule(p_enrollment_id bigint) returns integer language plpgsql security definer
set search_path = pg_catalog, pg_temp as $$
declare
    e record; v_account text; v_first_open date; v_policy text;
    v_tuition numeric; v_materials numeric; v_locked_t numeric; v_locked_m numeric; v_locked_f numeric;
    v_svc_start date; v_svc_end date; v_end date; v_total int; v_served int; v_target_t numeric; v_target_m numeric;
    v_from date; v_months int; v_left numeric; v_amt numeric; v_n int := 0; v_collected numeric; v_refunded numeric; v_forfeit numeric;
    v_event date;
begin
    select en.enrollment_id, en.status_code, en.status_changed_on, en.delivery_mode_code, co.programme_code,
           greatest(c.start_date, en.enrolled_on) as start_date, coalesce(c.actual_end_date, c.planned_end_date) as end_date
      into e
      from billing.enrollment en
      join ref.course co on co.course_id = en.course_id
      left join academic.class c on c.class_id = en.class_id
     where en.enrollment_id = p_enrollment_id;
    if not found then raise exception 'Enrolment % not found', p_enrollment_id; end if;

    select account_code into v_account from finance.revenue_account_map
     where programme_code = e.programme_code and delivery_mode_code = e.delivery_mode_code;
    v_policy := coalesce((select setting_value from ref.app_setting where setting_key = 'dropout_payment_policy'), 'FORFEIT');

    delete from billing.revenue_schedule rs using finance.fiscal_period p
     where rs.enrollment_id = p_enrollment_id and p.period_id = rs.period_id and p.status = 'OPEN';

    select coalesce(sum(amount) filter (where line_type = 'TUITION'), 0), coalesce(sum(amount) filter (where line_type = 'MATERIALS'), 0),
           coalesce(sum(amount) filter (where line_type = 'FORFEIT'), 0)
      into v_locked_t, v_locked_m, v_locked_f
      from billing.revenue_schedule where enrollment_id = p_enrollment_id;

    select coalesce(sum(amount) filter (where charge_type = 'MATERIALS_FEE'), 0),
           coalesce(sum(amount) filter (where charge_type <> 'MATERIALS_FEE'), 0)
      into v_materials, v_tuition
      from billing.enrollment_charge where enrollment_id = p_enrollment_id;

    -- service window and the amount earned in it
    v_target_t := 0; v_target_m := 0;
    if e.start_date is not null and e.status_code not in ('WAITLISTED', 'DEFERRED', 'CANCELLED') then
        v_svc_start := date_trunc('month', e.start_date)::date;
        v_svc_end   := date_trunc('month', e.end_date)::date;
        v_total     := finance.months_inclusive(v_svc_start, v_svc_end);
        if e.status_code = 'DROPPED' then
            v_end := least(date_trunc('month', e.status_changed_on)::date, v_svc_end);
            v_served := case when v_end < v_svc_start then 0 else finance.months_inclusive(v_svc_start, v_end) end;
            v_svc_end := v_end;
        else
            v_served := v_total;
        end if;
        v_target_t := round(v_tuition * v_served / v_total, 0);
        v_target_m := case when v_served > 0 then v_materials else 0 end;
        if v_served > 0 then
            perform finance.ensure_periods(v_svc_start, v_svc_end);
        end if;
    end if;

    select min(period_start) into v_first_open from finance.fiscal_period where status = 'OPEN';
    if v_first_open is null then
        perform finance.ensure_periods(current_date, current_date);
        select min(period_start) into v_first_open from finance.fiscal_period where status = 'OPEN';
    end if;

    -- tuition: what is left of the target, straight line over the open months of the window (catch-up in the first open month)
    v_left := v_target_t - v_locked_t;
    if v_left <> 0 then
        if v_svc_start is not null and v_served > 0 and v_svc_end >= v_first_open then
            v_from := greatest(v_svc_start, v_first_open);
            v_months := finance.months_inclusive(v_from, v_svc_end);
        else
            v_from := v_first_open; v_months := 1;
        end if;
        v_amt := v_left;
        for i in 1 .. v_months loop
            v_amt := case when i = v_months then v_left else round((v_target_t - v_locked_t) / v_months, 0) end;
            v_left := v_left - v_amt;
            if v_amt <> 0 then
                insert into billing.revenue_schedule (enrollment_id, period_id, line_type, account_code, amount)
                values (p_enrollment_id, finance.period_of((v_from + make_interval(months => i - 1))::date), 'TUITION', v_account, v_amt);
                v_n := v_n + 1;
            end if;
        end loop;
    end if;

    -- materials: in the class start month (or the first open month if that is closed)
    if v_target_m - v_locked_m <> 0 then
        insert into billing.revenue_schedule (enrollment_id, period_id, line_type, account_code, amount)
        values (p_enrollment_id, finance.period_of(greatest(coalesce(v_svc_start, v_first_open), v_first_open)), 'MATERIALS', v_account, v_target_m - v_locked_m);
        v_n := v_n + 1;
    end if;

    -- forfeited payments after a drop-out or cancellation
    if e.status_code in ('DROPPED', 'CANCELLED') and v_policy = 'FORFEIT' then
        select coalesce(sum(a.amount), 0) into v_collected
          from billing.payment_allocation a
          join billing.receipt r on r.receipt_id = a.receipt_id and r.status = 'ISSUED'
          join billing.payment_schedule s on s.schedule_line_id = a.schedule_line_id
         where s.enrollment_id = p_enrollment_id;
        select coalesce(sum(amount), 0) into v_refunded from billing.refund where enrollment_id = p_enrollment_id;
        v_forfeit := greatest(v_collected - v_refunded - v_target_t - v_target_m, 0) - v_locked_f;
        if v_forfeit <> 0 then
            v_event := greatest(date_trunc('month', e.status_changed_on)::date, v_first_open);
            perform finance.ensure_periods(v_event, v_event);
            insert into billing.revenue_schedule (enrollment_id, period_id, line_type, account_code, amount)
            values (p_enrollment_id, finance.period_of(v_event), 'FORFEIT', v_account, v_forfeit);
            v_n := v_n + 1;
        end if;
    end if;
    return v_n;
end $$;

-- Move enrolments along their life cycle from the class dates: registered -> active (class started) -> completed (class ended).
create or replace function billing.sync_enrollment_statuses(p_as_of date default null) returns integer language plpgsql as $$
declare v_as_of date := coalesce(p_as_of, ref.as_of_date()); n integer;
begin
    with target as (
        select e.enrollment_id,
               case when c.start_date > v_as_of then 'REGISTERED'
                    when coalesce(c.actual_end_date, c.planned_end_date) < v_as_of then 'COMPLETED'
                    else 'ACTIVE' end as status_code,
               case when c.start_date > v_as_of then e.enrolled_on
                    when coalesce(c.actual_end_date, c.planned_end_date) < v_as_of then coalesce(c.actual_end_date, c.planned_end_date)
                    else c.start_date end as changed_on
        from billing.enrollment e join academic.class c on c.class_id = e.class_id
        where e.status_code in ('WAITLISTED', 'REGISTERED', 'ACTIVE', 'COMPLETED'))
    update billing.enrollment e set status_code = t.status_code, status_changed_on = t.changed_on
      from target t where t.enrollment_id = e.enrollment_id and t.status_code <> e.status_code;
    get diagnostics n = row_count;
    return n;
end $$;

/* ------------------------------------------------------------------ billing: application API (one call per business action) */

-- Enrol a student (Sales). Looks up the price valid on the enrolment date, applies up to three discounts, sends discounts outside
-- policy to the Finance Manager for approval, prices the enrolment, builds the payment schedule and the revenue schedule, and
-- marks the lead as converted. The class is optional: without one the learner waits for a class to open.
create or replace function billing.enrol(
    p_student_id bigint, p_course_id smallint, p_delivery_mode text, p_class_id bigint, p_plan_code text,
    p_enrolled_on date, p_sales_owner bigint, p_lead_id bigint default null, p_discount_codes text[] default '{}',
    p_group_id bigint default null, p_deposit numeric default null, p_output_level_id smallint default null,
    p_notes text default null, p_documents_url text default null) returns bigint language plpgsql as $$
declare
    v_price ref.course_price; v_status text; v_id bigint; v_i int := 0; v_code text; d ref.discount_programme;
    v_threshold numeric; v_total_pct numeric := 0; c academic.class;
begin
    select * into v_price from billing.current_price(p_course_id, p_delivery_mode, 'FULL_COURSE', p_enrolled_on);
    if v_price.course_price_id is null then
        raise exception 'No price list entry for this course and delivery mode on %', p_enrolled_on;
    end if;
    if p_class_id is not null then
        select * into c from academic.class where class_id = p_class_id;
        if c.lifecycle_status = 'CANCELLED' then raise exception 'Class % is cancelled', c.class_code; end if;
        if (select count(*) from billing.enrollment where class_id = p_class_id
             and status_code in ('WAITLISTED','REGISTERED','ACTIVE')) >= c.capacity then
            raise exception 'Class % is full (% seats)', c.class_code, c.capacity;
        end if;
        v_status := case when c.start_date > p_enrolled_on then 'REGISTERED'
                         when coalesce(c.actual_end_date, c.planned_end_date) < p_enrolled_on then 'COMPLETED' else 'ACTIVE' end;
    else
        v_status := 'WAITLISTED';
    end if;
    if coalesce(array_length(p_discount_codes, 1), 0) > 3 then
        raise exception 'At most three discounts can be stacked';
    end if;

    insert into billing.enrollment (student_id, lead_id, course_id, delivery_mode_code, class_id, enrolled_on, sales_owner_employee_id,
                                    plan_code, course_price_id, list_price, group_id, output_commitment_level_id, status_code,
                                    status_changed_on, class_assigned_by, class_assigned_at, notes, documents_url)
    values (p_student_id, p_lead_id, p_course_id, p_delivery_mode, p_class_id, p_enrolled_on, p_sales_owner, p_plan_code,
            v_price.course_price_id, v_price.amount, p_group_id, p_output_level_id, v_status, p_enrolled_on,
            case when p_class_id is not null then p_sales_owner end, case when p_class_id is not null then now() end,
            p_notes, p_documents_url)
    returning enrollment_id into v_id;

    v_threshold := coalesce((select setting_value::numeric from ref.app_setting where setting_key = 'discount_approval_threshold'), 0.30);
    select coalesce(sum(case when discount_kind = 'PERCENT' then discount_value else discount_value / v_price.amount end), 0)
      into v_total_pct from ref.discount_programme where discount_code = any (p_discount_codes);
    foreach v_code in array coalesce(p_discount_codes, '{}') loop
        select * into d from ref.discount_programme where discount_code = v_code;
        if d.discount_code is null then raise exception 'Unknown discount %', v_code; end if;
        if p_enrolled_on < d.valid_from or (d.valid_to is not null and p_enrolled_on > d.valid_to) then
            raise exception 'Discount % is not valid on %', d.name, p_enrolled_on;
        end if;
        v_i := v_i + 1;
        insert into billing.enrollment_discount (enrollment_id, seq, discount_code, discount_kind, discount_value, approval_status, requested_by)
        values (v_id, v_i, d.discount_code, d.discount_kind, d.discount_value,
                case when d.requires_approval or v_total_pct > v_threshold then 'PENDING' else 'NOT_REQUIRED' end, p_sales_owner);
    end loop;

    perform billing.price_enrollment(v_id);
    perform billing.generate_payment_schedule(v_id, p_deposit);
    perform billing.build_revenue_schedule(v_id);
    if p_lead_id is not null then
        update crm.lead set qualification_code = 'CONVERTED', consultation_outcome_code = 'SUCCESS',
               closed_on = coalesce(closed_on, p_enrolled_on), next_follow_up_on = null
         where lead_id = p_lead_id;
    end if;
    return v_id;
end $$;

-- Assign (or move) an enrolment to a class of the same course (Sales). The learner appears on the class roster at once (BR-03).
create or replace function billing.assign_class(p_enrollment_id bigint, p_class_id bigint, p_by bigint, p_as_of date default null)
returns void language plpgsql as $$
declare e billing.enrollment; c academic.class; v_as_of date := coalesce(p_as_of, ref.as_of_date());
begin
    select * into e from billing.enrollment where enrollment_id = p_enrollment_id for update;
    select * into c from academic.class where class_id = p_class_id;
    if e.status_code in ('DROPPED', 'CANCELLED', 'COMPLETED') then
        raise exception 'Enrolment % is % and cannot be assigned to a class', e.enrollment_code, lower(e.status_code);
    end if;
    if c.course_id <> e.course_id then raise exception 'Class % teaches another course', c.class_code; end if;
    if (select count(*) from billing.enrollment where class_id = p_class_id and enrollment_id <> p_enrollment_id
          and status_code in ('WAITLISTED','REGISTERED','ACTIVE')) >= c.capacity then
        raise exception 'Class % is full (% seats)', c.class_code, c.capacity;
    end if;
    update billing.enrollment
       set class_id = p_class_id, class_assigned_by = p_by, class_assigned_at = now(),
           status_code = case when c.start_date > v_as_of then 'REGISTERED' else 'ACTIVE' end, status_changed_on = v_as_of
     where enrollment_id = p_enrollment_id;
    perform billing.build_revenue_schedule(p_enrollment_id);
end $$;

-- Drop-out, deferral (the learner keeps the remaining contract for a later class) or cancellation before the start (Sales / Finance).
create or replace function billing.change_enrollment_status(p_enrollment_id bigint, p_status text, p_effective date, p_reason text)
returns void language plpgsql as $$
declare e billing.enrollment; c academic.class;
begin
    select * into e from billing.enrollment where enrollment_id = p_enrollment_id for update;
    select * into c from academic.class where class_id = e.class_id;
    if p_status not in ('DROPPED', 'DEFERRED', 'CANCELLED') then raise exception 'Use assign_class to (re)activate an enrolment'; end if;
    if e.status_code in ('DROPPED', 'CANCELLED') then raise exception 'Enrolment % is already %', e.enrollment_code, lower(e.status_code); end if;
    if p_status = 'DROPPED' and (c.class_id is null or p_effective < c.start_date) then
        raise exception 'A learner who has not started class is cancelled, not dropped';
    end if;
    if p_status = 'CANCELLED' and c.class_id is not null and p_effective >= c.start_date then
        raise exception 'The class has started: record a drop-out instead of a cancellation';
    end if;
    update billing.enrollment
       set status_code = p_status, status_changed_on = p_effective,
           class_id = case when p_status = 'DEFERRED' then null else class_id end
     where enrollment_id = p_enrollment_id;
    update billing.enrollment_status_history set reason = p_reason
     where history_id = (select max(history_id) from billing.enrollment_status_history where enrollment_id = p_enrollment_id);
    perform billing.build_revenue_schedule(p_enrollment_id);
end $$;

-- Finance decision on a discount outside policy. A rejected discount is removed and the enrolment re-priced; if payments were already
-- allocated, the difference is added as a new instalment due in seven days.
create or replace function billing.decide_discount(p_enrollment_id bigint, p_seq smallint, p_approve boolean, p_by bigint, p_note text default null)
returns void language plpgsql as $$
declare v_before numeric; v_after numeric; v_paid boolean; v_deposit numeric;
begin
    if not exists (select 1 from billing.enrollment_discount where enrollment_id = p_enrollment_id and seq = p_seq and approval_status = 'PENDING') then
        raise exception 'No pending discount % on this enrolment', p_seq;
    end if;
    if p_approve then
        update billing.enrollment_discount set approval_status = 'APPROVED', approved_by = p_by, decided_at = now(),
               reason = coalesce(p_note, reason)
         where enrollment_id = p_enrollment_id and seq = p_seq;
        return;
    end if;
    select coalesce(sum(amount), 0) into v_before from billing.enrollment_charge where enrollment_id = p_enrollment_id;
    delete from billing.enrollment_discount where enrollment_id = p_enrollment_id and seq = p_seq;
    v_after := billing.price_enrollment(p_enrollment_id);
    select exists (select 1 from billing.payment_allocation a join billing.payment_schedule s using (schedule_line_id)
                    where s.enrollment_id = p_enrollment_id) into v_paid;
    if not v_paid then
        select amount_due into v_deposit from billing.payment_schedule where enrollment_id = p_enrollment_id and line_type = 'DEPOSIT';
        perform billing.generate_payment_schedule(p_enrollment_id, v_deposit);
    elsif v_after > v_before then
        insert into billing.payment_schedule (enrollment_id, seq, line_type, label, due_date, amount_due)
        select p_enrollment_id, max(seq) + 1, 'INSTALMENT', 'Discount not approved', ref.as_of_date() + 7, v_after - v_before
          from billing.payment_schedule where enrollment_id = p_enrollment_id;
    end if;
    perform billing.build_revenue_schedule(p_enrollment_id);
end $$;

-- Record a receipt (Sales / receipt desk): next receipt number, then the cash is applied to the enrolment's oldest open instalments.
create or replace function billing.record_receipt(
    p_student_id bigint, p_enrollment_id bigint, p_receipt_date date, p_amount numeric, p_method text,
    p_collected_by bigint, p_payer_name text default null, p_payer_guardian_id bigint default null, p_notes text default null)
returns bigint language plpgsql as $$
declare v_no text; v_id bigint; v_status text;
begin
    if p_enrollment_id is not null and not exists (select 1 from billing.enrollment where enrollment_id = p_enrollment_id and student_id = p_student_id) then
        raise exception 'The enrolment does not belong to this student';
    end if;
    perform pg_advisory_xact_lock(hashtext('billing.receipt_no'));
    select 'PT' || lpad((coalesce(max(substring(receipt_no from 3)::int), 0) + 1)::text, 4, '0') into v_no from billing.receipt;
    insert into billing.receipt (receipt_no, receipt_date, student_id, enrollment_id, payer_guardian_id, payer_name, amount,
                                 payment_method_code, collected_by, notes)
    values (v_no, p_receipt_date, p_student_id, p_enrollment_id, p_payer_guardian_id, p_payer_name, p_amount, p_method, p_collected_by, p_notes)
    returning receipt_id into v_id;
    if p_enrollment_id is not null then
        perform billing.allocate_receipt(v_id, p_enrollment_id);
        select status_code into v_status from billing.enrollment where enrollment_id = p_enrollment_id;
        if v_status in ('DROPPED', 'CANCELLED') then perform billing.build_revenue_schedule(p_enrollment_id); end if;
    end if;
    return v_id;
end $$;

-- Apply a receipt taken without an enrolment (an advance payment) once the learner is enrolled (Sales). Clears control BIL-04.
create or replace function billing.apply_receipt(p_receipt_id bigint, p_enrollment_id bigint) returns numeric language plpgsql as $$
declare r billing.receipt;
begin
    select * into r from billing.receipt where receipt_id = p_receipt_id for update;
    if r.status <> 'ISSUED' then raise exception 'Receipt % is void', r.receipt_no; end if;
    if not exists (select 1 from billing.enrollment where enrollment_id = p_enrollment_id and student_id = r.student_id) then
        raise exception 'Enrolment and receipt % belong to different learners', r.receipt_no;
    end if;
    update billing.receipt set enrollment_id = p_enrollment_id where receipt_id = p_receipt_id;
    return billing.allocate_receipt(p_receipt_id, p_enrollment_id);
end $$;

-- Staff ask for a receipt to be voided; only the Finance Manager can approve it (receipts are never edited or deleted).
create or replace function billing.request_receipt_void(p_receipt_id bigint, p_by bigint, p_reason text) returns void language plpgsql as $$
begin
    if coalesce(trim(p_reason), '') = '' then raise exception 'A reason is required'; end if;
    update billing.receipt set void_requested_by = p_by, void_requested_at = now(), void_reason = p_reason
     where receipt_id = p_receipt_id and status = 'ISSUED';
    if not found then raise exception 'Receipt not found or already void'; end if;
end $$;

create or replace function billing.decide_receipt_void(p_receipt_id bigint, p_approve boolean, p_by bigint) returns void language plpgsql as $$
declare r billing.receipt; v_enrollments bigint[];
begin
    select * into r from billing.receipt where receipt_id = p_receipt_id for update;
    if r.void_requested_at is null or r.status <> 'ISSUED' then raise exception 'No pending void request for this receipt'; end if;
    if not p_approve then
        update billing.receipt set void_requested_by = null, void_requested_at = null, void_reason = null where receipt_id = p_receipt_id;
        return;
    end if;
    if exists (select 1 from finance.fiscal_period where period_id = finance.period_of(r.receipt_date) and status = 'CLOSED') then
        raise exception 'Receipt % is in a closed period; record a refund instead', r.receipt_no;
    end if;
    select array_agg(distinct s.enrollment_id) into v_enrollments
      from billing.payment_allocation a join billing.payment_schedule s using (schedule_line_id) where a.receipt_id = p_receipt_id;
    delete from billing.payment_allocation where receipt_id = p_receipt_id;
    update billing.receipt set status = 'VOID', voided_by = p_by, voided_at = now() where receipt_id = p_receipt_id;
    perform billing.build_revenue_schedule(x) from unnest(coalesce(v_enrollments, '{}')) x;
end $$;

-- Refund (Finance). With p_reduce_contract the enrolment's price is reduced by the same amount (e.g. sessions the centre cancelled),
-- so the accrual view earns less; otherwise the refund returns cash that was never earned (cancelled / dropped learners).
create or replace function billing.record_refund(p_enrollment_id bigint, p_refund_date date, p_amount numeric, p_reason text,
                                                 p_by bigint, p_reduce_contract boolean default false, p_voucher_id bigint default null)
returns bigint language plpgsql as $$
declare v_paid numeric; v_refunded numeric; v_id bigint;
begin
    select coalesce(sum(a.amount), 0) into v_paid
      from billing.payment_allocation a join billing.receipt r using (receipt_id) join billing.payment_schedule s using (schedule_line_id)
     where s.enrollment_id = p_enrollment_id and r.status = 'ISSUED';
    select coalesce(sum(amount), 0) into v_refunded from billing.refund where enrollment_id = p_enrollment_id;
    if p_amount > v_paid - v_refunded then
        raise exception 'Refund % exceeds the % collected and not yet refunded', p_amount, v_paid - v_refunded;
    end if;
    insert into billing.refund (enrollment_id, refund_date, amount, reason, approved_by, voucher_id, reduces_contract)
    values (p_enrollment_id, p_refund_date, p_amount, p_reason, p_by, p_voucher_id, p_reduce_contract) returning refund_id into v_id;
    if p_reduce_contract then
        insert into billing.enrollment_charge (enrollment_id, charge_type, description, amount)
        values (p_enrollment_id, 'ADJUSTMENT', 'Refund: ' || p_reason, -p_amount);
    end if;
    perform billing.build_revenue_schedule(p_enrollment_id);
    return v_id;
end $$;

-- Write off earned tuition that will not be collected (Finance). Limited to the outstanding balance of a closed enrolment.
create or replace function billing.write_off_balance(p_enrollment_id bigint, p_date date, p_amount numeric, p_reason text, p_by bigint)
returns bigint language plpgsql as $$
declare v_out numeric; v_id bigint;
begin
    select outstanding_receivable into v_out from rpt.v_enrollment_balance where enrollment_id = p_enrollment_id;
    if (select status_code from billing.enrollment where enrollment_id = p_enrollment_id) not in ('DROPPED', 'CANCELLED') then
        raise exception 'Only balances of dropped-out or cancelled learners can be written off';
    end if;
    if p_amount > coalesce(v_out, 0) then raise exception 'Write-off % exceeds the outstanding balance %', p_amount, coalesce(v_out, 0); end if;
    insert into billing.write_off (enrollment_id, write_off_date, amount, reason, approved_by)
    values (p_enrollment_id, p_date, p_amount, p_reason, p_by) returning write_off_id into v_id;
    return v_id;
end $$;

/* ------------------------------------------------------------------ academic: application API */

-- Class code <PROGRAMME>_<COURSE>_<DDMMYY>, e.g. IE_PROGRESS_030325 (legacy convention).
create or replace function academic.make_class_code(p_course_id smallint, p_start date) returns text language sql stable as $$
    select case c.programme_code when 'AE' then 'AE' when 'COMM' then 'COM' when 'IELTS' then 'IE' else c.programme_code end
           || '_' || c.course_code || '_' || to_char(p_start, 'DDMMYY')
      from ref.course c where c.course_id = p_course_id
$$;

-- Open a class (Academic Manager): class code, weekly timetable, teacher and assistant, then every session is generated.
-- From this moment the class is selectable by Sales.
create or replace function academic.open_class(
    p_course_id smallint, p_delivery_mode text, p_start date, p_capacity smallint, p_room_id smallint,
    p_pattern jsonb, p_teacher_role_id bigint, p_assistant_role_id bigint default null, p_batch smallint default null,
    p_total_hours numeric default null, p_notes text default null) returns bigint language plpgsql as $$
declare co ref.course; v_id bigint; v_code text; p jsonb; v_hps numeric;
begin
    select * into co from ref.course where course_id = p_course_id;
    if jsonb_array_length(coalesce(p_pattern, '[]')) = 0 then raise exception 'The weekly timetable is empty'; end if;
    v_code := academic.make_class_code(p_course_id, p_start);
    if exists (select 1 from academic.class where class_code = v_code) then
        raise exception 'Class % already exists', v_code;
    end if;
    select round(extract(epoch from ((x->>'end')::time - (x->>'start')::time)) / 3600, 2) into v_hps
      from jsonb_array_elements(p_pattern) x limit 1;
    insert into academic.class (class_code, course_id, delivery_mode_code, batch_no, start_date, planned_end_date, total_hours,
                                hours_per_session, sessions_per_week, capacity, room_id, lifecycle_status, notes)
    values (v_code, p_course_id, p_delivery_mode, p_batch, p_start, p_start, coalesce(p_total_hours, co.standard_hours),
            v_hps, jsonb_array_length(p_pattern), p_capacity, p_room_id, 'OPEN', p_notes)
    returning class_id into v_id;
    for p in select * from jsonb_array_elements(p_pattern) loop
        insert into academic.class_meeting_pattern (class_id, weekday, start_time, end_time)
        values (v_id, (p->>'weekday')::smallint, (p->>'start')::time, (p->>'end')::time);
    end loop;
    insert into academic.class_staff_assignment (class_id, employee_role_id, assignment_role, effective_from)
    values (v_id, p_teacher_role_id, 'LEAD_TEACHER', p_start);
    if p_assistant_role_id is not null then
        insert into academic.class_staff_assignment (class_id, employee_role_id, assignment_role, effective_from)
        values (v_id, p_assistant_role_id, 'TEACHING_ASSISTANT', p_start);
    end if;
    perform academic.generate_sessions(v_id);
    return v_id;
end $$;

-- Confirm a delivered session (Academic Manager): marks it delivered and records the hours of every assigned staff member,
-- which is what payroll pays (spec section 6, BR-07). A cancelled session pays nobody.
create or replace function academic.confirm_session(p_session_id bigint, p_delivered boolean, p_by bigint, p_hours numeric default null)
returns integer language plpgsql as $$
declare s academic.class_session; n integer := 0;
begin
    select * into s from academic.class_session where session_id = p_session_id for update;
    if exists (select 1 from payroll.payroll_run where period_id = finance.period_of(s.session_date) and status in ('APPROVED','PAID')) then
        raise exception 'Payroll for % is already approved; the session can no longer change', to_char(s.session_date, 'Mon YYYY');
    end if;
    delete from academic.session_staff where session_id = p_session_id;
    if not p_delivered then
        update academic.class_session set status = 'CANCELLED' where session_id = p_session_id;
        return 0;
    end if;
    update academic.class_session set status = case when status = 'MAKE_UP' then 'MAKE_UP' else 'DELIVERED' end where session_id = p_session_id;
    insert into academic.session_staff (session_id, employee_role_id, hours, confirmed_by, confirmed_at)
    select p_session_id, a.employee_role_id, coalesce(p_hours, s.planned_hours), p_by, now()
      from academic.class_staff_assignment a
     where a.class_id = s.class_id and s.session_date >= a.effective_from and (a.effective_to is null or s.session_date < a.effective_to);
    get diagnostics n = row_count;
    return n;
end $$;

-- Schedule a make-up session for one the centre cancelled (Academic Manager): the class keeps its contracted hours. If the class
-- now ends in a later month, the revenue schedules of its learners are rebuilt.
create or replace function academic.add_make_up_session(p_class_id bigint, p_date date, p_start time, p_end time,
                                                        p_room_id smallint default null) returns bigint language plpgsql as $$
declare c academic.class; v_id bigint;
begin
    select * into c from academic.class where class_id = p_class_id for update;
    if c.lifecycle_status in ('COMPLETED', 'CANCELLED') then raise exception 'Class % is %', c.class_code, lower(c.lifecycle_status); end if;
    if exists (select 1 from academic.closure_day where closure_date = p_date) then raise exception 'The centre is closed on %', p_date; end if;
    insert into academic.class_session (class_id, session_no, session_date, start_time, end_time, room_id, status)
    select p_class_id, max(session_no) + 1, p_date, p_start, p_end, coalesce(p_room_id, c.room_id), 'MAKE_UP'
      from academic.class_session where class_id = p_class_id
    returning session_id into v_id;
    if p_date > c.planned_end_date then
        update academic.class set planned_end_date = p_date where class_id = p_class_id;
        if date_trunc('month', p_date) > date_trunc('month', c.planned_end_date) then
            perform billing.build_revenue_schedule(e.enrollment_id) from billing.enrollment e
             where e.class_id = p_class_id and e.status_code in ('REGISTERED', 'ACTIVE');
        end if;
    end if;
    return v_id;
end $$;

-- Cancel a class that will not run (e.g. too few learners). Only before any session is delivered. Its learners go back to the
-- waiting list so Sales can place them in another class (or cancel them).
create or replace function academic.cancel_class(p_class_id bigint, p_reason text) returns integer language plpgsql as $$
declare c academic.class; n integer;
begin
    select * into c from academic.class where class_id = p_class_id for update;
    if exists (select 1 from academic.class_session where class_id = p_class_id and status in ('DELIVERED', 'MAKE_UP')
                 and session_date <= ref.as_of_date()) then
        raise exception 'Class % has already delivered sessions and cannot be cancelled', c.class_code;
    end if;
    update academic.class set lifecycle_status = 'CANCELLED', notes = concat_ws(' | ', notes, 'Cancelled: ' || p_reason)
     where class_id = p_class_id;
    update academic.class_session set status = 'CANCELLED' where class_id = p_class_id;
    update billing.enrollment set class_id = null, status_code = 'WAITLISTED', status_changed_on = ref.as_of_date()
     where class_id = p_class_id and status_code in ('WAITLISTED', 'REGISTERED', 'ACTIVE');
    get diagnostics n = row_count;
    perform billing.build_revenue_schedule(e.enrollment_id) from billing.enrollment e
     where e.status_code = 'WAITLISTED' and e.class_id is null and e.status_changed_on = ref.as_of_date();
    return n;
end $$;

-- Move classes along their life cycle from the timetable: open -> running (first session reached) -> completed (last session past).
create or replace function academic.sync_class_statuses(p_as_of date default null) returns integer language plpgsql as $$
declare v_as_of date := coalesce(p_as_of, ref.as_of_date()); n integer;
begin
    update academic.class c
       set lifecycle_status = case when c.planned_end_date < v_as_of then 'COMPLETED' else 'RUNNING' end,
           actual_end_date  = case when c.planned_end_date < v_as_of then c.planned_end_date else c.actual_end_date end
     where c.lifecycle_status in ('PLANNED', 'OPEN', 'RUNNING') and c.start_date <= v_as_of
       and c.lifecycle_status <> case when c.planned_end_date < v_as_of then 'COMPLETED' else 'RUNNING' end;
    get diagnostics n = row_count;
    return n;
end $$;

-- Nightly job: class and enrolment life cycles, then every control (the exception queues the managers work from).
create or replace function app.run_daily_jobs(p_as_of date default null) returns table (job text, rows_affected integer)
language plpgsql as $$
declare v_as_of date := coalesce(p_as_of, ref.as_of_date());
begin
    job := 'Class statuses';      rows_affected := academic.sync_class_statuses(v_as_of);       return next;
    job := 'Enrolment statuses';  rows_affected := billing.sync_enrollment_statuses(v_as_of);   return next;
    job := 'Control exceptions';  select coalesce(sum(exceptions), 0) into rows_affected from ctl.run_all_controls(); return next;
end $$;

/* ------------------------------------------------------------------ payroll: commissions and period close */

-- Accrue sales commission for a month from the configurable rule (spec section 6): earned when the enrolment is fully paid
-- (or at its first payment, depending on the rule) and credited to the Learning Advisor who sold it.
create or replace function payroll.accrue_commissions(p_period_id integer) returns integer language plpgsql as $$
declare r payroll.commission_rule; v_start date; v_end date; n integer;
begin
    select period_start, period_end into v_start, v_end from finance.fiscal_period where period_id = p_period_id;
    select * into r from payroll.commission_rule
     where role_code = 'LA' and v_end >= effective_from and (effective_to is null or v_end < effective_to);
    if r.rule_id is null then return 0; end if;
    with paid as (
        select s.enrollment_id, r2.receipt_date,
               sum(a.amount) over (partition by s.enrollment_id order by r2.receipt_date, r2.receipt_id) as cumulative,
               row_number() over (partition by s.enrollment_id order by r2.receipt_date, r2.receipt_id) as nth
        from billing.payment_allocation a
        join billing.receipt r2 on r2.receipt_id = a.receipt_id and r2.status = 'ISSUED'
        join billing.payment_schedule s on s.schedule_line_id = a.schedule_line_id),
    price as (select enrollment_id, sum(amount) as net, sum(amount) filter (where charge_type <> 'MATERIALS_FEE') as tuition
              from billing.enrollment_charge group by enrollment_id),
    earned as (
        select e.enrollment_id, e.sales_owner_employee_id, p.tuition,
               min(pd.receipt_date) filter (where (r.earn_event = 'FULLY_PAID' and pd.cumulative >= p.net) or (r.earn_event = 'FIRST_PAYMENT' and pd.nth = 1)) as earned_on
        from billing.enrollment e join price p using (enrollment_id) join paid pd using (enrollment_id)
        where e.sales_owner_employee_id is not null and e.status_code <> 'CANCELLED'
          and not exists (select 1 from payroll.commission c where c.enrollment_id = e.enrollment_id)
        group by e.enrollment_id, e.sales_owner_employee_id, p.tuition)
    insert into payroll.commission (enrollment_id, employee_id, amount, earned_period_id)
    select enrollment_id, sales_owner_employee_id,
           case when r.basis = 'PCT_OF_NET_TUITION' then round(tuition * r.rate, -3) else r.fixed_amount end, p_period_id
      from earned where earned_on between v_start and v_end;
    get diagnostics n = row_count;
    return n;
end $$;

-- Month-end close (Finance Manager). Hard gates: the previous month is closed and the month's payroll is approved.
-- After closing, nothing dated in the month can be posted, changed or deleted.
create or replace function finance.close_period(p_period_id integer, p_by bigint) returns void language plpgsql as $$
declare v_prev integer;
begin
    if (select status from finance.fiscal_period where period_id = p_period_id) <> 'OPEN' then
        raise exception 'Period % is not open', p_period_id;
    end if;
    select max(period_id) into v_prev from finance.fiscal_period where period_id < p_period_id and status = 'OPEN';
    if v_prev is not null then raise exception 'Close % first: periods are closed in order', v_prev; end if;
    if not exists (select 1 from payroll.payroll_run where period_id = p_period_id and status in ('APPROVED', 'PAID')) then
        raise exception 'Payroll for % has not been approved by HR yet', p_period_id;
    end if;
    update finance.fiscal_period set status = 'CLOSED', closed_at = now() where period_id = p_period_id;
end $$;

-- HR approves a calculated run. Gate: every session of the month has been confirmed by the Academic Manager, otherwise teachers
-- would be paid on incomplete hours.
create or replace function payroll.approve_run(p_run_id bigint, p_by bigint) returns void language plpgsql as $$
declare r payroll.payroll_run; v_open integer;
begin
    select * into r from payroll.payroll_run where run_id = p_run_id for update;
    if r.status <> 'CALCULATED' then raise exception 'Only a calculated run can be approved (run is %)', r.status; end if;
    select count(*) into v_open
      from academic.class_session s join academic.class c using (class_id) join finance.fiscal_period p on p.period_id = r.period_id
     where s.session_date between p.period_start and least(p.period_end, ref.as_of_date())
       and c.lifecycle_status <> 'CANCELLED'
       and (s.status = 'SCHEDULED'
            or (s.status in ('DELIVERED','MAKE_UP') and not exists (select 1 from academic.session_staff ss
                                                                     where ss.session_id = s.session_id and ss.confirmed_at is not null)));
    if v_open > 0 then
        raise exception '% session(s) of this month are not confirmed yet: ask the Academic Manager to confirm them, then recalculate', v_open;
    end if;
    update payroll.payroll_run set status = 'APPROVED', approved_by = p_by, approved_at = now() where run_id = p_run_id;
end $$;

-- Payroll paid (bank transfer done): the run is final and its commissions are settled.
create or replace function payroll.mark_run_paid(p_run_id bigint, p_paid_on date) returns void language plpgsql as $$
begin
    update payroll.payroll_run set status = 'PAID', paid_on = p_paid_on where run_id = p_run_id and status = 'APPROVED';
    if not found then raise exception 'Only an approved run can be paid'; end if;
    update payroll.commission set status = 'PAID' where run_id = p_run_id and status = 'ACCRUED';
end $$;

/* ------------------------------------------------------------------ app: daily cash close (compensating control for staff cash handling) */

-- A collector closes the day: the system works out what should be in the drawer from the receipts issued that day; the collector
-- enters what was counted. Any difference stays visible until the Finance Manager reviews it (control BIL-09).
create or replace function app.close_cash(p_date date, p_collector bigint, p_counted numeric, p_note text default null) returns bigint
language plpgsql as $$
declare v_cash numeric; v_transfer numeric; v_id bigint;
begin
    select coalesce(sum(amount) filter (where payment_method_code = 'CASH'), 0),
           coalesce(sum(amount) filter (where payment_method_code <> 'CASH'), 0)
      into v_cash, v_transfer
      from billing.receipt where receipt_date = p_date and collected_by = p_collector and status = 'ISSUED';
    if p_counted <> v_cash and coalesce(trim(p_note), '') = '' then
        raise exception 'Counted cash differs from receipts by %: explain the difference', p_counted - v_cash;
    end if;
    insert into app.cash_close (close_date, collector_id, expected_cash, expected_transfer, counted_cash, note)
    values (p_date, p_collector, v_cash, v_transfer, p_counted, p_note)
    returning cash_close_id into v_id;
    return v_id;
end $$;

create or replace function app.review_cash_close(p_cash_close_id bigint, p_by bigint) returns void language plpgsql as $$
begin
    update app.cash_close set reviewed_by = p_by, reviewed_at = now() where cash_close_id = p_cash_close_id and reviewed_at is null;
    if not found then raise exception 'Cash close not found or already reviewed'; end if;
end $$;

/* ------------------------------------------------------------------ finance */

-- Straight-line monthly charge of a fixed asset; the last month absorbs rounding.
create or replace function finance.generate_depreciation(p_asset_id bigint) returns integer language plpgsql as $$
declare fa finance.fixed_asset%rowtype; v_start date; v_base numeric; v_amount numeric; v_left numeric; i integer;
begin
    select * into fa from finance.fixed_asset where asset_id = p_asset_id;
    delete from finance.depreciation_schedule where asset_id = p_asset_id;
    select period_start into v_start from finance.fiscal_period where period_id = fa.first_charge_period_id;
    perform finance.ensure_periods(v_start, (v_start + make_interval(months => fa.useful_life_months - 1))::date);
    v_base := fa.cost - fa.residual_value;
    v_left := v_base;
    for i in 1 .. fa.useful_life_months loop
        v_amount := case when i = fa.useful_life_months then v_left else round(v_base / fa.useful_life_months, 0) end;
        v_left := v_left - v_amount;
        insert into finance.depreciation_schedule (asset_id, period_id, amount)
        values (p_asset_id, finance.period_of((v_start + make_interval(months => i - 1))::date), v_amount);
    end loop;
    return fa.useful_life_months;
end $$;

-- Most specific GL account for an earning (role, programme and delivery mode are optional filters).
create or replace function finance.earning_account(p_earning text, p_role text, p_programme text, p_mode text)
returns text language sql stable as $$
    select account_code from finance.earning_account_map m
    where m.earning_type_code = p_earning
      and (m.role_code is null or m.role_code = p_role)
      and (m.programme_code is null or m.programme_code = p_programme)
      and (m.delivery_mode_code is null or m.delivery_mode_code = p_mode)
    order by (m.role_code is not null)::int + (m.programme_code is not null)::int + (m.delivery_mode_code is not null)::int desc
    limit 1
$$;

/* ------------------------------------------------------------------ payroll */

-- Hourly rate of an employee role on a date: personal override, else the salary-code rate (legacy 'Salary Pipeline').
create or replace function payroll.hourly_rate(p_employee_role_id bigint, p_on date) returns numeric language sql stable as $$
    select coalesce(
        (select o.hourly_rate from hr.employee_rate_override o
          where o.employee_role_id = p_employee_role_id and p_on >= o.effective_from and (o.effective_to is null or p_on < o.effective_to)),
        (select r.hourly_rate from hr.employee_role er join ref.salary_rate r on r.salary_code = er.salary_code
          where er.employee_role_id = p_employee_role_id and p_on >= r.effective_from and (r.effective_to is null or p_on < r.effective_to)))
$$;

-- Calculate a payroll run: teaching/TA hours from confirmed sessions, LA hours from worked shifts, fixed pay,
-- accrued commission; then payslips with PIT withholding and statutory deductions. MANUAL lines are kept.
create or replace function payroll.calculate_run(p_run_id bigint) returns integer language plpgsql as $$
declare
    v_period integer; v_start date; v_end date; v_status text; n integer; x record; v_pit numeric; v_ded numeric; v_slip bigint;
begin
    select r.period_id, p.period_start, p.period_end, r.status into v_period, v_start, v_end, v_status
    from payroll.payroll_run r join finance.fiscal_period p using (period_id) where r.run_id = p_run_id;
    if v_status in ('APPROVED','PAID') then raise exception 'Run % is % and cannot be recalculated', p_run_id, v_status; end if;

    delete from payroll.payslip where run_id = p_run_id;
    delete from payroll.payroll_line where run_id = p_run_id and source_type <> 'MANUAL';
    update payroll.commission set run_id = null where run_id = p_run_id and status = 'ACCRUED';
    perform payroll.accrue_commissions(v_period);

    -- 1. Teaching and assistant hours from confirmed, delivered sessions (legacy: Working Schedule x Pipeline)
    insert into payroll.payroll_line (run_id, employee_id, employee_role_id, earning_type_code, programme_code, delivery_mode_code,
                                      quantity_hours, rate, amount, source_type, account_code, cost_center_code)
    select p_run_id, er.employee_id, er.employee_role_id,
           case when er.role_code like 'TEACHER%' then 'TEACHING_PAY' when er.role_code like 'AT%' then 'AT_PAY' else 'TA_PAY' end,
           co.programme_code, c.delivery_mode_code,
           sum(ss.hours), payroll.hourly_rate(er.employee_role_id, s.session_date),
           round(sum(ss.hours) * payroll.hourly_rate(er.employee_role_id, s.session_date), 0),
           'SESSION_HOURS',
           finance.earning_account(case when er.role_code like 'TEACHER%' then 'TEACHING_PAY' when er.role_code like 'AT%' then 'AT_PAY' else 'TA_PAY' end,
                                   er.role_code, co.programme_code, c.delivery_mode_code),
           coalesce((select cc.cost_center_code from finance.cost_center cc where cc.programme_code = co.programme_code), er.cost_center_code)
    from academic.session_staff ss
    join academic.class_session s using (session_id)
    join academic.class c using (class_id)
    join ref.course co on co.course_id = c.course_id
    join hr.employee_role er on er.employee_role_id = ss.employee_role_id
    where s.session_date between v_start and v_end and s.status in ('DELIVERED','MAKE_UP') and ss.confirmed_at is not null
    group by er.employee_id, er.employee_role_id, er.role_code, er.cost_center_code, co.programme_code, c.delivery_mode_code,
             payroll.hourly_rate(er.employee_role_id, s.session_date);

    -- 2. Learning Advisor hours from worked shifts net of deductions
    insert into payroll.payroll_line (run_id, employee_id, employee_role_id, earning_type_code, quantity_hours, rate, amount,
                                      source_type, account_code, cost_center_code)
    select p_run_id, er.employee_id, er.employee_role_id, 'LA_PAY',
           sum(w.hours - w.deduction_hours), payroll.hourly_rate(er.employee_role_id, w.shift_date),
           round(sum(w.hours - w.deduction_hours) * payroll.hourly_rate(er.employee_role_id, w.shift_date), 0),
           'SHIFT_HOURS', finance.earning_account('LA_PAY', er.role_code, null, null), er.cost_center_code
    from hr.work_shift w join hr.employee_role er using (employee_role_id)
    where w.shift_date between v_start and v_end and w.status = 'WORKED'
    group by er.employee_id, er.employee_role_id, er.role_code, er.cost_center_code, payroll.hourly_rate(er.employee_role_id, w.shift_date);

    -- 3. Fixed monthly pay
    insert into payroll.payroll_line (run_id, employee_id, employee_role_id, earning_type_code, amount, source_type, account_code, cost_center_code)
    select p_run_id, er.employee_id, er.employee_role_id, 'FIXED_SALARY', fp.monthly_amount, 'FIXED_PAY',
           finance.earning_account('FIXED_SALARY', er.role_code, null, null), er.cost_center_code
    from hr.employee_fixed_pay fp join hr.employee_role er using (employee_role_id)
    where v_end >= fp.effective_from and (fp.effective_to is null or v_end < fp.effective_to)
      and v_end >= er.effective_from and (er.effective_to is null or v_end < er.effective_to);

    -- 4. Commission accrued in the month
    insert into payroll.payroll_line (run_id, employee_id, earning_type_code, amount, source_type, account_code, cost_center_code, note)
    select p_run_id, cm.employee_id, 'COMMISSION', cm.amount, 'COMMISSION',
           finance.earning_account('COMMISSION', null, null, null),
           coalesce(e.home_cost_center_code, '921012'), 'Enrolment ' || en.enrollment_code
    from payroll.commission cm join hr.employee e using (employee_id) join billing.enrollment en using (enrollment_id)
    where cm.earned_period_id = v_period and cm.status = 'ACCRUED';
    update payroll.commission set run_id = p_run_id where earned_period_id = v_period and status = 'ACCRUED';

    -- 5. Payslips: taxable earnings, allowances, PIT (legacy: IF(income > 2,000,000; income x 10%; 0)), insurance
    for x in
        select l.employee_id, e.employment_type,
               coalesce(sum(l.amount) filter (where et.is_taxable), 0) as taxable,
               coalesce(sum(l.amount) filter (where et.is_allowance), 0) as allowances
        from payroll.payroll_line l join ref.earning_type et using (earning_type_code) join hr.employee e using (employee_id)
        where l.run_id = p_run_id group by l.employee_id, e.employment_type loop
        select case when x.taxable > r.threshold_amount then round(x.taxable * r.rate, 0) else 0 end into v_pit
        from payroll.pit_rule r
        where r.employment_type = x.employment_type and v_end >= r.effective_from and (r.effective_to is null or v_end < r.effective_to);
        v_pit := coalesce(v_pit, 0);
        select coalesce(sum(round(x.taxable * d.employee_rate, 0)), 0) into v_ded
        from payroll.statutory_deduction_rule d
        where d.employment_type = x.employment_type and v_end >= d.effective_from and (d.effective_to is null or v_end < d.effective_to);
        insert into payroll.payslip (run_id, employee_id, taxable_earnings, allowances, pit_withheld, other_deductions, net_pay)
        values (p_run_id, x.employee_id, x.taxable, x.allowances, v_pit, v_ded, x.taxable + x.allowances - v_pit - v_ded)
        returning payslip_id into v_slip;
        insert into payroll.payslip_deduction (payslip_id, deduction_type_code, amount)
        select v_slip, 'PIT', v_pit where v_pit > 0;
        insert into payroll.payslip_deduction (payslip_id, deduction_type_code, amount)
        select v_slip, d.deduction_type_code, round(x.taxable * d.employee_rate, 0)
        from payroll.statutory_deduction_rule d
        where d.employment_type = x.employment_type and d.employee_rate > 0
          and v_end >= d.effective_from and (d.effective_to is null or v_end < d.effective_to);
    end loop;

    update payroll.payroll_run set status = 'CALCULATED', calculated_at = now() where run_id = p_run_id;
    select count(*) into n from payroll.payslip where run_id = p_run_id;
    return n;
end $$;

/* ------------------------------------------------------------------ controls */

-- Execute one control: run its check view and update the exception queue. A record that still fails keeps its exception (and its
-- owner and status); a resolved one that fails again is reopened; an open one that now passes is cleared automatically.
create or replace function ctl.run_control(p_control_code text, p_executed_by bigint default null) returns integer language plpgsql as $$
declare c ctl.control%rowtype; v_run bigint; n integer;
begin
    select * into c from ctl.control where control_code = p_control_code and is_active;
    if not found then raise exception 'Unknown or inactive control %', p_control_code; end if;
    insert into ctl.control_run (control_code, as_of_date, exception_count, executed_by)
    values (p_control_code, ref.as_of_date(), 0, p_executed_by) returning control_run_id into v_run;
    execute format($q$
        with f as (select entity_type, entity_id, entity_ref, detail from %s),
        ins as (
            insert into ctl.control_exception as x (control_code, entity_type, entity_id, entity_ref, detail, severity, first_run_id, last_run_id)
            select %L, entity_type, entity_id, entity_ref, detail, %L, %s, %s from f
            on conflict (control_code, entity_type, entity_id) do update
               set detail = excluded.detail, entity_ref = excluded.entity_ref, last_run_id = excluded.last_run_id,
                   status = case when x.status in ('RESOLVED', 'CLEARED') then 'OPEN' else x.status end,
                   opened_at = case when x.status in ('RESOLVED', 'CLEARED') then now() else x.opened_at end,
                   resolved_at = case when x.status in ('RESOLVED', 'CLEARED') then null else x.resolved_at end
            returning 1),
        clr as (
            update ctl.control_exception x set status = 'CLEARED', resolved_at = now(),
                   resolution_note = coalesce(x.resolution_note, 'Passed the rule again')
             where x.control_code = %L and x.status in ('OPEN', 'IN_PROGRESS')
               and not exists (select 1 from f where f.entity_type = x.entity_type and f.entity_id = x.entity_id)
            returning 1)
        select (select count(*) from ins)::int$q$, c.check_view, c.control_code, c.severity, v_run, v_run, c.control_code) into n;
    update ctl.control_run set exception_count = n where control_run_id = v_run;
    return n;
end $$;

-- Execute every active control; returns (control, exceptions).
create or replace function ctl.run_all_controls() returns table (control_code text, exceptions integer) language plpgsql as $$
declare c record;
begin
    for c in select ctl.control.control_code from ctl.control where is_active order by 1 loop
        control_code := c.control_code;
        exceptions := ctl.run_control(c.control_code);
        return next;
    end loop;
end $$;

/* ------------------------------------------------------------------ app: authentication */

-- Sign-in check. Runs with the owner's rights so password hashes are never readable by application roles.
create or replace function app.authenticate(p_username text, p_password text)
returns table (user_id integer, username text, full_name text, role_code text, employee_id bigint)
language plpgsql security definer set search_path = pg_catalog, pg_temp as $$
#variable_conflict use_column
begin
    return query
    with u as (
        update app.app_user a set last_login_at = now()
         where a.username = lower(trim(p_username)) and a.is_active
           and a.password_hash = extensions.crypt(p_password, a.password_hash)
        returning a.user_id, a.username, a.full_name, a.role_code, a.employee_id)
    select u.user_id, u.username, u.full_name, u.role_code, u.employee_id from u;
end $$;

-- Set or reset a password (administrators only; execution is revoked from application roles).
create or replace function app.set_password(p_username text, p_password text) returns void
language plpgsql security definer set search_path = pg_catalog, pg_temp as $$
begin
    if length(coalesce(p_password, '')) < 4 then raise exception 'Password too short'; end if;
    update app.app_user set password_hash = extensions.crypt(p_password, extensions.gen_salt('bf', 8)) where username = p_username;
    if not found then raise exception 'Unknown user %', p_username; end if;
end $$;
