"""Learning Advisor - lead pipeline: new inquiries, follow-ups, test booking, lost reasons."""
import datetime as dt

import streamlit as st

from ami import auth, db, ui

auth.require("LEARNING_ADVISOR")
me = auth.employee_id()
bd = db.business_date()
ui.header("Leads", "Every inquiry from first contact to enrolment or a recorded lost reason")

channels = db.lookup("select channel_code, name from ref.acquisition_channel order by name", "LA")
programmes = db.lookup("select programme_code, name from ref.programme order by name", "LA")
schools = db.lookup("select school_id, school_name from ref.school order by school_name", "LA")
ch_name = dict(zip(channels["channel_code"], channels["name"]))
pr_name = dict(zip(programmes["programme_code"], programmes["name"]))

tab_pipe, tab_new = st.tabs(["Pipeline", "New lead"])

# ------------------------------------------------------------------------------------------------ pipeline
with tab_pipe:
    c1, c2, c3 = st.columns([1.4, 2, 1.4], vertical_alignment="bottom")
    scope = c1.segmented_control("Show", ["My open leads", "All open leads", "Closed (last 90 days)"], default="My open leads",
                                 key="lead_scope")
    progs = c2.pills("Programme", list(pr_name), format_func=lambda p: pr_name[p], selection_mode="multi", key="lead_prog")
    search = c3.text_input("Search name or phone", key="lead_search", placeholder="e.g. Nguyễn or 0100")
    where = ["true"]
    if scope == "My open leads":
        where.append("l.closed_on is null and l.owner_employee_id = %(me)s")
    elif scope == "All open leads":
        where.append("l.closed_on is null")
    else:
        where.append("l.closed_on >= %(d)s - 90")
    if progs:
        where.append("l.programme_code = any(%(progs)s)")
    if search:
        where.append("(s.full_name ilike %(q)s or s.phone ilike %(q)s or g.phone ilike %(q)s or s.student_code ilike %(q)s)")
    leads = db.df(f"""
        select l.lead_id, s.student_code, s.full_name as learner, l.programme_code as programme, ls.name as stage,
               coalesce(q.name, '') as qualification, l.lead_date, l.next_follow_up_on, e.name_code as advisor,
               coalesce(c.name, '-') as channel, l.closed_on,
               case when l.qualification_code = 'CONVERTED' then 'Enrolled'
                    when l.closed_on is not null then 'Lost: ' || coalesce(lr.name, '') else 'Open' end as outcome
        from crm.lead l join crm.student s using (student_id) join ref.lead_stage ls using (stage_code)
        left join ref.qualification_status q using (qualification_code)
        left join ref.acquisition_channel c using (channel_code)
        left join ref.lost_reason lr on lr.reason_code = l.lost_reason_code
        left join hr.employee e on e.employee_id = l.owner_employee_id
        left join crm.student_guardian sg on sg.student_id = s.student_id and sg.is_primary_contact
        left join crm.guardian g on g.guardian_id = sg.guardian_id
        where {' and '.join(where)}
        order by l.closed_on is not null, l.next_follow_up_on nulls last, l.lead_date desc limit 400""",
                  {"me": me, "d": bd, "progs": progs or None, "q": f"%{search}%"})
    st.caption(f"{len(leads)} lead(s). Select a row to work on it.")
    sel = ui.table(leads, dates=["lead_date", "next_follow_up_on", "closed_on"], hide=["lead_id"], key="leads_tbl",
                   select=True, height=330)

    if sel:
        lid = int(sel["lead_id"])
        lead = db.one("""
            select l.*, s.full_name, s.student_code, s.phone, s.email, s.date_of_birth, s.grade_label, sc.school_name,
                   g.full_name as guardian, g.phone as guardian_phone, e.full_name as owner
            from crm.lead l join crm.student s using (student_id)
            left join ref.school sc on sc.school_id = s.school_id
            left join crm.student_guardian sg on sg.student_id = s.student_id and sg.is_primary_contact
            left join crm.guardian g on g.guardian_id = sg.guardian_id
            left join hr.employee e on e.employee_id = l.owner_employee_id
            where l.lead_id = %s""", (lid,))
        st.divider()
        h1, h2 = st.columns([2, 1])
        h1.subheader(f"{lead['full_name']}  ·  {lead['student_code']}", anchor=False)
        h1.caption(" · ".join(x for x in [
            pr_name.get(lead["programme_code"], ""), lead["grade_label"] or "", lead["school_name"] or "",
            f"phone {lead['phone']}" if lead["phone"] else "",
            f"guardian {lead['guardian']} ({lead['guardian_phone']})" if lead["guardian"] else "",
            f"advisor {lead['owner'] or 'unassigned'}", f"via {ch_name.get(lead['channel_code'], 'unknown channel')}"] if x))
        is_open = lead["closed_on"] is None
        with h2:
            if is_open and lead["stage_code"] == "TESTED":
                if st.button("Enrol this learner", type="primary", icon=":material/how_to_reg:", width="stretch"):
                    st.session_state["enrol_lead_id"] = lid
                    st.switch_page("ami/pages/sales/enrol.py")
            elif not is_open:
                st.badge("Enrolled" if lead["qualification_code"] == "CONVERTED" else "Closed - lost",
                         color="green" if lead["qualification_code"] == "CONVERTED" else "gray")

        act_col, hist_col = st.columns([1, 1.1], gap="large")
        with hist_col:
            st.markdown("**History**")
            hist = db.df("""
                select a.activity_at as at, a.activity_type as type, coalesce(o.name, '') as outcome, a.note, e.name_code as by
                from crm.lead_activity a left join ref.consultation_outcome o on o.outcome_code = a.outcome_code
                left join hr.employee e on e.employee_id = a.employee_id where a.lead_id = %(id)s
                union all
                select h.entered_at, 'STAGE', ls.name, null, null from crm.lead_stage_history h
                join ref.lead_stage ls on ls.stage_code = h.stage_code where h.lead_id = %(id)s
                union all
                select t.scheduled_at, 'TEST', t.status, t.test_type || coalesce(' - level ' || pl.level_code, ''), null
                from crm.placement_test t left join ref.proficiency_level pl on pl.level_id = t.overall_level_id where t.lead_id = %(id)s
                order by 1 desc""", {"id": lid})
            if not hist.empty:
                hist["at"] = hist["at"].dt.tz_convert("Asia/Ho_Chi_Minh").dt.strftime("%d %b %H:%M")
            ui.table(hist, key="hist", height=300)
        with act_col:
            if not is_open:
                st.info("This lead is closed.", icon=":material/lock:")
            else:
                a_log, a_test, a_lost = st.tabs(["Log contact", "Book test", "Mark as lost"])
                outcomes = db.lookup("select outcome_code, name from ref.consultation_outcome order by name", "LA")
                with a_log:
                    with st.form("log"):
                        t = st.segmented_control("Contact", ["CALL", "CHAT", "MEETING", "EMAIL", "NOTE"], default="CALL",
                                                 format_func=str.title)
                        o = st.selectbox("Outcome", outcomes["outcome_code"], format_func=lambda c: outcomes.set_index("outcome_code").loc[c, "name"],
                                         index=int((outcomes["outcome_code"] == "PENDING").idxmax()))
                        note = st.text_area("Note", placeholder="What was discussed, what was promised")
                        nxt = st.date_input("Next follow-up", value=bd + dt.timedelta(days=2), min_value=bd)
                        if st.form_submit_button("Save", type="primary"):
                            def _log():
                                with db.write() as c:
                                    c.execute("""insert into crm.lead_activity (lead_id, activity_type, activity_at, employee_id, outcome_code, note)
                                                 values (%s, %s, now(), %s, %s, %s)""", (lid, t or "NOTE", me, o, note or None))
                                    c.execute("""update crm.lead set consultation_outcome_code = %s, next_follow_up_on = %s,
                                                 stage_code = case when stage_code = 'NEW' and %s in ('NO_ANSWER','PHONE_OFF') then 'CONTACTED_NO_RESPONSE' else stage_code end,
                                                 owner_employee_id = coalesce(owner_employee_id, %s)
                                                 where lead_id = %s""", (o, nxt, o, me, lid))
                            ui.act(_log, "Contact logged.")
                with a_test:
                    with st.form("book"):
                        default_type = {"IELTS": "IELTS", "COMM": "COMMUNICATION"}.get(lead["programme_code"], "APPLIED_ENGLISH")
                        types = ["APPLIED_ENGLISH", "COMMUNICATION", "IELTS"]
                        tt = st.selectbox("Test", types, index=types.index(default_type), format_func=lambda x: x.replace("_", " ").title())
                        c1, c2 = st.columns(2)
                        tday = c1.date_input("Date", value=bd + dt.timedelta(days=2), min_value=bd)
                        ttime = c2.time_input("Time", value=dt.time(9, 30), step=900)
                        if st.form_submit_button("Book test", type="primary"):
                            def _book():
                                with db.write() as c:
                                    c.execute("""insert into crm.placement_test (lead_id, test_type, scheduled_at)
                                                 values (%s, %s, (%s::timestamp at time zone 'Asia/Ho_Chi_Minh'))""",
                                              (lid, tt, dt.datetime.combine(tday, ttime)))
                                    c.execute("""update crm.lead set stage_code = 'TEST_BOOKED', next_follow_up_on = %s,
                                                 qualification_code = coalesce(qualification_code, 'HIGH_POTENTIAL'),
                                                 owner_employee_id = coalesce(owner_employee_id, %s) where lead_id = %s""", (tday, me, lid))
                            ui.act(_book, f"Placement test booked for {ui.date(tday)}.")
                with a_lost:
                    reasons = db.lookup("select reason_code, name from ref.lost_reason order by name", "LA")
                    with st.form("lost"):
                        r = st.selectbox("Reason", reasons["reason_code"], format_func=lambda c: reasons.set_index("reason_code").loc[c, "name"])
                        o2 = st.selectbox("Last outcome", outcomes["outcome_code"],
                                          format_func=lambda c: outcomes.set_index("outcome_code").loc[c, "name"])
                        q = st.radio("Worth contacting again later?", ["LOW_POTENTIAL", "NOT_A_PROSPECT"], horizontal=True,
                                     format_func=lambda x: "Yes, low potential" if x == "LOW_POTENTIAL" else "No")
                        note2 = st.text_input("Detail (optional)")
                        if st.form_submit_button("Close as lost"):
                            ui.act(lambda: db.execute("""update crm.lead set lost_reason_code = %s, consultation_outcome_code = %s,
                                                         qualification_code = %s, lost_reason_note = %s, closed_on = %s, next_follow_up_on = null
                                                         where lead_id = %s""", (r, o2, q, note2 or None, bd, lid), fetch=False),
                                   "Lead closed. The reason feeds the funnel report.")

# ------------------------------------------------------------------------------------------------ new lead
with tab_new:
    st.caption("A learner is registered once (one student code for life). Search first if they have studied with us.")
    with st.form("new_lead", clear_on_submit=False):
        st.markdown("**Learner**")
        c1, c2, c3 = st.columns([2, 1, 1])
        name = c1.text_input("Full name *")
        gender = c2.selectbox("Gender", ["FEMALE", "MALE", "OTHER", "UNDISCLOSED"], format_func=str.title)
        dob = c3.date_input("Date of birth", value=None, min_value=dt.date(1950, 1, 1), max_value=bd)
        c4, c5, c6, c7 = st.columns([1, 1.4, 1.6, 1])
        phone = c4.text_input("Phone (adult learner)")
        email = c5.text_input("Email")
        school = c6.selectbox("School", [None] + schools["school_id"].tolist(),
                              format_func=lambda i: "-" if i is None else schools.set_index("school_id").loc[i, "school_name"])
        grade = c7.text_input("Grade / status", placeholder="Grade 5, University, Working")
        st.markdown("**Parent or guardian** (for learners under 16 - they pay and receive the calls)")
        g1, g2, g3 = st.columns([2, 1, 1])
        gname = g1.text_input("Guardian name")
        gphone = g2.text_input("Guardian phone")
        grel = g3.selectbox("Relationship", ["MOTHER", "FATHER", "GRANDPARENT", "SISTER", "BROTHER", "AUNT", "UNCLE", "OTHER_RELATIVE"], format_func=lambda x: x.replace("_", " ").title())
        st.markdown("**Inquiry**")
        i1, i2, i3, i4 = st.columns(4)
        prog = i1.selectbox("Programme *", list(pr_name), format_func=lambda p: pr_name[p])
        mode = i2.selectbox("Delivery", ["OFFLINE", "ONLINE"], format_func=str.title)
        chan = i3.selectbox("Channel *", channels["channel_code"], format_func=lambda c: ch_name[c])
        fu = i4.date_input("First follow-up", value=bd + dt.timedelta(days=1), min_value=bd)
        notes = st.text_area("Notes", placeholder="Goals, preferred schedule, questions asked")
        dup_ok = st.checkbox("Create even if a learner with the same phone exists")
        if st.form_submit_button("Create lead", type="primary"):
            if not name.strip():
                st.error("The learner's name is required.")
            else:
                dup = None
                if (phone or gphone) and not dup_ok:
                    dup = db.one("""select s.student_code, s.full_name from crm.student s
                                    left join crm.student_guardian sg using (student_id) left join crm.guardian g using (guardian_id)
                                    where (%(p)s <> '' and s.phone = %(p)s) or (%(gp)s <> '' and g.phone = %(gp)s) limit 1""",
                                 {"p": phone.strip(), "gp": gphone.strip()})
                if dup:
                    st.warning(f"{dup['student_code']} {dup['full_name']} already uses this phone. Open their record, or tick the box to create anyway.")
                else:
                    def _create():
                        with db.write() as c:
                            sid = c.execute("""insert into crm.student (full_name, gender, date_of_birth, phone, email, school_id, grade_label, first_contact_date)
                                               values (%s, %s, %s, %s, %s, %s, %s, %s) returning student_id, student_code""",
                                            (name.strip(), gender, dob, phone or None, email or None, school, grade or None, bd)).fetchone()
                            if gname.strip():
                                gid = c.execute("insert into crm.guardian (full_name, phone) values (%s, %s) returning guardian_id",
                                                (gname.strip(), gphone or None)).fetchone()["guardian_id"]
                                c.execute("""insert into crm.student_guardian (student_id, guardian_id, relationship_code, is_primary_contact, is_payer)
                                             values (%s, %s, %s, true, true)""", (sid["student_id"], gid, grel))
                            c.execute("""insert into crm.lead (student_id, lead_date, owner_employee_id, channel_code, programme_code,
                                                               delivery_mode_code, stage_code, next_follow_up_on, notes)
                                         values (%s, %s, %s, %s, %s, %s, 'NEW', %s, %s)""",
                                      (sid["student_id"], bd, me, chan, prog, mode, fu, notes or None))
                            return sid["student_code"]
                    ui.act(_create, lambda code: f"Lead created - learner {code}. It is in your pipeline.")
