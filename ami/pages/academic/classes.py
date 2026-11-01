"""Classes & rosters: timetable, staff, sessions and the roster derived from enrolments (BR-03).
Academic Manager edits; the Director reads."""
import datetime as dt

import streamlit as st

from ami import auth, db, ui

auth.require("ACADEMIC_MANAGER", "DIRECTOR")
bd = db.business_date()
can_edit = auth.role() == "ACADEMIC_MANAGER"
ui.header("Classes & rosters", "A roster is never typed: it is the list of learners enrolled in the class")
ui.read_only_note()

c1, c2 = st.columns([2, 2])
lc = c1.pills("Status", ["RUNNING", "OPEN", "COMPLETED", "CANCELLED"], selection_mode="multi", default=["RUNNING", "OPEN"],
              format_func=str.title)
pr = c2.pills("Programme", ["AE", "COMM", "IELTS", "PE"], selection_mode="multi")
cls = db.df("""
    select v.class_id, v.class_code, v.course_name, v.delivery_mode_code as mode, v.start_date, v.end_date, v.sessions_delivered,
           v.total_sessions, v.learners, v.capacity, v.teachers, v.assistants, v.status_label, c.lifecycle_status, c.notes
    from rpt.v_class_status v join academic.class c using (class_id)
    where (%(lc)s::text[] is null or c.lifecycle_status = any(%(lc)s)) and (%(pr)s::text[] is null or v.programme_code = any(%(pr)s))
    order by c.start_date desc""", {"lc": lc or None, "pr": pr or None})
sel = ui.table(cls, dates=["start_date", "end_date"], hide=["class_id", "lifecycle_status", "notes"], key="cls", select=True, height=330,
               labels={"status_label": "Status"})
if not sel:
    st.stop()

cid = int(sel["class_id"])
c = db.one("""select c.*, co.course_code, co.name as course_name, r.room_name
              from academic.class c join ref.course co using (course_id) left join academic.room r using (room_id)
              where c.class_id = %s""", (cid,))
st.divider()
st.subheader(f"{c['class_code']} · {c['course_name']}", anchor=False)
pat = db.df("""select case weekday when 1 then 'Mon' when 2 then 'Tue' when 3 then 'Wed' when 4 then 'Thu' when 5 then 'Fri'
                                   when 6 then 'Sat' else 'Sun' end as day, to_char(start_time, 'HH24:MI') || '-' || to_char(end_time, 'HH24:MI') as time
               from academic.class_meeting_pattern where class_id = %s order by weekday""", (cid,))
st.caption(f"{c['room_name'] or '-'} · {', '.join(pat['day'] + ' ' + pat['time'])} · {float(c['total_hours']):g} hours · "
           f"{ui.date(c['start_date'])} to {ui.date(c['actual_end_date'] or c['planned_end_date'])} · {c['lifecycle_status'].title()}"
           + (f" · {c['notes']}" if c["notes"] else ""))

t_roster, t_staff, t_sessions, t_actions = st.tabs(["Roster", "Teachers", "Sessions", "Class actions"])
with t_roster:
    ros = db.df("""select student_code, learner, date_of_birth, grade_label, phone, status_code as status, enrolled_on,
                          learning_advisor, output_commitment from rpt.v_class_roster where class_id = %s order by learner""", (cid,))
    st.caption(f"{len(ros)} learner(s) · capacity {c['capacity']}")
    ui.table(ros, dates=["date_of_birth", "enrolled_on"], key="ros")

with t_staff:
    staff = db.df("""select a.assignment_id, e.full_name, er.hr_code, a.assignment_role as role, a.effective_from, a.effective_to
                     from academic.class_staff_assignment a join hr.employee_role er using (employee_role_id) join hr.employee e using (employee_id)
                     where a.class_id = %s order by a.effective_from, a.assignment_role""", (cid,))
    staff["role"] = staff["role"].str.replace("_", " ").str.title()
    ui.table(staff, dates=["effective_from", "effective_to"], hide=["assignment_id"], key="staff")
    if can_edit and c["lifecycle_status"] in ("OPEN", "RUNNING", "PLANNED"):
        roles = db.df("""select er.employee_role_id, e.full_name, er.role_code, er.hr_code from hr.employee_role er join hr.employee e using (employee_id)
                         where er.role_code in ('TEACHER_AE_COMM','TEACHER_IELTS','FOREIGN_TEACHER','TA_AE_COMM','AT_IELTS')
                           and (er.effective_to is null or er.effective_to > %s) and (e.end_date is null or e.end_date > %s)
                         order by e.full_name""", (bd, bd))
        with st.form("assign"):
            st.markdown("**Assign or replace a teacher**")
            a1, a2, a3 = st.columns([2, 1.2, 1])
            who = a1.selectbox("Staff", roles["employee_role_id"],
                               format_func=lambda i: f"{roles.set_index('employee_role_id').loc[i, 'full_name']} · "
                                                     f"{roles.set_index('employee_role_id').loc[i, 'role_code'].replace('_', ' ').title()}")
            arole = a2.selectbox("As", ["LEAD_TEACHER", "TEACHING_ASSISTANT", "CO_TEACHER"], format_func=lambda s: s.replace("_", " ").title())
            frm = a3.date_input("From", value=max(bd, c["start_date"]))
            replace = st.checkbox("End the current assignment in this role on the same day", value=True)
            if st.form_submit_button("Save assignment", type="primary"):
                def _assign():
                    with db.write() as conn:
                        if replace:
                            conn.execute("""update academic.class_staff_assignment set effective_to = %s
                                            where class_id = %s and assignment_role = %s and effective_to is null and effective_from < %s""",
                                         (frm, cid, arole, frm))
                            conn.execute("""delete from academic.class_staff_assignment
                                            where class_id = %s and assignment_role = %s and effective_from >= %s and employee_role_id <> %s""",
                                         (cid, arole, frm, int(who)))
                        conn.execute("""insert into academic.class_staff_assignment (class_id, employee_role_id, assignment_role, effective_from)
                                        values (%s, %s, %s, %s)""", (cid, int(who), arole, frm))
                ui.act(_assign, "Assignment saved. Only assigned staff can be paid for this class's sessions.")

with t_sessions:
    ses = db.df("""
        select s.session_id, s.session_no as no, s.session_date, to_char(s.start_time, 'HH24:MI') as start, s.planned_hours as hours, s.status,
               (select string_agg(e.name_code || ' ' || ss.hours || 'h', ', ') from academic.session_staff ss
                  join hr.employee_role er using (employee_role_id) join hr.employee e using (employee_id)
                 where ss.session_id = s.session_id) as confirmed_hours
        from academic.class_session s where s.class_id = %s order by s.session_no""", (cid,))
    ses["status"] = ses["status"].str.replace("_", " ").str.title()
    ui.table(ses, dates=["session_date"], hide=["session_id"], key="ses", height=360)
    if can_edit and c["lifecycle_status"] in ("OPEN", "RUNNING"):
        with st.form("makeup"):
            st.markdown("**Schedule a make-up session** (for a session the centre cancelled)")
            m1, m2, m3 = st.columns(3)
            mday = m1.date_input("Date", value=bd + dt.timedelta(days=7), min_value=bd)
            mst = m2.time_input("Start", value=dt.time(18, 0), step=900)
            men = m3.time_input("End", value=dt.time(19, 30), step=900)
            if st.form_submit_button("Add make-up session"):
                ui.act(lambda: db.execute("select academic.add_make_up_session(%s, %s, %s, %s)", (cid, mday, mst, men)),
                       "Make-up session added.")

with t_actions:
    if not can_edit:
        st.caption("Read-only.")
    elif c["lifecycle_status"] in ("OPEN", "PLANNED"):
        with st.form("cancel"):
            st.markdown("**Cancel the class** (before any session is delivered)")
            st.caption("Its learners go back to the waiting list so the advisors can move them to another class or cancel them; "
                       "Finance refunds where needed.")
            reason = st.text_input("Reason *", placeholder="e.g. only 3 learners registered (minimum 5)")
            sure = st.checkbox("I understand the learners will be told by their advisors")
            if st.form_submit_button("Cancel class", type="primary", disabled=False):
                if not (reason.strip() and sure):
                    st.error("Give a reason and tick the confirmation.")
                else:
                    ui.act(lambda: db.execute("select academic.cancel_class(%s, %s)", (cid, reason.strip())),
                           lambda n: f"Class cancelled; {n} learner(s) moved to the waiting list.")
    else:
        st.caption("Running and finished classes cannot be cancelled. Use make-up sessions or move learners instead.")
