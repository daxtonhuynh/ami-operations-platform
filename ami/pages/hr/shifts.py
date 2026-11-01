"""HR Manager - Learning Advisor shifts: hours worked (net of deductions) are what advisors are paid for."""
import datetime as dt

import streamlit as st

from ami import auth, db, ui

auth.require("HR_MANAGER")
me = auth.employee_id()
bd = db.business_date()
ui.header("Advisor shifts", "Confirm the week's shifts; mark absences and late arrivals before the payroll is calculated")

monday = bd - dt.timedelta(days=bd.weekday())
weeks = [monday - dt.timedelta(weeks=i) for i in range(0, 8)]
wk = st.selectbox("Week", weeks, index=1 if bd.weekday() < 2 else 0, format_func=lambda m: f"{m:%d %b} - {m + dt.timedelta(days=6):%d %b %Y}")
sh = db.df("""
    select w.shift_id, w.shift_date, e.full_name, to_char(w.start_time, 'HH24:MI') || '-' || to_char(w.end_time, 'HH24:MI') as time,
           w.hours, w.deduction_hours, w.status, w.confirmed_at is not null as confirmed
    from hr.work_shift w join hr.employee_role r using (employee_role_id) join hr.employee e using (employee_id)
    where w.shift_date between %s and %s order by w.shift_date, e.full_name, w.start_time""", (wk, wk + dt.timedelta(days=6)))
if sh.empty:
    ui.empty("No shift recorded this week.")
else:
    tot = sh[sh["status"] == "WORKED"].groupby("full_name").apply(lambda g: (g["hours"] - g["deduction_hours"]).sum(), include_groups=False)
    st.caption(" · ".join(f"{n}: {h:g} h" for n, h in tot.items()) + f" · {int((~sh['confirmed']).sum())} shift(s) not confirmed")
    ed = st.data_editor(sh, hide_index=True, key="ed", disabled=["shift_date", "full_name", "time", "hours", "confirmed"],
                        column_config={"shift_id": None, "shift_date": st.column_config.DateColumn("Date", format="ddd DD MMM"),
                                       "full_name": "Advisor", "time": "Time", "hours": "Hours",
                                       "deduction_hours": st.column_config.NumberColumn("Deduction (h)", min_value=0.0, step=0.25),
                                       "status": st.column_config.SelectboxColumn("Status", options=["WORKED", "ABSENT", "PLANNED"]),
                                       "confirmed": "Confirmed"})
    if st.button("Save and confirm the week", type="primary", disabled=wk > bd):
        def _save():
            with db.write() as c:
                for r in ed.itertuples():
                    c.execute("""update hr.work_shift set deduction_hours = %s, status = %s,
                                 confirmed_by = %s, confirmed_at = coalesce(confirmed_at, now())
                                 where shift_id = %s and shift_date <= %s""", (r.deduction_hours, r.status, me, int(r.shift_id), bd))
        ui.act(_save, "Week confirmed. The hours will be paid in the month's payroll.")

with st.expander("Add a shift"):
    las = db.df("""select r.employee_role_id, e.full_name, r.hr_code from hr.employee_role r join hr.employee e using (employee_id)
                   where r.role_code = 'LA' and (r.effective_to is null or r.effective_to > %s)""", (bd,))
    with st.form("add"):
        c1, c2, c3, c4 = st.columns(4)
        who = c1.selectbox("Advisor", las["employee_role_id"], format_func=lambda i: las.set_index("employee_role_id").loc[i, "full_name"])
        day = c2.date_input("Date", value=bd, max_value=bd)
        t0 = c3.time_input("Start", value=dt.time(13, 30), step=900)
        t1 = c4.time_input("End", value=dt.time(21, 0), step=900)
        if st.form_submit_button("Add shift"):
            ui.act(lambda: db.execute("""insert into hr.work_shift (employee_role_id, shift_date, start_time, end_time, status)
                                         values (%s, %s, %s, %s, 'WORKED')""", (int(who), day, t0, t1), fetch=False), "Shift added.")
