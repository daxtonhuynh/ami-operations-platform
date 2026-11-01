"""Academic Manager - overview: classes running and starting, sessions to confirm, waiting-list demand."""
import streamlit as st

from ami import auth, db, ui

auth.require("ACADEMIC_MANAGER")
bd = db.business_date()
ui.header("Academic overview", f"{ui.date(bd)} · classes, teachers and the hours payroll will pay")

k = db.one("""
    select (select count(*) from academic.class where lifecycle_status = 'RUNNING') as running,
           (select count(*) from billing.enrollment where status_code = 'ACTIVE') as active_learners,
           (select count(*) from academic.class where lifecycle_status in ('OPEN','PLANNED') and start_date <= %(d)s + 30) as starting,
           (select count(*) from academic.class_session s join academic.class c using (class_id)
             where s.session_date < %(d)s and c.lifecycle_status <> 'CANCELLED'
               and (s.status = 'SCHEDULED' or (s.status in ('DELIVERED','MAKE_UP')
                    and not exists (select 1 from academic.session_staff ss where ss.session_id = s.session_id)))) as to_confirm,
           (select count(*) from billing.enrollment where status_code = 'WAITLISTED') as waitlist,
           (select round(avg(learners::numeric / nullif(capacity, 0)), 3) from rpt.v_class_status
             where class_id in (select class_id from academic.class where lifecycle_status = 'RUNNING')) as fill
""", {"d": bd})
ui.kpis([("Running classes", k["running"]), ("Active learners", k["active_learners"]),
         ("Average fill", ui.pct(k["fill"]), "Learners / capacity of running classes"),
         ("Starting in 30 days", k["starting"]), ("Sessions to confirm", k["to_confirm"], "Past sessions without confirmed hours"),
         ("Waiting list", k["waitlist"], "Enrolled learners without a class")])

left, right = st.columns([1.2, 1], gap="large")
with left:
    st.subheader("Classes starting soon", anchor=False)
    up = db.df("""
        select v.class_code, v.course_name, v.start_date, v.learners, v.capacity, coalesce(v.teachers, '- none -') as teacher,
               v.status_label
        from rpt.v_class_status v join academic.class c using (class_id)
        where c.lifecycle_status in ('OPEN','PLANNED') order by v.start_date""")
    if up.empty:
        ui.empty("No class is open for sale. Open the next intake.")
    else:
        if (up["teacher"] == "- none -").any():
            st.error("A class open for sale has no teacher (control ACA-03). Assign one in Classes & rosters.", icon=":material/person_off:")
        ui.table(up, dates=["start_date"], key="up")
    st.subheader("Sessions waiting for confirmation", anchor=False)
    sc = db.df("""
        select c.class_code, count(*) as sessions, min(s.session_date) as oldest, max(s.session_date) as latest
        from academic.class_session s join academic.class c using (class_id)
        where s.session_date < %(d)s and c.lifecycle_status <> 'CANCELLED'
          and (s.status = 'SCHEDULED' or (s.status in ('DELIVERED','MAKE_UP')
               and not exists (select 1 from academic.session_staff ss where ss.session_id = s.session_id)))
        group by c.class_code order by min(s.session_date)""", {"d": bd})
    if sc.empty:
        st.success("Every past session is confirmed.", icon=":material/check_circle:")
    else:
        ui.table(sc, dates=["oldest", "latest"], key="sc")
        st.page_link("ami/pages/academic/sessions.py", label="Confirm sessions", icon=":material/arrow_forward:")
with right:
    st.subheader("Waiting-list demand", anchor=False)
    wl = db.df("""
        select c.name as course, initcap(e.delivery_mode_code) as mode, count(*) as learners,
               min(e.enrolled_on) as waiting_since, count(*) filter (where e.enrolled_on < %s - 30) as waiting_over_30_days,
               string_agg(distinct e.notes, '; ') as notes
        from billing.enrollment e join ref.course c using (course_id)
        where e.status_code = 'WAITLISTED' group by 1, 2 order by 3 desc""", (bd,))
    if wl.empty:
        ui.empty("Nobody is waiting for a class.")
    else:
        st.caption("Paid learners waiting more than 30 days raise control BIL-07: their tuition cannot be earned until a class runs.")
        ui.table(wl, dates=["waiting_since"], key="wl")
        st.page_link("ami/pages/academic/open_class.py", label="Open a class", icon=":material/arrow_forward:")
    st.subheader("Teaching hours this month", anchor=False)
    th = db.df("""select h.full_name as staff, r.name as role, sum(h.confirmed_hours) as confirmed, sum(h.unconfirmed_hours) as unconfirmed
                  from rpt.v_teaching_hours h join ref.staff_role r using (role_code)
                  where h.period_id = %s group by 1, 2 order by 3 desc""", (bd.year * 100 + bd.month,))
    ui.table(th, key="th")
