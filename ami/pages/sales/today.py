"""Learning Advisor - my day: follow-ups, tests, collections and the cash drawer."""
import datetime as dt

import streamlit as st

from ami import auth, db, ui

auth.require("LEARNING_ADVISOR")
me = auth.employee_id()
bd = db.business_date()
user = auth.current_user()
ui.header(f"Good day, {user['full_name'].split()[-1]}", f"{ui.date(bd)} · your leads, tests, collections and cash drawer")

k = db.one("""
    select (select count(*) from crm.lead where owner_employee_id = %(me)s and closed_on is null) as open_leads,
           (select count(*) from crm.lead where owner_employee_id = %(me)s and closed_on is null and next_follow_up_on <= %(d)s) as follow_ups,
           (select count(*) from crm.placement_test t join crm.lead l using (lead_id)
             where l.owner_employee_id = %(me)s and t.status = 'BOOKED' and t.scheduled_at::date between %(d)s and %(d)s + 3) as tests,
           (select count(*) from crm.lead where owner_employee_id is null and closed_on is null) as unassigned,
           (select coalesce(sum(amount), 0) from billing.receipt where collected_by = %(me)s and receipt_date = %(d)s and status = 'ISSUED') as today_amount,
           (select count(*) from billing.receipt where collected_by = %(me)s and receipt_date = %(d)s and status = 'ISSUED') as today_count,
           (select coalesce(sum(overdue_amount), 0) from rpt.v_enrollment_balance where sales_owner_employee_id = %(me)s
              and status_code in ('REGISTERED','ACTIVE','COMPLETED','WAITLISTED')) as my_overdue,
           (select count(*) from billing.enrollment where sales_owner_employee_id = %(me)s
              and enrolled_on >= date_trunc('month', %(d)s::date)) as enrolled_month
""", {"me": me, "d": bd})
ui.kpis([
    ("Open leads", k["open_leads"], "Leads you own that are not converted or lost"),
    ("Follow-ups due", k["follow_ups"], "Next follow-up date is today or earlier"),
    ("Tests in 3 days", k["tests"]),
    ("Enrolled this month", k["enrolled_month"]),
    ("Collected today", ui.vnd_short(k["today_amount"]), f"{k['today_count']} receipts"),
    ("Overdue on my learners", ui.vnd_short(k["my_overdue"]), "Instalments past due on enrolments you sold"),
])

left, right = st.columns([1.15, 1], gap="large")
with left:
    st.subheader("Follow-ups due", anchor=False)
    fu = db.df("""
        select l.lead_id, s.full_name as learner, l.programme_code as programme, ls.name as stage, l.lead_date,
               l.next_follow_up_on, coalesce(s.phone, g.phone) as phone
        from crm.lead l join crm.student s using (student_id) join ref.lead_stage ls using (stage_code)
        left join crm.student_guardian sg on sg.student_id = s.student_id and sg.is_primary_contact
        left join crm.guardian g on g.guardian_id = sg.guardian_id
        where l.owner_employee_id = %(me)s and l.closed_on is null and l.next_follow_up_on <= %(d)s
        order by l.next_follow_up_on, l.lead_date""", {"me": me, "d": bd})
    if fu.empty:
        ui.empty("No follow-ups due. Nice.")
    else:
        ui.table(fu, dates=["lead_date", "next_follow_up_on"], hide=["lead_id"], key="fu")
    st.page_link("ami/pages/sales/leads.py", label="Open the lead pipeline", icon=":material/arrow_forward:")

    st.subheader("Collections: my learners with overdue instalments", anchor=False)
    od = db.df("""
        select l.enrollment_code, b.learner, b.course_name, l.label, l.due_date, l.remaining, l.days_overdue,
               coalesce(s.phone, g.phone) as phone
        from rpt.v_schedule_line_status l join rpt.v_enrollment_balance b using (enrollment_id)
        join crm.student s on s.student_id = b.student_id
        left join crm.student_guardian sg on sg.student_id = s.student_id and sg.is_payer
        left join crm.guardian g on g.guardian_id = sg.guardian_id
        where b.sales_owner_employee_id = %(me)s and l.days_overdue > 0 and l.remaining > 0
        order by l.days_overdue desc limit 15""", {"me": me})
    if od.empty:
        ui.empty("No overdue instalments on your learners.")
    else:
        ui.table(od, money=["remaining"], dates=["due_date"], key="od")
    st.page_link("ami/pages/sales/students.py", label="Record a payment", icon=":material/arrow_forward:")

with right:
    st.subheader("Placement tests coming up", anchor=False)
    tests = db.df("""
        select t.scheduled_at, s.full_name as learner, t.test_type, e.name_code as advisor
        from crm.placement_test t join crm.lead l using (lead_id) join crm.student s using (student_id)
        left join hr.employee e on e.employee_id = l.owner_employee_id
        where t.status = 'BOOKED' and t.scheduled_at::date between %(d)s - 2 and %(d)s + 7
        order by t.scheduled_at""", {"d": bd})
    if tests.empty:
        ui.empty("No tests booked for the coming week.")
    else:
        tests["scheduled_at"] = tests["scheduled_at"].dt.tz_convert("Asia/Ho_Chi_Minh").dt.strftime("%a %d %b %H:%M")
        tests["test_type"] = tests["test_type"].str.replace("_", " ").str.title()
        ui.table(tests, key="tests")

    st.subheader("Unassigned leads", anchor=False)
    un = db.df("""select l.lead_id, s.full_name as learner, l.programme_code as programme, l.lead_date, l.notes
                  from crm.lead l join crm.student s using (student_id)
                  where l.owner_employee_id is null and l.closed_on is null order by l.lead_date""")
    if un.empty:
        ui.empty("Every open lead has an advisor.")
    else:
        st.caption("New inquiries from the website. Take the ones you will call (control SAL-01).")
        ui.table(un, dates=["lead_date"], hide=["lead_id"], key="un")
        with st.form("take_lead"):
            c1, c2, c3 = st.columns([1.4, 1.2, 0.8], vertical_alignment="bottom")
            pick = c1.selectbox("Lead", un["lead_id"], format_func=lambda i: un.set_index("lead_id").loc[i, "learner"])
            channels = db.lookup("select channel_code, name from ref.acquisition_channel order by name", "LA")
            ch = c2.selectbox("Channel", channels["channel_code"], format_func=lambda c: channels.set_index("channel_code").loc[c, "name"],
                              index=int((channels["channel_code"] == "OTHER").idxmax()))
            if c3.form_submit_button("Take it", type="primary", width="stretch"):
                ui.act(lambda: db.execute("""update crm.lead set owner_employee_id = %s, channel_code = %s, next_follow_up_on = %s
                                             where lead_id = %s and owner_employee_id is null""", (me, ch, bd, int(pick)), fetch=False),
                       "Lead assigned to you - call them today.")

    st.subheader("Cash drawer", anchor=False)
    open_days = db.df("""
        select r.receipt_date, count(*) as receipts,
               coalesce(sum(r.amount) filter (where r.payment_method_code = 'CASH'), 0) as cash,
               coalesce(sum(r.amount) filter (where r.payment_method_code <> 'CASH'), 0) as transfer_card
        from billing.receipt r
        where r.collected_by = %(me)s and r.status = 'ISSUED' and r.receipt_date >= %(d)s - 14
          and not exists (select 1 from app.cash_close k where k.close_date = r.receipt_date and k.collector_id = r.collected_by)
        group by r.receipt_date order by r.receipt_date""", {"me": me, "d": bd})
    if open_days.empty:
        st.success("All your cash days are closed.", icon=":material/check_circle:")
    else:
        late = open_days[open_days["receipt_date"] < bd]
        if not late.empty:
            st.error(f"{len(late)} earlier day(s) not closed yet - close them before you leave (control BIL-09).", icon=":material/warning:")
        ui.table(open_days, money=["cash", "transfer_card"], dates=["receipt_date"], key="cash")
    st.page_link("ami/pages/sales/cash.py", label="Close the cash drawer", icon=":material/arrow_forward:")

n_exc = db.val("select count(*) from ctl.control_exception where status in ('OPEN','IN_PROGRESS')")
if n_exc:
    st.info(f"{n_exc} control exception(s) on the sales desk need attention.", icon=":material/rule:")
    st.page_link("ami/pages/shared/controls.py", label="Open my exceptions", icon=":material/arrow_forward:")
