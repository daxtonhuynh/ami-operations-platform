"""Learning Advisor - receipt register: reprint a receipt or ask Finance to void one (receipts are never edited)."""
import datetime as dt

import streamlit as st

from ami import auth, db, pdf, ui

auth.require("LEARNING_ADVISOR")
me = auth.employee_id()
bd = db.business_date()
ui.header("Receipt register", "Numbered receipts in date order. A wrong receipt is voided by Finance, never changed")

c1, c2, c3 = st.columns([1.4, 1, 1.4], vertical_alignment="bottom")
rng = c1.date_input("Receipt dates", value=(bd - dt.timedelta(days=6), bd), max_value=bd)
who = c2.segmented_control("Collected by", ["Me", "Everyone"], default="Me")
stat = c3.segmented_control("Status", ["Issued", "Void request pending", "Void"], key="rc_stat")
d0, d1 = (rng if isinstance(rng, tuple) and len(rng) == 2 else (rng, rng)) if rng else (bd, bd)
where = ["r.receipt_date between %(d0)s and %(d1)s"]
if who == "Me":
    where.append("r.collected_by = %(me)s")
if stat == "Issued":
    where.append("r.status = 'ISSUED'")
elif stat == "Void":
    where.append("r.status = 'VOID'")
elif stat == "Void request pending":
    where.append("r.status = 'ISSUED' and r.void_requested_at is not null")
recs = db.df(f"""
    select r.receipt_id, r.receipt_no, r.receipt_date, s.full_name as learner, coalesce(en.enrollment_code, 'advance') as enrolment,
           r.amount, r.payment_method_code as method, e.name_code as collected_by,
           case when r.status = 'VOID' then 'Void' when r.void_requested_at is not null then 'Void requested' else 'Issued' end as status
    from billing.receipt r join crm.student s using (student_id)
    left join billing.enrollment en on en.enrollment_id = r.enrollment_id
    left join hr.employee e on e.employee_id = r.collected_by
    where {' and '.join(where)} order by r.receipt_date desc, r.receipt_no desc""", {"d0": d0, "d1": d1, "me": me})
tot = recs[recs["status"] != "Void"]
ui.kpis([("Receipts", len(tot)), ("Total", ui.vnd(tot["amount"].sum())),
         ("Cash", ui.vnd(tot.loc[tot["method"] == "CASH", "amount"].sum())),
         ("Transfer / card", ui.vnd(tot.loc[tot["method"] != "CASH", "amount"].sum()))])
sel = ui.table(recs, money=["amount"], dates=["receipt_date"], hide=["receipt_id"], key="recs", select=True, height=380)

if sel:
    rid = int(sel["receipt_id"])
    r = db.one("""select r.receipt_no, r.receipt_date, s.full_name as learner, s.student_code, r.payer_name, r.amount,
                         r.payment_method_code as method, en.enrollment_code, c.name as course_name, e.full_name as collected_by,
                         r.status, r.void_reason, r.void_requested_at, r.collected_by as collector_id
                  from billing.receipt r join crm.student s using (student_id)
                  left join billing.enrollment en on en.enrollment_id = r.enrollment_id left join ref.course c on c.course_id = en.course_id
                  left join hr.employee e on e.employee_id = r.collected_by where r.receipt_id = %s""", (rid,))
    centre = db.lookup("select setting_key, setting_value from ref.app_setting where setting_key like 'centre_%%'", "LA")
    cfg = dict(zip(centre["setting_key"], centre["setting_value"]))
    st.divider()
    a, b = st.columns([1, 1.2], gap="large")
    with a:
        st.subheader(f"Receipt {r['receipt_no']}", anchor=False)
        st.write(f"{ui.vnd(r['amount'])} · {r['method'].replace('_', ' ').title()} · {ui.date(r['receipt_date'])}")
        st.write(f"From {r['payer_name'] or r['learner']} for {r['learner']} ({r['student_code']}) · {r['enrollment_code'] or 'advance payment'}")
        st.download_button("Download PDF", pdf.receipt_pdf(r, cfg.get("centre_name", ""), cfg.get("centre_address", "")),
                           file_name=f"{r['receipt_no']}.pdf", mime="application/pdf", icon=":material/download:")
    with b:
        if r["status"] == "VOID":
            st.error(f"Void: {r['void_reason']}")
        elif r["void_requested_at"]:
            st.warning(f"Void requested: {r['void_reason']}. Waiting for the Finance Manager.")
        else:
            with st.form("void"):
                st.markdown("**Ask Finance to void this receipt**")
                reason = st.text_area("Reason *", placeholder="e.g. keyed as cash, parent paid by bank transfer")
                st.caption("After approval the receipt stays in the register marked VOID and its amount goes back to the instalments. "
                           "Issue the correct receipt afterwards.")
                if st.form_submit_button("Request void"):
                    ui.act(lambda: db.execute("select billing.request_receipt_void(%s, %s, %s)", (rid, me, reason), fetch=False),
                           "Void requested - Finance has it in their approvals.")
