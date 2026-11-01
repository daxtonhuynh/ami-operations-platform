"""Revenue & deferred revenue: tuition is earned month by month while the class runs, whatever the payment plan.
The gap between cash kept and revenue earned is deferred revenue (or earned-not-collected)."""
import pandas as pd
import streamlit as st

from ami import auth, charts, db, ui

auth.require("FINANCE_MANAGER", "DIRECTOR")
bd = db.business_date()
cur = bd.year * 100 + bd.month
ui.header("Revenue & deferred", "Contract-based recognition: net tuition spread evenly from the class start month to its end month")
ui.read_only_note()

cov = db.df("""select period_id, cash_received, revenue_recognised, deferred_movement, deferred_balance, earned_not_collected,
                      total_expenses, months_of_costs_prefunded
               from rpt.v_deferred_revenue_coverage where period_id <= %s order by period_id""", (cur,))
cov["month"] = cov["period_id"].map(ui.period_label)
last = cov.iloc[-1]
ui.kpis([("Deferred revenue", ui.vnd_short(last["deferred_balance"]), "Cash kept for lessons not yet taught"),
         ("Earned, not collected", ui.vnd_short(last["earned_not_collected"]), "Taught but not yet paid (instalment plans)"),
         ("Months of costs pre-funded", f"{float(last['months_of_costs_prefunded'] or 0):.1f}",
          "Deferred revenue / this month's total costs"),
         ("Still to recognise", ui.vnd_short(db.val("select sum(still_to_recognise) from rpt.v_enrollment_revenue_position")),
          "Contract value of current enrolments not yet earned")])
charts.lines(cov, ["cash_received", "revenue_recognised"], ["Cash received", "Revenue recognised"], "Cash received vs revenue recognised",
             note="The legacy workbook treated 'cash minus revenue' as money available; here it is shown as what it is - "
                  "an obligation to teach.", table=False)
ui.table(cov[["month", "cash_received", "revenue_recognised", "deferred_movement", "deferred_balance", "earned_not_collected",
              "months_of_costs_prefunded"]],
         money=["cash_received", "revenue_recognised", "deferred_movement", "deferred_balance", "earned_not_collected"], key="cov", height=300)

st.subheader("By enrolment", anchor=False)
q = st.text_input("Search", placeholder="ENR code, learner or class")
pos = db.df("""select enrollment_id, enrollment_code, learner, course_name, class_code, status_code as status, net_payable, cash_kept,
                      recognised_to_date, still_to_recognise, deferred_revenue, earned_not_collected
               from rpt.v_enrollment_revenue_position
               where %(q)s = '' or enrollment_code ilike %(p)s or learner ilike %(p)s or class_code ilike %(p)s
               order by deferred_revenue desc limit 300""", {"q": q, "p": f"%{q}%"})
sel = ui.table(pos, money=["net_payable", "cash_kept", "recognised_to_date", "still_to_recognise", "deferred_revenue", "earned_not_collected"],
               hide=["enrollment_id"], key="pos", select=True, height=320)
if sel:
    rs = db.df("""select r.period_id, r.line_type, r.amount, p.status as period from billing.revenue_schedule r
                  join finance.fiscal_period p using (period_id) where r.enrollment_id = %s order by r.period_id, r.line_type""",
               (int(sel["enrollment_id"]),))
    rs["month"] = rs["period_id"].map(ui.period_label)
    st.markdown(f"**Revenue schedule of {sel['enrollment_code']}** · closed months are final; a change (drop-out, transfer, refund) "
                "re-spreads only what is left over the open months")
    ui.table(rs[["month", "line_type", "amount", "period"]], money=["amount"], key="rs")
