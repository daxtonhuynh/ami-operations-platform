"""P&L on two bases: cash (money in and out of the month) and accrual (revenue earned, costs incurred). Same ledger,
two views - no figure is typed twice (BR-08)."""
import pandas as pd
import streamlit as st

from ami import auth, db, ui

auth.require("FINANCE_MANAGER", "DIRECTOR")
bd = db.business_date()
cur = bd.year * 100 + bd.month
ui.header("P&L: cash vs accrual", "Built from receipts, revenue schedule, vouchers, payroll, depreciation and journals")
ui.read_only_note()

periods = db.df("select period_id, status from finance.fiscal_period where period_id <= %s and period_id >= %s - 200 order by period_id",
                (cur, cur))
pids = periods["period_id"].tolist()
t_stmt, t_cmp, t_class = st.tabs(["Statement", "Cash vs accrual for one month", "Class contribution"])
with t_stmt:
    c1, c2 = st.columns([1, 2.5])
    basis = c1.segmented_control("Basis", ["ACCRUAL", "CASH"], default="ACCRUAL", format_func=str.title, key="basis")
    rng = c2.select_slider("Months", options=pids, value=(pids[max(0, len(pids) - 6)], pids[-1]), format_func=ui.period_label)
    data = db.df("""select section, pnl_line, sort_order, period_id, sum(amount) as amount from rpt.v_pnl_by_line
                    where basis = %s and period_id between %s and %s group by 1, 2, 3, 4""", (basis or "ACCRUAL", rng[0], rng[1]))
    if data.empty:
        ui.empty("No figures in this range.")
    else:
        sign = data["section"].map(lambda s: 1 if s == "REVENUE" else -1)
        data["amount"] = data["amount"] * sign
        piv = data.pivot_table(index=["sort_order", "section", "pnl_line"], columns="period_id", values="amount", aggfunc="sum").fillna(0)
        piv = piv.sort_index().reset_index().drop(columns="sort_order")
        cols = [c for c in piv.columns if isinstance(c, (int,)) or str(c).isdigit()]
        piv["Total"] = piv[cols].sum(axis=1)
        tot = piv[cols + ["Total"]].sum()
        piv = pd.concat([piv, pd.DataFrame([{"section": "RESULT", "pnl_line": "EBIT", **tot.to_dict()}])], ignore_index=True)
        piv["section"] = piv["section"].str.replace("_", " ").str.capitalize()
        piv = piv.rename(columns={c: ui.period_label(c) for c in cols})
        money_cols = [ui.period_label(c) for c in cols] + ["Total"]
        st.caption("Revenue positive, costs negative. Open months are provisional (" +
                   ", ".join(ui.period_label(p) for p in periods[periods["status"] == "OPEN"]["period_id"]) + ").")
        ui.table(piv, money=money_cols, key="piv", height=600, labels={"pnl_line": "Line"})

with t_cmp:
    m = st.selectbox("Month", pids[::-1], format_func=lambda p: f"{ui.period_label(p)} ({periods.set_index('period_id').loc[p, 'status'].title()})")
    s = db.df("select * from rpt.v_pnl_summary where period_id = %s", (m,)).set_index("basis")
    rows = ["revenue", "deductions", "net_revenue", "cost_of_sales", "gross_margin", "staff_costs", "marketing_costs", "establishment_costs",
            "administration_costs", "total_indirect_costs", "ebit", "depreciation", "ebitda"]
    comp = pd.DataFrame({"line": [r.replace("_", " ").capitalize() for r in rows],
                         "cash": [float(s.loc["CASH", r]) if "CASH" in s.index else 0 for r in rows],
                         "accrual": [float(s.loc["ACCRUAL", r]) if "ACCRUAL" in s.index else 0 for r in rows]})
    comp["difference"] = comp["accrual"] - comp["cash"]
    ui.table(comp, money=["cash", "accrual", "difference"], key="comp", height=500)
    why = db.df("""select source_type, basis, sum(amount) as amount from rpt.v_pnl_ledger where period_id = %s
                   and source_type in ('RECEIPT_ALLOCATION','REVENUE_SCHEDULE','REFUND','WRITE_OFF','JOURNAL_LINE') group by 1, 2 order by 1, 2""", (m,))
    st.markdown("**Where the two bases differ**")
    st.caption("Cash revenue = receipts applied to tuition in the month, less refunds. Accrual revenue = the month's revenue schedule "
               "(teaching delivered, forfeits). Write-offs and accrual journals exist only in the accrual view.")
    ui.table(why, money=["amount"], key="why")

with t_class:
    cc = db.df("""select class_code, programme_code as programme, course_name, status_label as status, learners, revenue_recognised,
                         teacher_cost, assistant_cost, direct_costs, contribution, contribution_margin_pct, revenue_per_teaching_hour
                  from rpt.v_class_contribution order by contribution desc""")
    st.caption("Revenue earned by each class minus its teacher, assistant and direct costs (books). The basis for deciding which "
               "classes and timetables to repeat.")
    ui.table(cc, money=["revenue_recognised", "teacher_cost", "assistant_cost", "direct_costs", "contribution", "revenue_per_teaching_hour"],
             pcts=["contribution_margin_pct"], key="cc", height=520)
