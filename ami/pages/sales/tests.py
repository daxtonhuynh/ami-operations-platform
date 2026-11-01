"""Learning Advisor - placement tests: booked tests and their results (entered from the marked test paper)."""
import streamlit as st

from ami import auth, db, ui

auth.require("LEARNING_ADVISOR")
me = auth.employee_id()
bd = db.business_date()
ui.header("Placement tests", "Results decide the course a learner is placed in and the level the centre commits to")

booked = db.df("""
    select t.test_id, t.lead_id, t.scheduled_at, s.full_name as learner, s.student_code, t.test_type, l.programme_code as programme,
           e.name_code as advisor, (t.scheduled_at::date < %(d)s) as overdue
    from crm.placement_test t join crm.lead l using (lead_id) join crm.student s using (student_id)
    left join hr.employee e on e.employee_id = l.owner_employee_id
    where t.status = 'BOOKED' order by t.scheduled_at""", {"d": bd})

st.subheader("Booked tests", anchor=False)
if booked.empty:
    ui.empty("No test is waiting for a result.")
    sel = None
else:
    show = booked.copy()
    show["scheduled_at"] = show["scheduled_at"].dt.tz_convert("Asia/Ho_Chi_Minh").dt.strftime("%a %d %b %H:%M")
    show["test_type"] = show["test_type"].str.replace("_", " ").str.title()
    st.caption("Select a test to record its result. Tests in the past without a result are marked as overdue.")
    sel = ui.table(show, hide=["test_id", "lead_id"], key="booked", select=True,
                   column_order=["scheduled_at", "learner", "student_code", "test_type", "programme", "advisor", "overdue"])

if sel:
    tid, lid = int(sel["test_id"]), int(sel["lead_id"])
    t = booked.set_index("test_id").loc[tid]
    scale = "IELTS" if t["test_type"] == "IELTS" else "CEFR"
    levels = db.lookup("select level_id, level_code, level_rank from ref.proficiency_level where scale_code = %s order by level_rank",
                       "LA", (scale,))
    courses = db.lookup("select course_id, course_code, name, programme_code from ref.course where is_active order by course_id", "LA")
    teachers = db.lookup("""select distinct e.employee_id, e.full_name from hr.employee e join hr.employee_role r using (employee_id)
                            where r.role_code in ('TEACHER_AE_COMM','TEACHER_IELTS','ACADEMIC_MANAGER','FOREIGN_TEACHER')
                              and (e.end_date is null or e.end_date > current_date) order by 2""", "LA")
    st.divider()
    st.subheader(f"Result for {sel['learner']}", anchor=False)
    with st.form("result"):
        status = st.segmented_control("Outcome", ["COMPLETED", "NO_SHOW", "CANCELLED"], default="COMPLETED",
                                      format_func=lambda s: s.replace("_", "-").title())
        c1, c2, c3 = st.columns(3)
        lvl = c1.selectbox("Overall level", levels["level_id"], format_func=lambda i: levels.set_index("level_id").loc[i, "level_code"],
                           index=min(3, len(levels) - 1))
        marker = c2.selectbox("Marked by", teachers["employee_id"], format_func=lambda i: teachers.set_index("employee_id").loc[i, "full_name"])
        prog_courses = courses[courses["programme_code"] == t["programme"]] if t["programme"] else courses
        rec = c3.selectbox("Recommended course", prog_courses["course_id"],
                           format_func=lambda i: f"{courses.set_index('course_id').loc[i, 'course_code']} - {courses.set_index('course_id').loc[i, 'name']}")
        skills = {}
        if scale == "IELTS":
            st.caption("Skill bands")
            cols = st.columns(4)
            for col, skill in zip(cols, ["LISTENING", "READING", "WRITING", "SPEAKING"]):
                skills[skill] = col.selectbox(skill.title(), levels["level_id"], key=f"sk_{skill}",
                                              format_func=lambda i: levels.set_index("level_id").loc[i, "level_code"], index=min(3, len(levels) - 1))
        note = st.text_input("Comment for the parent / learner")
        if st.form_submit_button("Save result", type="primary"):
            def _save():
                with db.write() as c:
                    if status == "COMPLETED":
                        c.execute("""update crm.placement_test set status = 'COMPLETED', assessed_by = %s, overall_level_id = %s,
                                     completed_at = now(), notes = %s where test_id = %s""", (marker, lvl, note or None, tid))
                        for skill, level_id in skills.items():
                            c.execute("""insert into crm.placement_test_score (test_id, skill_code, level_id) values (%s, %s, %s)
                                         on conflict (test_id, skill_code) do update set level_id = excluded.level_id""", (tid, skill, level_id))
                        c.execute("""update crm.lead set stage_code = 'TESTED', recommended_course_id = %s, consultation_outcome_code = 'PENDING',
                                     next_follow_up_on = %s where lead_id = %s""", (rec, bd, lid))
                    else:
                        c.execute("update crm.placement_test set status = %s, notes = %s where test_id = %s", (status, note or None, tid))
                        if status == "NO_SHOW":
                            c.execute("update crm.lead set stage_code = 'NO_SHOW', next_follow_up_on = %s where lead_id = %s", (bd, lid))
            ui.act(_save, "Result saved. The lead is ready for enrolment." if status == "COMPLETED" else "Test updated.")

st.subheader("Recent results", anchor=False)
recent = db.df("""
    select t.completed_at::date as tested_on, s.full_name as learner, t.test_type, pl.level_code as level, c.course_code as recommended,
           case when l.qualification_code = 'CONVERTED' then 'Enrolled' when l.closed_on is not null then 'Lost' else 'Deciding' end as outcome
    from crm.placement_test t join crm.lead l using (lead_id) join crm.student s using (student_id)
    left join ref.proficiency_level pl on pl.level_id = t.overall_level_id
    left join ref.course c on c.course_id = l.recommended_course_id
    where t.status = 'COMPLETED' and t.completed_at >= %(d)s::date - 30
    order by t.completed_at desc""", {"d": bd})
recent["test_type"] = recent["test_type"].str.replace("_", " ").str.title()
ui.table(recent, dates=["tested_on"], key="recent", height=320)
