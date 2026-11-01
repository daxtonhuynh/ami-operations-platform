"""Academic Manager - open a class: code, weekly timetable, teacher and assistant; every session is generated
(public holidays and Tet skipped). From that moment the advisors can sell it."""
import datetime as dt
import json

import streamlit as st

from ami import auth, db, ui

auth.require("ACADEMIC_MANAGER")
bd = db.business_date()
ui.header("Open a class", "The timetable generates every session; the end date follows from the course hours and the closure days")

courses = db.lookup("""select course_id, course_code, name, programme_code, standard_hours, default_hours_per_session
                       from ref.course where is_active order by course_id""", "AM")
rooms = db.lookup("select room_id, room_name, capacity, is_online from academic.room order by room_id", "AM")
staff = db.df("""select er.employee_role_id, e.full_name, er.role_code from hr.employee_role er join hr.employee e using (employee_id)
                 where (er.effective_to is null or er.effective_to > %s) and (e.end_date is null or e.end_date > %s)
                   and er.role_code in ('TEACHER_AE_COMM','TEACHER_IELTS','FOREIGN_TEACHER','TA_AE_COMM','AT_IELTS')
                 order by e.full_name""", (bd, bd))
teachers = staff[staff["role_code"].str.contains("TEACHER")]
assistants = staff[~staff["role_code"].str.contains("TEACHER")]
co = courses.set_index("course_id")

c1, c2, c3 = st.columns([2, 1, 1])
course = c1.selectbox("Course", courses["course_id"], format_func=lambda i: f"{co.loc[i, 'course_code']} - {co.loc[i, 'name']} "
                                                                          f"({float(co.loc[i, 'standard_hours']):g} h)")
mode = c2.selectbox("Delivery", ["OFFLINE", "ONLINE"], format_func=str.title)
start = c3.date_input("Start date", value=bd + dt.timedelta(days=21), min_value=bd)
d1, d2, d3, d4 = st.columns([2.2, 1, 1, 1])
days = d1.pills("Weekdays", [1, 2, 3, 4, 5, 6, 7], selection_mode="multi", default=[1, 3],
                format_func=lambda d: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][d - 1])
hps = float(co.loc[course, "default_hours_per_session"])
t0 = d2.time_input("Start time", value=dt.time(17, 30), step=900)
t1 = d3.time_input("End time", value=(dt.datetime.combine(bd, dt.time(17, 30)) + dt.timedelta(hours=hps)).time(), step=900)
cap = d4.number_input("Capacity", min_value=1, max_value=40, value=15)
r1, r2, r3 = st.columns(3)
room_opts = rooms[rooms["is_online"] == (mode == "ONLINE")]
room = r1.selectbox("Room", room_opts["room_id"], format_func=lambda i: f"{rooms.set_index('room_id').loc[i, 'room_name']} "
                                                                     f"({rooms.set_index('room_id').loc[i, 'capacity']} seats)")
teacher = r2.selectbox("Lead teacher", teachers["employee_role_id"],
                       format_func=lambda i: f"{staff.set_index('employee_role_id').loc[i, 'full_name']} · "
                                             f"{staff.set_index('employee_role_id').loc[i, 'role_code'].replace('_', ' ').title()}")
assistant = r3.selectbox("Assistant (optional)", [None] + assistants["employee_role_id"].tolist(),
                         format_func=lambda i: "None" if i is None else staff.set_index("employee_role_id").loc[i, "full_name"])
notes = st.text_input("Notes", placeholder="e.g. intake for the summer holidays")

pattern = json.dumps([{"weekday": d, "start": t0.strftime("%H:%M"), "end": t1.strftime("%H:%M")} for d in sorted(days or [])])
call = "select academic.open_class(%s::smallint, %s, %s, %s::smallint, %s::smallint, %s::jsonb, %s, %s, null, null, %s)"
params = (int(course), mode, start, int(cap), int(room), pattern, int(teacher), int(assistant) if assistant else None, notes or None)

if not days:
    st.info("Pick the weekdays of the timetable.")
    st.stop()
if t1 <= t0:
    st.error("The end time must be after the start time.")
    st.stop()
try:
    info, sessions, clash = db.preview(
        call, params,
        ("select class_code, start_date, planned_end_date, total_sessions, total_weeks from academic.class where class_id = %s", lambda k: (k,)),
        ("select session_no, session_date from academic.class_session where class_id = %s order by session_no", lambda k: (k,)),
        ("""select distinct o.class_code, s2.session_date from academic.class_session s1
            join academic.class_session s2 on s2.session_date = s1.session_date and s2.class_id <> s1.class_id
             and s2.start_time < s1.end_time and s1.start_time < s2.end_time and s2.status <> 'CANCELLED'
            join academic.class o on o.class_id = s2.class_id
            where s1.class_id = %s and (s2.room_id = s1.room_id) order by 2 limit 5""", lambda k: (k,)))
except db.BusinessRuleError as e:
    st.error(str(e))
    st.stop()
i = info.iloc[0]
with st.container(border=True):
    ui.kpis([("Class code", i["class_code"]), ("Sessions", int(i["total_sessions"])), ("Weeks", f"{float(i['total_weeks']):g}"),
             ("Last session", ui.date(i["planned_end_date"]))])
    if not clash.empty:
        st.warning("The room is already booked at that time: " + ", ".join(f"{r.class_code} on {r.session_date:%d %b}" for r in clash.itertuples()))
    skipped = db.df("select closure_date, reason from academic.closure_day where closure_date between %s and %s order by 1",
                    (start, i["planned_end_date"]))
    if not skipped.empty:
        st.caption("Closed days skipped: " + "; ".join(f"{r.closure_date:%d %b} {r.reason}" for r in skipped.itertuples()))
if st.button("Open the class for sale", type="primary", icon=":material/add_circle:"):
    ui.act(lambda: db.execute(call, params), lambda cid: f"Class {i['class_code']} is open. Advisors can enrol learners now.")
