"""HR Manager - payroll runs: manual lines, calculation from confirmed hours / shifts / fixed pay / commission rule,
approval (gated on session confirmation), payslips. Finance pays the approved run."""
import datetime as dt

import streamlit as st

from ami import auth, db, pdf, ui

auth.require("HR_MANAGER")
me = auth.employee_id()
bd = db.business_date()
ui.header("Payroll runs", "Hours x rate, fixed pay, commission and allowances; PIT withheld by the monthly rule")

runs = db.df("select run_id, period_id, status from payroll.payroll_run where run_type = 'REGULAR' order by period_id desc")
cur_pid = bd.year * 100 + bd.month
if cur_pid not in set(runs["period_id"]):
    if st.button(f"Create the {ui.period_label(cur_pid)} payroll run", icon=":material/add:"):
        ui.act(lambda: db.execute("insert into payroll.payroll_run (period_id) values (%s) returning run_id", (cur_pid,)), "Run created.")
if runs.empty:
    st.stop()
rid = st.selectbox("Month", runs["run_id"], format_func=lambda i: f"{ui.period_label(runs.set_index('run_id').loc[i, 'period_id'])} · "
                                                              f"{runs.set_index('run_id').loc[i, 'status'].title()}")
run = db.one("select r.*, p.status as period_status from payroll.payroll_run r join finance.fiscal_period p using (period_id) where run_id = %s", (rid,))
status = run["status"]

steps = ["DRAFT", "CALCULATED", "APPROVED", "PAID"]
cols = st.columns(4)
for i, s in enumerate(steps):
    done = steps.index(status) >= i
    cols[i].markdown(f"{':material/check_circle:' if done else ':material/radio_button_unchecked:'} **{s.title()}**")

c1, c2, c3 = st.columns([1, 1, 2])
if status in ("DRAFT", "CALCULATED"):
    if c1.button("Calculate", type="primary", icon=":material/calculate:", width="stretch"):
        ui.act(lambda: db.execute("select payroll.calculate_run(%s)", (rid,)), lambda n: f"Calculated: {n} payslip(s).")
if status == "CALCULATED":
    if c2.button("Approve", icon=":material/verified:", width="stretch"):
        ui.act(lambda: db.execute("select payroll.approve_run(%s, %s)", (rid, me), fetch=False),
               "Approved. Finance can pay it; the month's sessions are now frozen.")
if status == "APPROVED":
    c3.info("Approved - waiting for Finance to pay the salaries.", icon=":material/hourglass_top:")
if status == "PAID":
    c3.success(f"Paid on {ui.date(run['paid_on'])}.", icon=":material/paid:")

t_reg, t_lines, t_slip, t_comm = st.tabs(["Register", "Manual lines", "Payslips", "Commission"])
with t_reg:
    reg = db.df("""select employee_code, full_name, la_pay, teaching_pay, assistant_pay, fixed_salary, commission, other_pay, allowances,
                          taxable_earnings, pit_withheld, other_deductions, net_pay, balance_check
                   from rpt.v_payroll_register where run_id = %s order by employee_code""", (rid,))
    if reg.empty or status == "DRAFT":
        ui.empty("Not calculated yet. Calculate the run once the month's sessions and shifts are confirmed.")
    else:
        ui.kpis([("Payslips", len(reg)), ("Gross", ui.vnd(reg["taxable_earnings"].sum() + reg["allowances"].sum())),
                 ("PIT withheld", ui.vnd(reg["pit_withheld"].sum())), ("Net to pay", ui.vnd(reg["net_pay"].sum()))])
        ui.table(reg, money=[c for c in reg.columns if c not in ("employee_code", "full_name", "balance_check")], key="reg", height=420,
                 labels={"employee_code": "Code", "la_pay": "Advisor pay (shifts)", "teaching_pay": "Teaching pay",
                         "assistant_pay": "Assistant pay", "pit_withheld": "PIT withheld", "other_deductions": "Insurance etc.",
                         "balance_check": "Check"})
with t_lines:
    lines = db.df("""select l.payroll_line_id, e.full_name, et.name as earning, l.amount, l.note
                     from payroll.payroll_line l join hr.employee e using (employee_id) join ref.earning_type et using (earning_type_code)
                     where l.run_id = %s and l.source_type = 'MANUAL' order by e.full_name""", (rid,))
    st.caption("Allowances, bonuses and other items entered by HR. Calculated lines (hours, fixed pay, commission) are rebuilt at each calculation.")
    ui.table(lines, money=["amount"], hide=["payroll_line_id"], key="ml")
    if status in ("DRAFT", "CALCULATED"):
        emps = ui.emp_options()
        ets = db.lookup("select earning_type_code, name from ref.earning_type order by name", "HR")
        with st.form("line"):
            a, b, c, d = st.columns([1.5, 1.5, 1, 2])
            who = a.selectbox("Employee", emps["employee_id"], format_func=lambda i: emps.set_index("employee_id").loc[i, "full_name"])
            et = b.selectbox("Type", ets["earning_type_code"], format_func=lambda x: ets.set_index("earning_type_code").loc[x, "name"])
            amt = c.number_input("Amount", min_value=0.0, step=50000.0, format="%.0f")
            note = d.text_input("Note")
            if st.form_submit_button("Add line"):
                ui.act(lambda: db.execute("""insert into payroll.payroll_line (run_id, employee_id, earning_type_code, amount, source_type,
                                                account_code, cost_center_code, note)
                                             select %s, e.employee_id, %s, %s, 'MANUAL', finance.earning_account(%s, null, null, null),
                                                    e.home_cost_center_code, %s from hr.employee e where e.employee_id = %s""",
                                          (rid, et, round(amt), et, note or None, int(who)), fetch=False),
                       "Line added - recalculate to update the payslips.")
with t_slip:
    slips = db.df("""select s.payslip_id, e.employee_code, e.full_name, s.taxable_earnings, s.allowances, s.pit_withheld, s.other_deductions, s.net_pay
                     from payroll.payslip s join hr.employee e using (employee_id) where s.run_id = %s order by e.employee_code""", (rid,))
    if slips.empty:
        ui.empty("Calculate the run to produce payslips.")
    else:
        pick = st.selectbox("Payslip", slips["payslip_id"], format_func=lambda i: slips.set_index("payslip_id").loc[i, "full_name"])
        p = slips.set_index("payslip_id").loc[pick].to_dict()
        p.update({"period_label": ui.period_label(run["period_id"]), "status": status})
        ln = db.rows("""select et.name as earning, l.quantity_hours, l.rate, l.amount, l.note
                        from payroll.payroll_line l join ref.earning_type et using (earning_type_code)
                        join payroll.payslip s on s.run_id = l.run_id and s.employee_id = l.employee_id
                        where s.payslip_id = %s order by et.is_allowance, l.amount desc""", (int(pick),))
        de = db.rows("""select dt.name as deduction, d.amount from payroll.payslip_deduction d join ref.deduction_type dt using (deduction_type_code)
                        where d.payslip_id = %s""", (int(pick),))
        st.dataframe([{k: v for k, v in r.items()} for r in ln], hide_index=True)
        centre = db.lookup("select setting_key, setting_value from ref.app_setting where setting_key like 'centre_%%'", "HR")
        cfg = dict(zip(centre["setting_key"], centre["setting_value"]))
        st.download_button(f"Download payslip ({ui.vnd(p['net_pay'])} net)", pdf.payslip_pdf(p, ln, de, cfg.get("centre_name", ""), cfg.get("centre_address", "")),
                           file_name=f"payslip-{p['employee_code']}-{run['period_id']}.pdf", mime="application/pdf", icon=":material/download:")
with t_comm:
    cm = db.df("""select en.enrollment_code, en.status_code as enrolment_status, e.full_name as advisor, c.amount, c.status
                  from payroll.commission c join billing.enrollment en using (enrollment_id)
                  join hr.employee e on e.employee_id = c.employee_id where c.earned_period_id = %s order by e.full_name""", (run["period_id"],))
    st.caption("Accrued by the rule when an enrolment becomes fully paid in the month (control PAY-02 watches drop-outs).")
    ui.table(cm, money=["amount"], key="cm")
