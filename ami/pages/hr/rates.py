"""HR Manager - pay rates: the salary-code rate card (dated) and personal rates agreed at hiring."""
import datetime as dt

import streamlit as st

from ami import auth, db, ui

auth.require("HR_MANAGER")
bd = db.business_date()
ui.header("Pay rates", "Hourly rates by salary code (role x contract stage). A new rate starts on a date; earlier months keep the old rate")

card = db.df("""
    select sc.salary_code, sr.name as role, sc.contract_stage_code as stage, r.hourly_rate, r.effective_from, r.effective_to,
           (r.effective_from <= %(d)s and (r.effective_to is null or %(d)s < r.effective_to)) as current
    from ref.salary_code sc join ref.staff_role sr using (role_code) join ref.salary_rate r using (salary_code)
    order by sc.salary_code, r.effective_from""", {"d": bd})
t_card, t_over, t_comm = st.tabs(["Rate card", "Personal rates", "Commission rule"])
with t_card:
    only = st.toggle("Current rates only", value=True)
    ui.table(card[card["current"]] if only else card, money=["hourly_rate"], dates=["effective_from", "effective_to"], key="card",
             hide=["current"], height=420)
    codes = card.drop_duplicates("salary_code")
    with st.form("rate"):
        st.markdown("**New rate from a date**")
        c1, c2, c3 = st.columns(3)
        code = c1.selectbox("Salary code", codes["salary_code"], format_func=lambda c: f"{c} · {codes.set_index('salary_code').loc[c, 'role']} "
                                                                                  f"({codes.set_index('salary_code').loc[c, 'stage'].title()})")
        rate = c2.number_input("Hourly rate (VND)", min_value=0.0, step=1000.0, format="%.0f")
        frm = c3.date_input("Effective from", value=(bd.replace(day=1) + dt.timedelta(days=32)).replace(day=1))
        if st.form_submit_button("Save new rate", type="primary"):
            def _rate():
                with db.write() as c:
                    c.execute("""update ref.salary_rate set effective_to = %s
                                 where salary_code = %s and effective_to is null and effective_from < %s""", (frm, code, frm))
                    c.execute("insert into ref.salary_rate (salary_code, hourly_rate, effective_from) values (%s, %s, %s)", (code, round(rate), frm))
            ui.act(_rate, f"New rate for {code} from {ui.date(frm)}.")
with t_over:
    ov = db.df("""select e.full_name, r.hr_code, o.hourly_rate, o.effective_from, o.effective_to, o.reason, a.full_name as approved_by
                  from hr.employee_rate_override o join hr.employee_role r using (employee_role_id) join hr.employee e using (employee_id)
                  left join hr.employee a on a.employee_id = o.approved_by order by o.effective_from desc""")
    st.caption("A personal rate replaces the salary-code rate for that HR code (e.g. agreed at the offer).")
    ui.table(ov, money=["hourly_rate"], dates=["effective_from", "effective_to"], key="ov")
with t_comm:
    cr = db.df("""select r.role_code, r.basis, r.rate, r.fixed_amount, r.earn_event, r.effective_from, r.effective_to, r.note
                  from payroll.commission_rule r order by r.effective_from""")
    st.caption("Sales commission is accrued automatically by the payroll calculation from this rule.")
    ui.table(cr, money=["fixed_amount"], pcts=["rate"], dates=["effective_from", "effective_to"], key="cr")
