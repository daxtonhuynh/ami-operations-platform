"""HR Manager - staff and HR codes. One person can hold several roles (e.g. Academic Manager who also teaches IELTS);
each role is a dated HR code with its contract stage, salary code and cost centre."""
import datetime as dt

import streamlit as st

from ami import auth, db, ui

auth.require("HR_MANAGER")
bd = db.business_date()
ui.header("Staff & HR codes", "Changes are dated: a new contract stage ends the old HR code and starts a new one, so past pay is never rewritten")

roles = db.lookup("select role_code, name, pay_basis, hr_code_suffix from ref.staff_role order by name", "HR")
stages = db.lookup("select contract_stage_code from ref.contract_stage order by 1", "HR")
ccs = db.lookup("select cost_center_code, name from finance.cost_center order by 1", "HR")
emp = db.df("""
    select e.employee_id, e.employee_code, e.full_name, e.employment_type, e.hire_date, e.end_date,
           string_agg(r.role_code || ' (' || r.contract_stage_code || ')', ', ' order by r.role_code)
               filter (where r.effective_to is null or r.effective_to > %(d)s) as current_roles,
           (select sum(f.monthly_amount) from hr.employee_fixed_pay f join hr.employee_role r2 using (employee_role_id)
             where r2.employee_id = e.employee_id and %(d)s >= f.effective_from and (f.effective_to is null or %(d)s < f.effective_to)) as fixed_pay
    from hr.employee e left join hr.employee_role r using (employee_id)
    group by e.employee_id order by e.end_date is not null, e.employee_code""", {"d": bd})
emp["employment_type"] = emp["employment_type"].str.replace("_", " ").str.title()
t_list, t_new = st.tabs(["Staff", "New employee"])
with t_list:
    sel = ui.table(emp, money=["fixed_pay"], dates=["hire_date", "end_date"], hide=["employee_id"], key="emp", select=True, height=380)
    if sel:
        eid = int(sel["employee_id"])
        st.divider()
        st.subheader(sel["full_name"], anchor=False)
        hr = db.df("""select r.employee_role_id, r.hr_code, r.role_code, r.contract_stage_code as stage, r.salary_code, r.cost_center_code,
                             r.effective_from, r.effective_to, sr.hourly_rate as code_rate,
                             (select o.hourly_rate from hr.employee_rate_override o where o.employee_role_id = r.employee_role_id
                                and %(d)s >= o.effective_from and (o.effective_to is null or %(d)s < o.effective_to)) as personal_rate
                      from hr.employee_role r
                      left join ref.salary_rate sr on sr.salary_code = r.salary_code and %(d)s >= sr.effective_from
                                                   and (sr.effective_to is null or %(d)s < sr.effective_to)
                      where r.employee_id = %(e)s order by r.effective_from""", {"d": bd, "e": eid})
        ui.table(hr, money=["code_rate", "personal_rate"], dates=["effective_from", "effective_to"], hide=["employee_role_id"], key="hr")
        current = hr[hr["effective_to"].isna()]
        a1, a2, a3 = st.tabs(["Change contract stage / role", "Fixed monthly pay", "End employment"])
        with a1:
            with st.form("stage"):
                c1, c2, c3, c4 = st.columns(4)
                role = c1.selectbox("Role", roles["role_code"], format_func=lambda r: roles.set_index("role_code").loc[r, "name"])
                stage = c2.selectbox("Contract stage", stages["contract_stage_code"], format_func=str.title,
                                     index=int((stages["contract_stage_code"] == "OFFICIAL").idxmax()))
                cc = c3.selectbox("Cost centre", ccs["cost_center_code"], format_func=lambda c: f"{c} {ccs.set_index('cost_center_code').loc[c, 'name']}")
                frm = c4.date_input("From", value=bd + dt.timedelta(days=1))
                st.caption("If the person already holds this role, the current HR code ends the day before and a new HR code starts "
                           "(e.g. probation passed: new salary code from the date).")
                if st.form_submit_button("Save", type="primary"):
                    def _stage():
                        with db.write() as c:
                            sal = c.execute("select salary_code from ref.salary_code where role_code = %s and contract_stage_code = %s",
                                            (role, stage)).fetchone()
                            c.execute("""update hr.employee_role set effective_to = %s
                                         where employee_id = %s and role_code = %s and effective_to is null and effective_from < %s""",
                                      (frm, eid, role, frm))
                            base = sel["employee_code"] + roles.set_index("role_code").loc[role, "hr_code_suffix"]
                            n = c.execute("select count(*) + 1 as n from hr.employee_role where hr_code like %s", (base + "%",)).fetchone()["n"]
                            c.execute("""insert into hr.employee_role (hr_code, employee_id, role_code, contract_stage_code, salary_code,
                                                                         cost_center_code, effective_from)
                                         values (%s, %s, %s, %s, %s, %s, %s)""",
                                      (f"{base}{n:03d}", eid, role, stage, sal["salary_code"] if sal else None, cc, frm))
                    ui.act(_stage, "HR code saved. Pay follows the new salary code from the start date.")
        with a2:
            if current.empty:
                st.info("No current role.")
            else:
                with st.form("fixed"):
                    rid = st.selectbox("HR code", current["employee_role_id"], format_func=lambda i: current.set_index("employee_role_id").loc[i, "hr_code"])
                    amt = st.number_input("Monthly amount (VND)", min_value=0.0, step=500000.0, format="%.0f")
                    frm2 = st.date_input("From", value=bd.replace(day=1))
                    if st.form_submit_button("Save fixed pay"):
                        def _fixed():
                            with db.write() as c:
                                c.execute("""update hr.employee_fixed_pay set effective_to = %s
                                             where employee_role_id = %s and effective_to is null and effective_from < %s""", (frm2, int(rid), frm2))
                                c.execute("insert into hr.employee_fixed_pay (employee_role_id, monthly_amount, effective_from) values (%s, %s, %s)",
                                          (int(rid), round(amt), frm2))
                        ui.act(_fixed, "Fixed pay saved.")
        with a3:
            with st.form("end"):
                last = st.date_input("Last working day", value=bd)
                st.caption("Ends every current HR code. The Academic Manager must reassign the person's classes (control ACA-03 shows any class left without a teacher).")
                if st.form_submit_button("End employment"):
                    def _end():
                        with db.write() as c:
                            c.execute("update hr.employee set end_date = %s where employee_id = %s", (last, eid))
                            c.execute("""update hr.employee_role set effective_to = %s + 1
                                         where employee_id = %s and (effective_to is null or effective_to > %s + 1)""", (last, eid, last))
                    ui.act(_end, "Employment ended.")

with t_new:
    with st.form("new"):
        c1, c2, c3 = st.columns([2, 1, 1])
        name = c1.text_input("Full name *")
        short = c2.text_input("Short name *", placeholder="e.g. Nhi NY", help="Shown in rosters and timetables; must be unique")
        gender = c3.selectbox("Gender", ["FEMALE", "MALE", "OTHER", "UNDISCLOSED"], format_func=str.title)
        c4, c5, c6, c7 = st.columns(4)
        etype = c4.selectbox("Employment", ["PART_TIME", "FULL_TIME", "CONTRACTOR"], format_func=lambda x: x.replace("_", " ").title())
        hire = c5.date_input("Hire date", value=bd)
        role = c6.selectbox("First role", roles["role_code"], format_func=lambda r: roles.set_index("role_code").loc[r, "name"])
        stage = c7.selectbox("Contract stage", stages["contract_stage_code"], format_func=str.title)
        cc = st.selectbox("Cost centre", ccs["cost_center_code"], format_func=lambda c: f"{c} {ccs.set_index('cost_center_code').loc[c, 'name']}")
        email = st.text_input("Work email")
        if st.form_submit_button("Create employee", type="primary"):
            def _new():
                with db.write() as c:
                    code = c.execute("""select 'E' || lpad((coalesce(max(substring(employee_code from 2)::int), 0) + 1)::text, 3, '0') as code
                                        from hr.employee""").fetchone()["code"]
                    eid = c.execute("""insert into hr.employee (employee_code, full_name, name_code, gender, employment_type, home_cost_center_code,
                                                               hire_date, email) values (%s, %s, %s, %s, %s, %s, %s, %s) returning employee_id""",
                                    (code, name.strip(), short.strip(), gender, etype, cc, hire, email or None)).fetchone()["employee_id"]
                    sal = c.execute("select salary_code from ref.salary_code where role_code = %s and contract_stage_code = %s", (role, stage)).fetchone()
                    c.execute("""insert into hr.employee_role (hr_code, employee_id, role_code, contract_stage_code, salary_code, cost_center_code, effective_from)
                                 values (%s, %s, %s, %s, %s, %s, %s)""",
                              (f"{code}{roles.set_index('role_code').loc[role, 'hr_code_suffix']}001", eid, role, stage, sal["salary_code"] if sal else None, cc, hire))
                    return code
            if not (name.strip() and short.strip()):
                st.error("Name and short name are required.")
            else:
                ui.act(_new, lambda code: f"Employee {code} created.")
