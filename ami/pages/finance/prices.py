"""Finance Manager - prices, discounts and business settings. Prices are dated: an enrolment keeps the price valid on
its enrolment date."""
import datetime as dt

import streamlit as st

from ami import auth, db, ui

auth.require("FINANCE_MANAGER")
bd = db.business_date()
ui.header("Prices & settings", "The rules the advisors sell with")

t_price, t_disc, t_set = st.tabs(["Price list", "Discount programmes", "Settings"])
with t_price:
    pl = db.df("""select p.course_price_id, c.course_code, c.name as course, p.delivery_mode_code as mode, p.price_basis as basis, p.amount,
                         p.effective_from, p.effective_to,
                         (%(d)s >= p.effective_from and (p.effective_to is null or %(d)s < p.effective_to)) as current
                  from ref.course_price p join ref.course c using (course_id) order by c.course_id, p.delivery_mode_code, p.effective_from""",
               {"d": bd})
    only = st.toggle("Current prices only", value=True)
    ui.table(pl[pl["current"]] if only else pl, money=["amount"], dates=["effective_from", "effective_to"], hide=["course_price_id", "current"],
             key="pl", height=380)
    cur = pl[pl["current"]]
    with st.form("price"):
        st.markdown("**New price from a date**")
        c1, c2, c3 = st.columns([2.2, 1, 1])
        pid = c1.selectbox("Price line", cur["course_price_id"], format_func=lambda i: (
            f"{cur.set_index('course_price_id').loc[i, 'course_code']} {cur.set_index('course_price_id').loc[i, 'mode'].title()} "
            f"{cur.set_index('course_price_id').loc[i, 'basis'].replace('_', ' ').lower()} · now {ui.vnd(cur.set_index('course_price_id').loc[i, 'amount'])}"))
        amt = c2.number_input("New amount (VND)", min_value=0.0, step=50000.0, format="%.0f")
        frm = c3.date_input("Effective from", value=(bd.replace(day=1) + dt.timedelta(days=32)).replace(day=1), min_value=bd + dt.timedelta(days=1))
        if st.form_submit_button("Save new price", type="primary"):
            def _price():
                with db.write() as c:
                    old = c.execute("select * from ref.course_price where course_price_id = %s", (int(pid),)).fetchone()
                    c.execute("update ref.course_price set effective_to = %s where course_price_id = %s", (frm, int(pid)))
                    c.execute("""insert into ref.course_price (course_id, delivery_mode_code, price_basis, amount, effective_from)
                                 values (%s, %s, %s, %s, %s)""", (old["course_id"], old["delivery_mode_code"], old["price_basis"], round(amt), frm))
            ui.act(_price, f"New price from {ui.date(frm)}. Earlier enrolments keep their price.")
with t_disc:
    dp = db.df("""select discount_code, name, discount_kind as kind, discount_value as value, requires_approval, valid_from, valid_to,
                         (select count(*) from billing.enrollment_discount d where d.discount_code = p.discount_code) as times_used
                  from ref.discount_programme p order by valid_to nulls first, discount_code""")
    thr = db.val("select setting_value from ref.app_setting where setting_key = 'discount_approval_threshold'")
    st.caption(f"Discounts marked 'requires approval', or a total above {float(thr) * 100:.0f}% of list price, wait for the Finance Manager.")
    ui.table(dp, dates=["valid_from", "valid_to"], key="dp")
with t_set:
    s = db.df("select setting_key, setting_value, description from ref.app_setting where setting_key <> 'as_of_date' order by setting_key")
    ed = st.data_editor(s, hide_index=True, disabled=["setting_key", "description"], key="set",
                        column_config={"setting_key": "Setting", "setting_value": "Value", "description": st.column_config.TextColumn("Meaning", width="large")})
    st.caption("dropout_payment_policy: FORFEIT earns kept payments when a learner leaves; REFUND keeps them deferred until Finance refunds.")
    if st.button("Save settings"):
        def _save():
            with db.write() as c:
                for r in ed.itertuples():
                    c.execute("update ref.app_setting set setting_value = %s where setting_key = %s", (r.setting_value, r.setting_key))
        ui.act(_save, "Settings saved.")
