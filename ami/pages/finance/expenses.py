"""Finance Manager - expenses: payment vouchers (company account or petty cash) with VAT, account, cost centre and the
month the cost belongs to."""
import datetime as dt

import pandas as pd
import streamlit as st

from ami import auth, db, ui

auth.require("FINANCE_MANAGER")
me = auth.employee_id()
bd = db.business_date()
ui.header("Expenses & vouchers", "Every payment out has a voucher; capital purchases go to the asset register, not the P&L")

t_list, t_new = st.tabs(["Vouchers", "New voucher"])
with t_list:
    c1, c2 = st.columns([1.3, 2])
    rng = c1.date_input("Voucher dates", value=(bd.replace(day=1) - dt.timedelta(days=31), bd))
    d0, d1 = (rng if isinstance(rng, tuple) and len(rng) == 2 else (rng, rng)) if rng else (bd, bd)
    src = c2.pills("Funding", ["COMPANY_ACCOUNT", "PETTY_CASH"], selection_mode="multi", format_func=lambda s: s.replace("_", " ").title())
    v = db.df("""
        select v.voucher_id, v.voucher_no, v.voucher_date, coalesce(vd.vendor_name, e.full_name) as payee, v.funding_source as funding,
               v.has_invoice as invoice, sum(l.amount_incl_vat) as amount, string_agg(l.description, '; ') as description,
               string_agg(distinct l.account_code, ', ') as accounts, v.notes
        from finance.payment_voucher v left join finance.payment_voucher_line l using (voucher_id)
        left join finance.vendor vd on vd.vendor_id = v.payee_vendor_id left join hr.employee e on e.employee_id = v.payee_employee_id
        where v.voucher_date between %(d0)s and %(d1)s and (%(src)s::text[] is null or v.funding_source = any(%(src)s))
        group by v.voucher_id, vd.vendor_name, e.full_name order by v.voucher_date desc, v.voucher_no desc""",
              {"d0": d0, "d1": d1, "src": src or None})
    v["funding"] = v["funding"].str.replace("_", " ").str.title()
    ui.kpis([("Vouchers", len(v)), ("Total paid", ui.vnd(v["amount"].sum())),
             ("Without VAT invoice", ui.vnd(v.loc[~v["invoice"], "amount"].sum()), "Payments at or above the threshold raise EXP-01")])
    sel = ui.table(v, money=["amount"], dates=["voucher_date"], hide=["voucher_id"], key="v", select=True, height=400)
    if sel:
        ln = db.df("""select l.line_no, l.description, l.amount_excl_vat, l.vat_code, l.vat_amount, l.amount_incl_vat, l.account_code,
                             g.name as account, l.cost_center_code, l.recognition_period_id as cost_month, c.class_code
                      from finance.payment_voucher_line l join finance.gl_account g using (account_code)
                      left join academic.class c using (class_id) where l.voucher_id = %s order by l.line_no""", (int(sel["voucher_id"]),))
        if not ln.empty:
            ln["cost_month"] = ln["cost_month"].map(ui.period_label)
        ui.table(ln, money=["amount_excl_vat", "vat_amount", "amount_incl_vat"], key="ln")

with t_new:
    vendors = db.df("select vendor_id, vendor_name, default_account_code from finance.vendor order by vendor_name")
    accts = db.df("""select account_code, name, is_capex from finance.gl_account
                     where account_class = 'EXPENSE' and is_postable order by account_code""")
    ccs = db.df("select cost_center_code, name from finance.cost_center where is_active order by 1")
    periods = db.df("select period_id from finance.fiscal_period where status = 'OPEN' and period_id <= %s order by 1", (bd.year * 100 + bd.month + 1,))
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    vendor = c1.selectbox("Payee (vendor)", vendors["vendor_id"], format_func=lambda i: vendors.set_index("vendor_id").loc[i, "vendor_name"])
    funding = c2.selectbox("Paid from", ["COMPANY_ACCOUNT", "PETTY_CASH"], format_func=lambda s: s.replace("_", " ").title())
    method = c3.selectbox("Method", ["BANK_TRANSFER", "CASH", "CARD"], format_func=lambda s: s.replace("_", " ").title())
    inv = c4.text_input("VAT invoice no.", placeholder="blank = no invoice")
    default_acc = vendors.set_index("vendor_id").loc[vendor, "default_account_code"]
    acc_list = accts["account_code"].tolist()
    lines = st.data_editor(
        pd.DataFrame([{"description": "", "amount_excl_vat": 0.0, "vat_code": "i10", "account_code": default_acc if default_acc in acc_list else acc_list[0],
                       "cost_center_code": "921011", "cost_month": bd.year * 100 + bd.month}]),
        num_rows="dynamic", hide_index=True, key="new_lines",
        column_config={"description": st.column_config.TextColumn("Description", required=True, width="large"),
                       "amount_excl_vat": st.column_config.NumberColumn("Amount excl. VAT", min_value=0, step=1000, format="localized"),
                       "vat_code": st.column_config.SelectboxColumn("VAT", options=["i0", "i8", "i10"], required=True),
                       "account_code": st.column_config.SelectboxColumn("Account", options=acc_list, required=True),
                       "cost_center_code": st.column_config.SelectboxColumn("Cost centre", options=ccs["cost_center_code"].tolist(), required=True),
                       "cost_month": st.column_config.SelectboxColumn("Cost month", options=periods["period_id"].tolist(), required=True)})
    capex = set(accts[accts["is_capex"]]["account_code"])
    if lines["account_code"].isin(capex).any():
        st.info("A capital account is used: after saving, capitalise the line in Fixed assets so it is depreciated (control EXP-02).")
    note = st.text_input("Notes")
    if st.button("Save voucher", type="primary"):
        good = lines[(lines["description"].str.strip() != "") & (lines["amount_excl_vat"] > 0)]
        if good.empty:
            st.error("Add at least one line with a description and an amount.")
        else:
            def _save():
                with db.write() as c:
                    no = c.execute("""select 'PC' || lpad((coalesce(max(substring(voucher_no from 3)::int), 0) + 1)::text, 4, '0') as no
                                      from finance.payment_voucher""").fetchone()["no"]
                    vid = c.execute("""insert into finance.payment_voucher (voucher_no, voucher_date, requested_by, approved_by, payee_vendor_id,
                                         funding_source, payment_method_code, has_invoice, invoice_no, notes)
                                       values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning voucher_id""",
                                    (no, bd, me, me, int(vendor), funding, method, bool(inv.strip()), inv.strip() or None, note or None)).fetchone()["voucher_id"]
                    for i, r in enumerate(good.itertuples(), 1):
                        c.execute("""insert into finance.payment_voucher_line (voucher_id, line_no, description, amount_excl_vat, vat_code,
                                         recognition_period_id, cost_center_code, account_code) values (%s, %s, %s, %s, %s, %s, %s, %s)""",
                                  (vid, i, r.description.strip(), round(r.amount_excl_vat), r.vat_code, int(r.cost_month), r.cost_center_code, r.account_code))
                    return no
            ui.act(_save, lambda no: f"Voucher {no} saved.")
