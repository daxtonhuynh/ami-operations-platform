"""Finance Manager - approvals: the compensating controls behind staff data entry (discounts outside policy, receipt
voids, cash differences, expense claims)."""
import streamlit as st

from ami import auth, db, ui

auth.require("FINANCE_MANAGER")
me = auth.employee_id()
bd = db.business_date()
ui.header("Approvals", "Staff enter sales and receipts; anything that lowers a price or removes cash needs a second person")

disc = db.df("""
    select d.enrollment_id, d.seq, en.enrollment_code, s.full_name as learner, c.course_code as course, p.name as discount,
           d.discount_value as value, pr.list_price, pr.net_payable, e.name_code as requested_by, en.enrolled_on
    from billing.enrollment_discount d join billing.enrollment en using (enrollment_id) join crm.student s using (student_id)
    join ref.course c using (course_id) join ref.discount_programme p using (discount_code)
    join rpt.v_enrollment_pricing pr using (enrollment_id) left join hr.employee e on e.employee_id = d.requested_by
    where d.approval_status = 'PENDING' order by en.enrolled_on""")
voids = db.df("""
    select r.receipt_id, r.receipt_no, r.receipt_date, s.full_name as learner, r.amount, r.payment_method_code as method,
           r.void_reason, e.name_code as requested_by, r.void_requested_at,
           (select status from finance.fiscal_period where period_id = finance.period_of(r.receipt_date)) as period_status
    from billing.receipt r join crm.student s using (student_id) left join hr.employee e on e.employee_id = r.void_requested_by
    where r.void_requested_at is not null and r.status = 'ISSUED' order by r.void_requested_at""")
cash = db.df("""
    select k.cash_close_id, k.close_date, e.full_name as collector, k.expected_cash, k.counted_cash, k.difference, k.note
    from app.cash_close k join hr.employee e on e.employee_id = k.collector_id
    where k.difference <> 0 and k.reviewed_at is null order by k.close_date""")
claims = db.df("""
    select c.claim_id, c.claim_no, e.full_name as employee, c.submitted_on, sum(l.amount_excl_vat) as amount,
           string_agg(l.description, '; ') as items
    from finance.expense_claim c join hr.employee e using (employee_id) join finance.expense_claim_line l using (claim_id)
    where c.status in ('SUBMITTED','APPROVED') group by c.claim_id, e.full_name order by c.submitted_on""")

t1, t2, t3, t4 = st.tabs([f"Discounts ({len(disc)})", f"Receipt voids ({len(voids)})", f"Cash differences ({len(cash)})",
                          f"Expense claims ({len(claims)})"])
with t1:
    if disc.empty:
        ui.empty("No discount is waiting.")
    else:
        st.caption("The enrolment is priced with the discount until you decide. Refusing removes it and re-prices the enrolment; "
                   "if instalments were already paid, the difference becomes a new instalment due in 7 days.")
        sel = ui.table(disc, money=["list_price", "net_payable"], pcts=["value"], dates=["enrolled_on"], hide=["enrollment_id", "seq"],
                       key="disc", select=True)
        if sel:
            with st.form("disc_f"):
                note = st.text_input("Note", placeholder="e.g. partner-school letter checked")
                a, b = st.columns(2)
                if a.form_submit_button("Approve", type="primary", width="stretch"):
                    ui.act(lambda: db.execute("select billing.decide_discount(%s, %s::smallint, true, %s, %s)",
                                              (int(sel["enrollment_id"]), int(sel["seq"]), me, note or None), fetch=False), "Discount approved.")
                if b.form_submit_button("Refuse", width="stretch"):
                    ui.act(lambda: db.execute("select billing.decide_discount(%s, %s::smallint, false, %s, %s)",
                                              (int(sel["enrollment_id"]), int(sel["seq"]), me, note or None), fetch=False),
                           "Discount refused - enrolment re-priced. The advisor should call the family.")
with t2:
    if voids.empty:
        ui.empty("No void request.")
    else:
        voids["void_requested_at"] = voids["void_requested_at"].dt.tz_convert("Asia/Ho_Chi_Minh").dt.strftime("%d %b %H:%M")
        sel = ui.table(voids, money=["amount"], dates=["receipt_date"], hide=["receipt_id"], key="voids", select=True)
        if sel:
            if sel["period_status"] == "CLOSED":
                st.warning("This receipt is in a closed month: it cannot be voided. Record a refund instead.")
            a, b = st.columns(2)
            if a.button("Approve void", type="primary", width="stretch"):
                ui.act(lambda: db.execute("select billing.decide_receipt_void(%s, true, %s)", (int(sel["receipt_id"]), me), fetch=False),
                       "Receipt voided; its amount is back on the instalments. The advisor issues the correct receipt.")
            if b.button("Reject request", width="stretch"):
                ui.act(lambda: db.execute("select billing.decide_receipt_void(%s, false, %s)", (int(sel["receipt_id"]), me), fetch=False),
                       "Void request rejected.")
with t3:
    if cash.empty:
        ui.empty("Every cash difference has been reviewed.")
    else:
        sel = ui.table(cash, money=["expected_cash", "counted_cash", "difference"], dates=["close_date"], hide=["cash_close_id"],
                       key="cash", select=True)
        if sel and st.button("Mark as reviewed", type="primary"):
            ui.act(lambda: db.execute("select app.review_cash_close(%s, %s)", (int(sel["cash_close_id"]), me), fetch=False),
                   "Reviewed. Control BIL-09 clears at the next run.")
with t4:
    if claims.empty:
        ui.empty("No expense claim waiting.")
    else:
        sel = ui.table(claims, money=["amount"], dates=["submitted_on"], hide=["claim_id"], key="claims", select=True)
        if sel and st.button("Approve and reimburse from petty cash", type="primary"):
            def _pay():
                with db.write() as c:
                    cid = int(sel["claim_id"])
                    head = c.execute("select employee_id, cost_center_code from finance.expense_claim where claim_id = %s", (cid,)).fetchone()
                    no = c.execute("""select 'PC' || lpad((coalesce(max(substring(voucher_no from 3)::int), 0) + 1)::text, 4, '0') as no
                                      from finance.payment_voucher""").fetchone()["no"]
                    vid = c.execute("""insert into finance.payment_voucher (voucher_no, voucher_date, requested_by, approved_by, payee_employee_id,
                                         funding_source, payment_method_code, has_invoice, claim_id, notes)
                                       values (%s, %s, %s, %s, %s, 'PETTY_CASH', 'CASH', false, %s, 'Expense claim reimbursement')
                                       returning voucher_id""", (no, bd, head["employee_id"], me, head["employee_id"], cid)).fetchone()["voucher_id"]
                    c.execute("""insert into finance.payment_voucher_line (voucher_id, line_no, description, business_purpose, amount_excl_vat, vat_code,
                                     recognition_period_id, cost_center_code, account_code)
                                 select %s, row_number() over (order by line_no), description, business_purpose, amount_excl_vat, vat_code,
                                        finance.period_of(%s), %s, 'E8.016'
                                 from finance.expense_claim_line where claim_id = %s""", (vid, bd, head["cost_center_code"], cid))
                    c.execute("update finance.expense_claim set status = 'PAID', approved_by = %s, approved_on = %s where claim_id = %s", (me, bd, cid))
                    return no
            ui.act(_pay, lambda no: f"Claim reimbursed with voucher {no}.")
