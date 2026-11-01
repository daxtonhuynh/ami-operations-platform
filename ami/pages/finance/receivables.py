"""Receivables & collections: ageing, overdue learners, write-offs of dropped-out balances, refunds."""
import streamlit as st

from ami import auth, db, ui

auth.require("FINANCE_MANAGER", "DIRECTOR")
me = auth.employee_id()
bd = db.business_date()
ui.header("Receivables & collections", "Tuition due and not yet paid, by age. Dropped-out balances are written off as bad debt (accrual P&L only)")
ui.read_only_note()

age = db.df("""select ageing_bucket, count(*) as instalments, sum(remaining) as amount
               from rpt.v_schedule_line_status where remaining > 0 and is_billable group by 1""")
order = ["Not yet due", "1-30 days", "31-60 days", "61-90 days", "90+ days"]
age = age.set_index("ageing_bucket").reindex(order).fillna(0).reset_index()
ui.kpis([(b, ui.vnd_short(a), f"{int(n)} instalment(s)") for b, n, a in age[["ageing_bucket", "instalments", "amount"]].itertuples(index=False)])

t_over, t_wo, t_ref = st.tabs(["Overdue learners", "Dropped out - balance due", "Refunds"])
with t_over:
    od = db.df("""
        select b.enrollment_code, b.learner, b.course_name, b.class_code, b.status_code as status, b.overdue_amount as overdue,
               b.outstanding_receivable as outstanding, max(l.days_overdue) as max_days, e.name_code as advisor,
               coalesce(s.phone, g.phone) as phone, x.status as exception, x.resolution_note as follow_up
        from rpt.v_enrollment_balance b join rpt.v_schedule_line_status l using (enrollment_id)
        join crm.student s on s.student_id = b.student_id
        left join crm.student_guardian sg on sg.student_id = s.student_id and sg.is_payer left join crm.guardian g on g.guardian_id = sg.guardian_id
        left join hr.employee e on e.employee_id = b.sales_owner_employee_id
        left join lateral (select x.status, x.resolution_note from ctl.control_exception x join billing.payment_schedule ps on ps.schedule_line_id = x.entity_id
                           where x.control_code = 'BIL-03' and ps.enrollment_id = b.enrollment_id order by x.opened_at desc limit 1) x on true
        where b.overdue_amount > 0 and l.days_overdue > 0
        group by b.enrollment_id, b.enrollment_code, b.learner, b.course_name, b.class_code, b.status_code, b.overdue_amount,
                 b.outstanding_receivable, e.name_code, s.phone, g.phone, x.status, x.resolution_note
        order by max(l.days_overdue) desc""")
    st.caption("Advisors chase these from their 'My day' page; instalments more than 30 days late raise control BIL-03.")
    ui.table(od, money=["overdue", "outstanding"], key="od", height=420)

with t_wo:
    wo = db.df("""select b.enrollment_id, b.enrollment_code, b.learner, b.course_name, b.status_code as status, e.status_changed_on as left_on,
                         b.recognised_total as earned, b.collected - b.refunded as paid, b.outstanding_receivable as balance
                  from rpt.v_enrollment_balance b join billing.enrollment e using (enrollment_id)
                  where b.uncollectible_not_written_off > 0 order by e.status_changed_on""")
    if wo.empty:
        ui.empty("No dropped-out balance is left.")
    else:
        st.caption("Earned (taught) but unpaid tuition of learners who left. Writing off removes the receivable and books bad debt "
                   "in the accrual P&L; the cash P&L never counted it.")
        sel = ui.table(wo, money=["earned", "paid", "balance"], dates=["left_on"], hide=["enrollment_id"], key="wo", select=True)
        if sel and not auth.read_only():
            with st.form("wo_f"):
                amt = st.number_input("Amount to write off (VND)", min_value=0.0, max_value=float(sel["balance"]), value=float(sel["balance"]),
                                      step=10000.0, format="%.0f")
                reason = st.text_input("Reason *", value="Learner left; reminders unanswered")
                if st.form_submit_button("Write off", type="primary"):
                    ui.act(lambda: db.execute("select billing.write_off_balance(%s, %s, %s, %s, %s)",
                                              (int(sel["enrollment_id"]), bd, round(amt), reason, me)), "Balance written off.")

with t_ref:
    refs = db.df("""select f.refund_date, en.enrollment_code, s.full_name as learner, f.amount, f.reason, f.reduces_contract,
                           e.name_code as approved_by
                    from billing.refund f join billing.enrollment en using (enrollment_id) join crm.student s on s.student_id = en.student_id
                    left join hr.employee e on e.employee_id = f.approved_by order by f.refund_date desc""")
    ui.table(refs, money=["amount"], dates=["refund_date"], key="refs", height=260,
             labels={"reduces_contract": "Contract reduced"})
    if not auth.read_only():
        st.markdown("**New refund**")
        q = st.text_input("Find the enrolment", placeholder="ENR code or learner name")
        if q:
            cand = db.df("""select enrollment_id, enrollment_code, learner, status_code, collected - refunded as cash_kept
                            from rpt.v_enrollment_balance where (enrollment_code ilike %(q)s or learner ilike %(q)s) and collected - refunded > 0
                            order by enrolled_on desc limit 20""", {"q": f"%{q}%"})
            if cand.empty:
                ui.empty("No enrolment with cash to refund.")
            else:
                with st.form("refund"):
                    eid = st.selectbox("Enrolment", cand["enrollment_id"], format_func=lambda i: (
                        f"{cand.set_index('enrollment_id').loc[i, 'enrollment_code']} · {cand.set_index('enrollment_id').loc[i, 'learner']} · "
                        f"{cand.set_index('enrollment_id').loc[i, 'status_code'].title()} · kept {ui.vnd(cand.set_index('enrollment_id').loc[i, 'cash_kept'])}"))
                    amt = st.number_input("Amount (VND)", min_value=0.0, step=50000.0, format="%.0f")
                    reason = st.text_input("Reason *")
                    reduce = st.checkbox("The centre did not deliver the service (reduce the contract price by the same amount)",
                                         help="E.g. sessions the centre cancelled. Without it, the refund gives back cash that was not earned.")
                    if st.form_submit_button("Record refund", type="primary"):
                        ui.act(lambda: db.execute("select billing.record_refund(%s, %s, %s, %s, %s, %s)",
                                                  (int(eid), bd, round(amt), reason, me, reduce)),
                               "Refund recorded. Revenue and deferred revenue were recalculated.")
