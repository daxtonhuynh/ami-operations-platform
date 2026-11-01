"""Finance Manager - fixed assets: capital purchases are depreciated straight-line, not expensed in one month."""
import streamlit as st

from ami import auth, db, ui

auth.require("FINANCE_MANAGER")
bd = db.business_date()
cur = bd.year * 100 + bd.month
ui.header("Fixed assets", "Projectors, air conditioners, fit-out: cost spread over the useful life (the legacy file expensed them at once)")

reg = db.df("""
    select a.asset_id, a.asset_code, a.asset_name, a.acquisition_date, a.cost, a.useful_life_months as life_months, a.status,
           coalesce(sum(d.amount) filter (where d.period_id <= %(p)s), 0) as depreciated,
           a.cost - coalesce(sum(d.amount) filter (where d.period_id <= %(p)s), 0) as net_book_value,
           max(d.amount) filter (where d.period_id = %(p)s) as this_month
    from finance.fixed_asset a left join finance.depreciation_schedule d using (asset_id)
    group by a.asset_id order by a.acquisition_date""", {"p": cur})
ui.kpis([("Assets", len(reg)), ("Cost", ui.vnd(reg["cost"].sum())), ("Net book value", ui.vnd(reg["net_book_value"].sum())),
         ("Depreciation this month", ui.vnd(reg["this_month"].sum()))])
sel = ui.table(reg, money=["cost", "depreciated", "net_book_value", "this_month"], dates=["acquisition_date"], hide=["asset_id"], key="reg",
               select=True, height=300)
if sel:
    ds = db.df("select period_id, amount from finance.depreciation_schedule where asset_id = %s order by period_id", (int(sel["asset_id"]),))
    ds["month"] = ds["period_id"].map(ui.period_label)
    st.caption(f"Depreciation schedule of {sel['asset_code']}")
    ui.table(ds[["month", "amount"]], money=["amount"], key="ds", height=250)

st.subheader("Capital purchases not yet capitalised", anchor=False)
todo = db.df("""
    select l.voucher_line_id, v.voucher_no, v.voucher_date, l.description, l.amount_incl_vat, l.account_code, g.name as account
    from finance.payment_voucher_line l join finance.payment_voucher v using (voucher_id) join finance.gl_account g using (account_code)
    where g.is_capex and v.status <> 'VOID' and not exists (select 1 from finance.fixed_asset a where a.voucher_line_id = l.voucher_line_id)
    order by v.voucher_date""")
if todo.empty:
    st.success("Every capital purchase is in the register.", icon=":material/check_circle:")
else:
    st.caption("Control EXP-02: these purchases are in no P&L month until they are capitalised.")
    pick = ui.table(todo, money=["amount_incl_vat"], dates=["voucher_date"], hide=["voucher_line_id"], key="todo", select=True)
    if pick:
        charge = {"E3.001": "E3.004", "E3.002": "E3.005", "E3.003": "E3.006"}.get(pick["account_code"], "E4.001")
        with st.form("cap"):
            c1, c2 = st.columns([2, 1])
            name = c1.text_input("Asset name", value=pick["description"])
            life = c2.number_input("Useful life (months)", min_value=1, max_value=120, value=36 if pick["account_code"] == "E3.001" else 60)
            if st.form_submit_button("Capitalise", type="primary"):
                def _cap():
                    with db.write() as c:
                        code = c.execute("""select 'FA-' || lpad((coalesce(max(substring(asset_code from 4)::int), 0) + 1)::text, 4, '0') as c
                                            from finance.fixed_asset""").fetchone()["c"]
                        aid = c.execute("""insert into finance.fixed_asset (asset_code, asset_name, capex_account_code, charge_account_code,
                                              cost_center_code, voucher_line_id, acquisition_date, cost, useful_life_months, first_charge_period_id)
                                           select %s, %s, l.account_code, %s, l.cost_center_code, l.voucher_line_id, v.voucher_date, l.amount_incl_vat, %s,
                                                  greatest(finance.period_of(v.voucher_date),
                                                           (select min(period_id) from finance.fiscal_period where status = 'OPEN'))
                                           from finance.payment_voucher_line l join finance.payment_voucher v using (voucher_id)
                                           where l.voucher_line_id = %s returning asset_id""",
                                        (code, name, charge, int(life), int(pick["voucher_line_id"]))).fetchone()["asset_id"]
                        c.execute("select finance.generate_depreciation(%s)", (aid,))
                        return code
                ui.act(_cap, lambda code: f"Asset {code} registered and depreciation scheduled.")
