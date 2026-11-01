"""Finance dashboard (Finance Manager) / business dashboard (Director): revenue earned vs cash collected, profit,
receivables, deferred revenue and what needs a decision."""
import pandas as pd
import streamlit as st

from ami import auth, charts, db, ui

auth.require("FINANCE_MANAGER", "DIRECTOR")
bd = db.business_date()
cur = bd.year * 100 + bd.month
ui.header("Business dashboard" if auth.read_only() else "Finance dashboard",
          f"{ui.date(bd)} · accrual figures show what was earned (taught); cash figures show what was collected")
ui.read_only_note()

summ = db.df("""select s.period_id, s.basis, s.revenue, s.net_revenue, s.gross_margin, s.ebit, s.ebit_pct, p.status
                from rpt.v_pnl_summary s join finance.fiscal_period p using (period_id)
                where s.period_id <= %s order by s.period_id""", (cur,))
acc = summ[summ["basis"] == "ACCRUAL"].set_index("period_id")
cash = summ[summ["basis"] == "CASH"].set_index("period_id")
last_closed = db.val("select max(period_id) from finance.fiscal_period where status = 'CLOSED' and period_id <= %s", (cur,))
cov = db.df("select * from rpt.v_deferred_revenue_coverage where period_id <= %s order by period_id", (cur,))
bal = db.one("""select sum(outstanding_receivable) as outstanding, sum(overdue_amount) as overdue, sum(deferred_revenue) as deferred,
                       count(*) filter (where status_code = 'ACTIVE') as active
                from rpt.v_enrollment_balance""")
prev = (pd.Timestamp(year=cur // 100, month=cur % 100, day=1) - pd.offsets.MonthBegin(1))
prev_pid = prev.year * 100 + prev.month


def g(frame, pid, col):
    return float(frame.loc[pid, col]) if pid in frame.index and pd.notna(frame.loc[pid, col]) else None


rev_now, rev_prev = g(acc, cur, "net_revenue"), g(acc, prev_pid, "net_revenue")
ebit_lc, pct_lc = g(acc, last_closed, "ebit"), g(acc, last_closed, "ebit_pct")
ui.kpis([
    (f"Revenue earned · {ui.period_label(cur)}", ui.vnd_short(rev_now), "Accrual: tuition recognised for teaching delivered this month",
     ui.vnd_short(rev_now - rev_prev) + " vs last month" if rev_now is not None and rev_prev is not None else None),
    (f"Cash collected · {ui.period_label(cur)}", ui.vnd_short(g(cash, cur, "revenue")), "Receipts applied to tuition this month"),
    (f"EBIT · {ui.period_label(last_closed)} (closed)" if last_closed else "EBIT", ui.vnd_short(ebit_lc),
     f"Accrual basis, margin {ui.pct(pct_lc, 1)}"),
    ("Receivables", ui.vnd_short(bal["outstanding"]), f"Of which overdue {ui.vnd(bal['overdue'])}"),
    ("Deferred revenue", ui.vnd_short(bal["deferred"]), "Cash received for lessons not taught yet - a liability, not profit"),
    ("Active learners", bal["active"]),
])

months = [p for p in acc.index if p >= cur - 100][-13:]
trend = pd.DataFrame({"month": [ui.period_label(p) for p in months],
                      "accrual": [g(acc, p, "net_revenue") or 0 for p in months],
                      "cash": [g(cash, p, "net_revenue") or 0 for p in months],
                      "ebit": [g(acc, p, "ebit") or 0 for p in months]})
c1, c2 = st.columns(2, gap="large")
with c1:
    charts.lines(trend, ["accrual", "cash"], ["Revenue earned (accrual)", "Cash collected (cash basis)"], "Revenue: earned vs collected",
                 note="Cash runs ahead of revenue before each intake (pre-sales); revenue catches up while classes are taught.")
with c2:
    closed = [p for p in months if p in acc.index and acc.loc[p, "status"] == "CLOSED"]
    charts.bars(trend[[p in closed for p in months]], "ebit", "EBIT by closed month (accrual)", signed=True,
                note="Open months are left out: their payroll and accruals are not complete yet.")

c3, c4 = st.columns(2, gap="large")
with c3:
    byp = db.df("""select r.period_id, p.name as programme, sum(r.amount) as revenue
                   from billing.revenue_schedule r join billing.enrollment e using (enrollment_id) join ref.course c using (course_id)
                   join ref.programme p using (programme_code)
                   where r.period_id between %s and %s group by 1, 2 order by 1""", (months[0], cur))
    byp["month"] = byp["period_id"].map(ui.period_label)
    progs = list(byp.groupby("programme")["revenue"].sum().sort_values(ascending=False).index)
    charts.grouped(byp, "programme", "revenue", "Revenue earned by programme", progs)
with c4:
    cv = cov[cov["period_id"].isin(months)].copy()
    cv["month"] = cv["period_id"].map(ui.period_label)
    charts.bars(cv.rename(columns={"deferred_balance": "deferred"}), "deferred", "Deferred revenue at month end",
                note="Tuition paid in advance. It funds operations but is owed back as teaching (or refunds) - see Revenue & deferred.")

st.subheader("Needs attention", anchor=False)
att = db.one("""
    select (select count(*) from billing.enrollment_discount where approval_status = 'PENDING') as discounts,
           (select count(*) from billing.receipt where void_requested_at is not null and status = 'ISSUED') as voids,
           (select count(*) from app.cash_close where difference <> 0 and reviewed_at is null) as cash,
           (select count(*) from finance.expense_claim where status = 'SUBMITTED') as claims,
           (select count(*) from ctl.control_exception where status in ('OPEN','IN_PROGRESS') and severity = 'HIGH') as high,
           (select min(period_id) from finance.fiscal_period where status = 'OPEN') as open_period""")
a = st.columns(5)
a[0].metric("Discounts to approve", att["discounts"], border=True)
a[1].metric("Receipt voids to decide", att["voids"], border=True)
a[2].metric("Cash differences to review", att["cash"], border=True)
a[3].metric("High-severity exceptions", att["high"], border=True)
a[4].metric("Oldest open month", ui.period_label(att["open_period"]) if att["open_period"] else "-", border=True)
if not auth.read_only():
    st.page_link("ami/pages/finance/approvals.py", label="Go to approvals", icon=":material/arrow_forward:")
