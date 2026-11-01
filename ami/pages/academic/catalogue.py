"""Academic Manager - courses, rooms and the closure calendar (sessions are never generated on closure days)."""
import streamlit as st

from ami import auth, db, ui

auth.require("ACADEMIC_MANAGER")
bd = db.business_date()
ui.header("Courses & calendar", "The catalogue the advisors sell from and the days the centre is closed")

t_courses, t_days, t_rooms = st.tabs(["Courses", "Closure days", "Rooms"])
with t_courses:
    cr = db.df("""
        select c.course_code, c.name, p.name as programme, c.standard_hours, c.default_hours_per_session as hours_per_session,
               c.default_sessions_per_week as sessions_per_week, c.is_active,
               (select amount from ref.course_price x where x.course_id = c.course_id and x.delivery_mode_code = 'OFFLINE'
                  and x.price_basis = 'FULL_COURSE' and %(d)s >= x.effective_from and (x.effective_to is null or %(d)s < x.effective_to)) as offline_price,
               (select count(*) from academic.class k where k.course_id = c.course_id and k.lifecycle_status in ('OPEN','RUNNING')) as classes_now
        from ref.course c join ref.programme p using (programme_code) order by c.course_id""", {"d": bd})
    st.caption("Prices are owned by the Finance Manager (dated price list).")
    ui.table(cr, money=["offline_price"], key="cr", height=520)

with t_days:
    days = db.df("select closure_date, reason from academic.closure_day where closure_date >= %s - 60 order by 1", (bd,))
    ui.table(days, dates=["closure_date"], key="days", height=300)
    with st.form("closure"):
        c1, c2 = st.columns([1, 2])
        d = c1.date_input("Day", min_value=bd)
        reason = c2.text_input("Reason", placeholder="e.g. Teacher training day")
        st.caption("Only affects classes opened afterwards; existing sessions on that day must be cancelled and made up.")
        if st.form_submit_button("Add closure day"):
            ui.act(lambda: db.execute("insert into academic.closure_day (closure_date, reason) values (%s, %s)", (d, reason or "Closed"), fetch=False),
                   "Closure day added.")

with t_rooms:
    rooms = db.df("""select r.room_name, r.capacity, r.is_online, r.is_hybrid,
                            (select count(distinct c.class_id) from academic.class c where c.room_id = r.room_id and c.lifecycle_status in ('OPEN','RUNNING')) as classes_now
                     from academic.room r order by r.room_id""")
    ui.table(rooms, key="rooms")
