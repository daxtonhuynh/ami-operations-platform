"""Learning Advisor - daily cash close: count the drawer, the system knows what should be in it."""
import streamlit as st

from ami import auth, db, ui

auth.require("LEARNING_ADVISOR")
me = auth.employee_id()
bd = db.business_date()
ui.header("Daily cash close", "At the end of each day count the cash you collected. Differences go to the Finance Manager for review")

days = db.df("""
    select r.receipt_date, count(*) as receipts,
           coalesce(sum(r.amount) filter (where r.payment_method_code = 'CASH'), 0) as expected_cash,
           coalesce(sum(r.amount) filter (where r.payment_method_code <> 'CASH'), 0) as transfer_card
    from billing.receipt r
    where r.collected_by = %(me)s and r.status = 'ISSUED' and r.receipt_date <= %(d)s and r.receipt_date >= %(d)s - 30
      and not exists (select 1 from app.cash_close k where k.close_date = r.receipt_date and k.collector_id = r.collected_by)
    group by r.receipt_date order by r.receipt_date""", {"me": me, "d": bd})

if days.empty:
    st.success("Nothing to close: every day with receipts is closed.", icon=":material/check_circle:")
else:
    st.subheader("Days to close", anchor=False)
    ui.table(days, money=["expected_cash", "transfer_card"], dates=["receipt_date"], key="days")
    pick = st.selectbox("Close the day", days["receipt_date"], format_func=ui.date)
    row = days.set_index("receipt_date").loc[pick]
    with st.form("close"):
        st.markdown(f"Cash receipts on {ui.date(pick)}: **{ui.vnd(row['expected_cash'])}** "
                    f"({int(row['receipts'])} receipts incl. {ui.vnd(row['transfer_card'])} by transfer or card, not in the drawer).")
        counted = st.number_input("Cash counted in the drawer (VND)", min_value=0.0, value=float(row["expected_cash"]), step=10000.0, format="%.0f")
        note = st.text_input("Explanation (required if the count differs)")
        diff = counted - float(row["expected_cash"])
        if diff:
            st.warning(f"Difference {ui.vnd(diff)} - it stays visible to Finance until reviewed (control BIL-09).")
        if st.form_submit_button("Close the day", type="primary"):
            ui.act(lambda: db.execute("select app.close_cash(%s, %s, %s, %s)", (pick, me, round(counted), note or None)),
                   f"Cash for {ui.date(pick)} closed.")

st.subheader("My recent closes", anchor=False)
hist = db.df("""select k.close_date, k.expected_cash, k.counted_cash, k.difference, k.expected_transfer as transfer_card, k.note,
                       case when k.difference = 0 then 'Balanced' when k.reviewed_at is null then 'Waiting for Finance' else 'Reviewed' end as review
                from app.cash_close k where k.collector_id = %s order by k.close_date desc limit 30""", (me,))
ui.table(hist, money=["expected_cash", "counted_cash", "difference", "transfer_card"], dates=["close_date"], key="hist")
