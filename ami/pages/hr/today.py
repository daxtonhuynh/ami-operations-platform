"""HR Manager - overview: people, hours to confirm and where the monthly payroll stands."""
import streamlit as st

from ami import auth, db, ui

auth.require("HR_MANAGER")
bd = db.business_date()
pid = bd.year * 100 + bd.month
ui.header("HR overview", f"{ui.date(bd)} · staff, hours and the payroll calendar (calculate on the 2nd, approve on the 3rd, Finance pays on the 5th)")

k = db.one("""
    select (select count(*) from hr.employee where end_date is null or end_date > %(d)s) as staff,
           (select count(*) from hr.work_shift where confirmed_at is null and shift_date < %(d)s) as shifts,
           (select coalesce(sum(confirmed_hours), 0) from rpt.v_teaching_hours where period_id = %(p)s) as hours,
           (select coalesce(sum(unconfirmed_hours), 0) from rpt.v_teaching_hours where period_id = %(p)s) as hours_open,
           (select status from payroll.payroll_run where period_id = %(p)s and run_type = 'REGULAR') as run_status,
           (select sum(net_pay) from payroll.payslip s join payroll.payroll_run r using (run_id)
             where r.period_id = (select max(period_id) from payroll.payroll_run where status = 'PAID')) as last_net
""", {"d": bd, "p": pid})
ui.kpis([("Active staff", k["staff"]), ("Shifts to confirm", k["shifts"], "Learning Advisor shifts not yet confirmed"),
         ("Teaching hours this month", f"{float(k['hours']):,.1f} h", f"{float(k['hours_open']):,.1f} h still to be confirmed by Academic"),
         (f"{ui.period_label(pid)} payroll", (k["run_status"] or "not created").title()),
         ("Last net payroll paid", ui.vnd_short(k["last_net"]))])

left, right = st.columns([1.2, 1], gap="large")
with left:
    st.subheader("Payroll runs", anchor=False)
    runs = db.df("""select r.period_id, r.status, r.calculated_at, r.approved_at, r.paid_on, count(s.*) as payslips,
                           sum(s.taxable_earnings + s.allowances) as gross, sum(s.net_pay) as net
                    from payroll.payroll_run r left join payroll.payslip s using (run_id)
                    group by r.run_id order by r.period_id desc limit 13""")
    runs["month"] = runs["period_id"].map(ui.period_label)
    runs["status"] = runs["status"].str.title()
    for c in ("calculated_at", "approved_at"):
        runs[c] = runs[c].dt.tz_convert("Asia/Ho_Chi_Minh").dt.strftime("%d %b")
    ui.table(runs[["month", "status", "payslips", "gross", "net", "calculated_at", "approved_at", "paid_on"]], money=["gross", "net"],
             dates=["paid_on"], key="runs")
    st.page_link("ami/pages/hr/payroll.py", label="Open payroll", icon=":material/arrow_forward:")
with right:
    st.subheader("Staff changes", anchor=False)
    ch = db.df("""
        select e.full_name, r.hr_code, r.role_code as role, r.contract_stage_code as stage, r.effective_from, r.effective_to,
               case when r.effective_to is not null then 'Ended' when r.effective_from > %(d)s - 60 then 'New' else 'Current' end as change
        from hr.employee_role r join hr.employee e using (employee_id)
        where r.effective_from > %(d)s - 120 or (r.effective_to between %(d)s - 120 and %(d)s + 30)
        order by coalesce(r.effective_to, r.effective_from) desc""", {"d": bd})
    ch["role"] = ch["role"].str.replace("_", " ").str.title()
    ui.table(ch, dates=["effective_from", "effective_to"], key="ch")
    st.subheader("Hours by person this month", anchor=False)
    th = db.df("""select full_name as staff, sum(confirmed_hours) as confirmed, sum(unconfirmed_hours) as unconfirmed
                  from rpt.v_teaching_hours where period_id = %s group by 1 order by 2 desc""", (pid,))
    ui.table(th, key="th")
