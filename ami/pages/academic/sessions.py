"""Academic Manager - confirm sessions: what was delivered is what payroll pays (BR-07). Once HR approves a month's
payroll, its sessions are frozen."""
import pandas as pd
import streamlit as st

from ami import auth, db, ui

auth.require("ACADEMIC_MANAGER")
me = auth.employee_id()
bd = db.business_date()
ui.header("Confirm sessions", "Tick what was taught. A session the centre cancelled pays nobody - schedule a make-up in the class")

todo = db.df("""
    select s.session_id, s.session_date, c.class_code, to_char(s.start_time, 'HH24:MI') || '-' || to_char(s.end_time, 'HH24:MI') as time,
           s.planned_hours as hours, s.status,
           (select string_agg(e.name_code, ', ') from academic.class_staff_assignment a join hr.employee_role er using (employee_role_id)
              join hr.employee e using (employee_id)
             where a.class_id = s.class_id and s.session_date >= a.effective_from and (a.effective_to is null or s.session_date < a.effective_to)) as staff
    from academic.class_session s join academic.class c using (class_id)
    where s.session_date <= %(d)s and c.lifecycle_status <> 'CANCELLED'
      and (s.status = 'SCHEDULED' or (s.status in ('DELIVERED','MAKE_UP')
           and not exists (select 1 from academic.session_staff ss where ss.session_id = s.session_id)))
    order by s.session_date, s.start_time""", {"d": bd})

if todo.empty:
    st.success("Every session up to today is confirmed.", icon=":material/check_circle:")
else:
    st.caption(f"{len(todo)} session(s) to confirm. Older than 3 days are flagged by control ACA-02.")
    todo.insert(0, "outcome", "Delivered")
    edited = st.data_editor(
        todo, hide_index=True, key="ed", disabled=["session_date", "class_code", "time", "hours", "status", "staff"],
        column_order=["outcome", "session_date", "class_code", "time", "hours", "staff", "status"],
        column_config={"outcome": st.column_config.SelectboxColumn("Outcome", options=["Delivered", "Cancelled by centre", "Skip for now"], required=True),
                       "session_date": st.column_config.DateColumn("Date", format="ddd DD MMM"),
                       "session_id": None, "class_code": "Class", "hours": st.column_config.NumberColumn("Hours"),
                       "staff": "Staff paid", "status": "Status"})
    n_del = int((edited["outcome"] == "Delivered").sum())
    n_can = int((edited["outcome"] == "Cancelled by centre").sum())
    if st.button(f"Confirm {n_del} delivered and {n_can} cancelled", type="primary", disabled=(n_del + n_can) == 0):
        def _confirm():
            done = 0
            for r in edited.itertuples():
                if r.outcome == "Skip for now":
                    continue
                db.execute("select academic.confirm_session(%s, %s, %s)", (int(r.session_id), r.outcome == "Delivered", me))
                done += 1
            return done
        ui.act(_confirm, lambda n: f"{n} session(s) confirmed. Their hours are ready for payroll.")

st.subheader("Confirmed recently", anchor=False)
rec = db.df("""
    select s.session_date, c.class_code, s.status, string_agg(e.name_code || ' ' || ss.hours || 'h', ', ') as paid_hours,
           max(ss.confirmed_at) as confirmed_at
    from academic.class_session s join academic.class c using (class_id)
    left join academic.session_staff ss on ss.session_id = s.session_id
    left join hr.employee_role er on er.employee_role_id = ss.employee_role_id left join hr.employee e on e.employee_id = er.employee_id
    where s.session_date between %(d)s - 14 and %(d)s and (ss.session_id is not null or s.status = 'CANCELLED')
    group by s.session_id, s.session_date, c.class_code, s.status order by s.session_date desc, c.class_code""", {"d": bd})
if not rec.empty:
    rec["confirmed_at"] = pd.to_datetime(rec["confirmed_at"], utc=True).dt.tz_convert("Asia/Ho_Chi_Minh").dt.strftime("%d %b %H:%M")
    rec["status"] = rec["status"].str.replace("_", " ").str.title()
ui.table(rec, dates=["session_date"], key="rec", height=320)
