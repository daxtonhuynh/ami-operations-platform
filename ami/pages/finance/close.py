"""Finance Manager - month-end close. Hard gates in the database: months close in order and only after HR approved the
payroll. After the close nothing dated in the month can be posted, changed or deleted."""
import streamlit as st

from ami import auth, db, ui

auth.require("FINANCE_MANAGER")
me = auth.employee_id()
bd = db.business_date()
ui.header("Month-end close", "Checklist, accruals, then lock the month. Corrections after the close are made in an open month")

periods = db.df("""select p.period_id, p.status, p.closed_at, r.status as payroll
                   from finance.fiscal_period p left join payroll.payroll_run r on r.period_id = p.period_id and r.run_type = 'REGULAR'
                   where p.period_id <= %s order by p.period_id desc limit 14""", (bd.year * 100 + bd.month,))
first_open = db.val("select min(period_id) from finance.fiscal_period where status = 'OPEN'")
show = periods.copy()
show["month"] = show["period_id"].map(ui.period_label)
show["closed_at"] = show["closed_at"].dt.tz_convert("Asia/Ho_Chi_Minh").dt.strftime("%d %b %Y").fillna("-")
show["status"] = show["status"].str.title()
show["payroll"] = show["payroll"].fillna("not created").str.title()
c1, c2 = st.columns([1, 1.6], gap="large")
with c1:
    ui.table(show[["month", "status", "payroll", "closed_at"]], key="per", height=420)
with c2:
    st.subheader(f"Close {ui.period_label(first_open)}", anchor=False)
    p = first_open
    chk = db.one("""
        select (select status from payroll.payroll_run where period_id = %(p)s and run_type = 'REGULAR') as payroll,
               (select count(*) from academic.class_session s join academic.class c using (class_id) join finance.fiscal_period fp on fp.period_id = %(p)s
                 where s.session_date between fp.period_start and fp.period_end and c.lifecycle_status <> 'CANCELLED'
                   and (s.status = 'SCHEDULED' or (s.status in ('DELIVERED','MAKE_UP')
                        and not exists (select 1 from academic.session_staff ss where ss.session_id = s.session_id)))) as sessions,
               (select count(*) from app.cash_close where difference <> 0 and reviewed_at is null and finance.period_of(close_date) <= %(p)s) as cash,
               (select count(*) from billing.enrollment_discount d join billing.enrollment e using (enrollment_id)
                 where d.approval_status = 'PENDING') as discounts,
               (select count(*) from billing.receipt where void_requested_at is not null and status = 'ISSUED'
                 and finance.period_of(receipt_date) = %(p)s) as voids,
               (select count(*) from rpt.v_enrollment_balance where uncollectible_not_written_off > 0) as writeoffs,
               (select count(*) from ctl.control_exception where status in ('OPEN','IN_PROGRESS') and severity = 'HIGH') as high,
               (select period_end from finance.fiscal_period where period_id = %(p)s) as period_end
    """, {"p": p})
    items = [
        ("Previous month closed", True, "Months close in order (enforced)."),
        ("Payroll approved by HR", chk["payroll"] in ("APPROVED", "PAID"), f"Payroll is {(chk['payroll'] or 'not created').lower()} (enforced)."),
        ("All sessions of the month confirmed", chk["sessions"] == 0, f"{chk['sessions']} session(s) still unconfirmed."),
        ("Receipt voids of the month decided", chk["voids"] == 0, f"{chk['voids']} void request(s) pending - after the close they can only be refunds."),
        ("Cash differences reviewed", chk["cash"] == 0, f"{chk['cash']} difference(s) not reviewed."),
        ("Discount approvals decided", chk["discounts"] == 0, f"{chk['discounts']} discount(s) waiting."),
        ("Dropped-out balances written off or chased", chk["writeoffs"] == 0, f"{chk['writeoffs']} balance(s) not written off."),
        ("No high-severity exception open", chk["high"] == 0, f"{chk['high']} high-severity exception(s) open."),
    ]
    for label, ok, detail in items:
        st.markdown(f":green[:material/check_circle:] **{label}**" if ok else f":red[:material/cancel:] **{label}** - {detail}")
    if bd <= chk["period_end"]:
        st.info(f"{ui.period_label(p)} is not over yet (business date {ui.date(bd)}). Close it in the first days of next month.")
    with st.expander("Accrual journal for this month (accrual basis only)"):
        with st.form("je"):
            a, b, c = st.columns([2, 1, 1])
            desc = a.text_input("Description", placeholder="e.g. Accrue Q4 audit fee")
            amt = b.number_input("Amount (VND)", min_value=0.0, step=100000.0, format="%.0f")
            acc = c.selectbox("Expense account", ["E7.001", "E7.004", "E7.006", "E8.016"])
            if st.form_submit_button("Post accrual"):
                def _je():
                    with db.write() as conn:
                        no = conn.execute("""select 'JE-' || to_char(%s::date, 'YYYY') || '-' ||
                                                    lpad((count(*) + 1)::text, 4, '0') as no from finance.journal_entry""", (bd,)).fetchone()["no"]
                        je = conn.execute("""insert into finance.journal_entry (entry_no, period_id, entry_date, basis, entry_type, description, posted_by)
                                             values (%s, %s, %s, 'ACCRUAL_ONLY', 'ACCRUAL', %s, %s) returning journal_entry_id""",
                                          (no, p, chk["period_end"], desc, me)).fetchone()["journal_entry_id"]
                        conn.execute("""insert into finance.journal_line (journal_entry_id, line_no, account_code, cost_center_code, debit, credit, memo)
                                        values (%s, 1, %s, '921010', %s, 0, %s), (%s, 2, 'B2.201', null, 0, %s, 'Accrued expenses')""",
                                     (je, acc, round(amt), desc, je, round(amt)))
                ui.act(_je, "Accrual posted (balanced journal, accrual P&L only).")
    if st.button(f"Close {ui.period_label(p)}", type="primary", icon=":material/lock:"):
        ui.act(lambda: db.execute("select finance.close_period(%s, %s)", (p, me), fetch=False),
               f"{ui.period_label(p)} is closed. Its figures are final.")
