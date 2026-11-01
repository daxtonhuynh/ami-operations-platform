"""Learning Advisor - students & balances: what each learner owes, record a payment, change an enrolment."""
import datetime as dt

import streamlit as st

from ami import auth, db, pdf, ui

auth.require("LEARNING_ADVISOR")
me = auth.employee_id()
bd = db.business_date()
ui.header("Students & balances", "Find a learner, see the instalments, take a payment - the receipt is applied to the oldest instalment first")

c1, c2, c3 = st.columns([1.6, 2.6, 1], vertical_alignment="bottom")
q = c1.text_input("Search", placeholder="Name, AMI code, phone or ENR code", key="st_q")
status = c2.pills("Payment status", ["Overdue", "Partially paid", "Not paid yet", "Fully paid", "On hold (deferred)",
                                     "Dropped out - balance due"], key="st_status")
mine = c3.toggle("Only my learners", value=False)
focus = st.session_state.pop("students_focus", None)

where, p = ["true"], {"me": me, "q": f"%{q}%", "status": status, "focus": focus}
if focus:
    where.append("b.student_id = %(focus)s")
if q:
    where.append("(b.learner ilike %(q)s or b.student_code ilike %(q)s or b.enrollment_code ilike %(q)s or s.phone ilike %(q)s or g.phone ilike %(q)s)")
if status:
    where.append("b.payment_status = %(status)s")
if mine:
    where.append("b.sales_owner_employee_id = %(me)s")
if not (focus or q or status or mine):
    where.append("b.status_code in ('WAITLISTED','REGISTERED','ACTIVE','DEFERRED') or b.outstanding_receivable > 0")
bal = db.df(f"""
    select b.enrollment_id, b.student_id, b.enrollment_code, b.student_code, b.learner, b.course_name, b.class_code, b.plan_code,
           b.status_code, b.net_payable, b.collected - b.refunded as paid, b.outstanding_receivable as outstanding, b.overdue_amount as overdue,
           b.payment_status, e.name_code as advisor
    from rpt.v_enrollment_balance b
    join crm.student s on s.student_id = b.student_id
    left join crm.student_guardian sg on sg.student_id = s.student_id and sg.is_primary_contact
    left join crm.guardian g on g.guardian_id = sg.guardian_id
    left join hr.employee e on e.employee_id = b.sales_owner_employee_id
    where {' and '.join(f'({w})' for w in where)}
    order by b.overdue_amount desc, b.enrolled_on desc limit 300""", p)
st.caption(f"{len(bal)} enrolment(s). Select one to see its instalments and take a payment.")
sel = ui.table(bal, money=["net_payable", "paid", "outstanding", "overdue"], hide=["enrollment_id", "student_id"], key="bal",
               select=True, height=300)
if focus and len(bal) == 1 and not sel:
    sel = bal.iloc[0].to_dict()
if not sel:
    st.stop()

eid, sid = int(sel["enrollment_id"]), int(sel["student_id"])
e = db.one("""select b.*, s.phone, s.full_name, g.guardian_id, g.full_name as guardian, g.phone as guardian_phone, c.start_date,
                     en.course_id, en.delivery_mode_code, so.full_name as advisor_name
              from rpt.v_enrollment_balance b join crm.student s on s.student_id = b.student_id
              join billing.enrollment en on en.enrollment_id = b.enrollment_id
              left join academic.class c on c.class_id = b.class_id
              left join hr.employee so on so.employee_id = b.sales_owner_employee_id
              left join crm.student_guardian sg on sg.student_id = s.student_id and sg.is_payer
              left join crm.guardian g on g.guardian_id = sg.guardian_id
              where b.enrollment_id = %s""", (eid,))
st.divider()
st.subheader(f"{e['learner']} · {e['enrollment_code']}", anchor=False)
st.caption(" · ".join(x for x in [e["course_name"], e["class_code"] or "waiting list", e["plan_code"].replace("_", " "),
                                  e["status_code"].title(), f"advisor {e['advisor_name'] or '-'}",
                                  f"payer {e['guardian']} {e['guardian_phone'] or ''}" if e["guardian"] else f"phone {e['phone'] or '-'}"] if x))
ui.kpis([("Net payable", ui.vnd(e["net_payable"])), ("Paid", ui.vnd(float(e["collected"]) - float(e["refunded"]))),
         ("Outstanding", ui.vnd(e["outstanding_receivable"])), ("Overdue", ui.vnd(e["overdue_amount"])),
         ("Status", e["payment_status"])])

left, right = st.columns([1.25, 1], gap="large")
with left:
    st.markdown("**Instalments**")
    lines = db.df("""select seq, label, due_date, amount_due, paid, remaining, days_overdue, ageing_bucket
                     from rpt.v_schedule_line_status where enrollment_id = %s order by due_date, seq""", (eid,))
    ui.table(lines, money=["amount_due", "paid", "remaining"], dates=["due_date"], key="lines")
    st.markdown("**Receipts**")
    rec = db.df("""select r.receipt_id, r.receipt_no, r.receipt_date, r.amount, r.payment_method_code as method, r.status,
                          e.name_code as collected_by, r.void_requested_at is not null and r.status = 'ISSUED' as void_pending
                   from billing.receipt r left join hr.employee e on e.employee_id = r.collected_by
                   where r.enrollment_id = %s order by r.receipt_date desc, r.receipt_no desc""", (eid,))
    ui.table(rec, money=["amount"], dates=["receipt_date"], hide=["receipt_id"], key="rec")

with right:
    t_pay, t_status, t_class = st.tabs(["Take a payment", "Drop / defer / cancel", "Class"])
    with t_pay:
        nxt = lines[lines["remaining"] > 0]
        default = float(nxt.iloc[0]["remaining"]) if not nxt.empty else 0.0
        if e["status_code"] in ("DROPPED", "CANCELLED") and float(e["outstanding_receivable"]) <= 0:
            st.info("Nothing is owed on this enrolment.")
        else:
            with st.form("pay"):
                amount = st.number_input("Amount (VND)", min_value=0.0, value=default, step=50000.0, format="%.0f",
                                         help="Defaults to the next open instalment. More than one instalment can be paid at once.")
                method = st.segmented_control("Method", ["CASH", "BANK_TRANSFER", "CARD"], default="CASH",
                                              format_func=lambda m: m.replace("_", " ").title())
                payer = st.text_input("Paid by", value=e["guardian"] or e["learner"])
                note = st.text_input("Note (optional)")
                st.caption(f"Receipt date: {ui.date(bd)} (business date). Receipts cannot be edited afterwards - "
                           "a mistake is corrected by a void approved by Finance.")
                if st.form_submit_button("Issue receipt", type="primary"):
                    if amount <= 0:
                        st.error("Enter an amount.")
                    else:
                        def _pay():
                            rid = db.execute("select billing.record_receipt(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                                             (sid, eid, bd, round(amount), method or "CASH", me, payer or None, e["guardian_id"], note or None))
                            st.session_state["last_receipt"] = rid
                            return db.val("select receipt_no from billing.receipt where receipt_id = %s", (rid,))
                        ui.act(_pay, lambda no: f"Receipt {no} issued for {ui.vnd(amount)}. Print it from the receipt register.")
        last = st.session_state.get("last_receipt")
        if last:
            r = db.one("""select r.receipt_no, r.receipt_date, s.full_name as learner, s.student_code, r.payer_name, r.amount,
                                 r.payment_method_code as method, en.enrollment_code, c.name as course_name, e.full_name as collected_by,
                                 r.status, r.void_reason
                          from billing.receipt r join crm.student s using (student_id)
                          left join billing.enrollment en on en.enrollment_id = r.enrollment_id left join ref.course c on c.course_id = en.course_id
                          left join hr.employee e on e.employee_id = r.collected_by where r.receipt_id = %s""", (last,))
            centre = db.lookup("select setting_key, setting_value from ref.app_setting where setting_key like 'centre_%%'", "LA")
            cfg = dict(zip(centre["setting_key"], centre["setting_value"]))
            st.download_button(f"Download receipt {r['receipt_no']} (PDF)", pdf.receipt_pdf(r, cfg.get("centre_name", ""), cfg.get("centre_address", "")),
                               file_name=f"{r['receipt_no']}.pdf", mime="application/pdf", icon=":material/download:", type="primary")
        adv = db.df("""select r.receipt_id, r.receipt_no, r.receipt_date, r.amount from billing.receipt r
                       where r.student_id = %s and r.status = 'ISSUED'
                         and r.amount > coalesce((select sum(a.amount) from billing.payment_allocation a where a.receipt_id = r.receipt_id), 0)""", (sid,))
        if not adv.empty:
            st.info("This learner has an advance payment that is not applied to any instalment yet (control BIL-04).")
            pick = st.selectbox("Advance receipt", adv["receipt_id"],
                                format_func=lambda i: f"{adv.set_index('receipt_id').loc[i, 'receipt_no']} · {ui.vnd(adv.set_index('receipt_id').loc[i, 'amount'])}")
            if st.button("Apply it to this enrolment"):
                ui.act(lambda: db.execute("select billing.apply_receipt(%s, %s)", (int(pick), eid)), "Advance payment applied.")

    with t_status:
        if e["status_code"] in ("DROPPED", "CANCELLED", "COMPLETED"):
            st.info(f"The enrolment is {e['status_code'].lower()}.")
        else:
            started = e["start_date"] is not None and e["start_date"] <= bd
            options = ["DROPPED", "DEFERRED"] if started else ["CANCELLED", "DEFERRED"]
            with st.form("status"):
                new = st.radio("Change to", options, horizontal=True, format_func=lambda s: {
                    "DROPPED": "Dropped out", "DEFERRED": "Deferred (keeps the contract for a later class)", "CANCELLED": "Cancelled before start"}[s])
                eff = st.date_input("Effective", value=bd, max_value=bd)
                reason = st.text_input("Reason *")
                st.caption("Drop-out: tuition is earned up to this month; payments kept beyond that are earned at once under the "
                           "non-refundable policy. Cancellation: only the deposit is kept. Finance handles refunds and write-offs.")
                if st.form_submit_button("Save status change"):
                    if not reason.strip():
                        st.error("A reason is required.")
                    else:
                        ui.act(lambda: db.execute("select billing.change_enrollment_status(%s, %s, %s, %s)", (eid, new, eff, reason.strip()), fetch=False),
                               f"Enrolment marked {new.lower()}. Revenue and balance were recalculated.")

    with t_class:
        if e["status_code"] in ("DROPPED", "CANCELLED", "COMPLETED"):
            st.info("Only waiting, registered, active or deferred learners can be (re)assigned.")
        else:
            cls = db.df("""select c.class_id, c.class_code, c.start_date,
                                  c.capacity - (select count(*) from billing.enrollment x where x.class_id = c.class_id
                                                 and x.status_code in ('WAITLISTED','REGISTERED','ACTIVE')) as seats_left
                           from academic.class c where c.course_id = %s and c.delivery_mode_code = %s
                             and c.lifecycle_status in ('OPEN','RUNNING') and c.class_id is distinct from %s order by c.start_date""",
                        (e["course_id"], e["delivery_mode_code"], e["class_id"]))
            if cls.empty:
                st.info("No other open class of this course. The Academic Manager sees the waiting list as demand.")
            else:
                target = st.selectbox("Move to class", cls["class_id"],
                                      format_func=lambda i: f"{cls.set_index('class_id').loc[i, 'class_code']} · starts "
                                                            f"{cls.set_index('class_id').loc[i, 'start_date']:%d %b} · "
                                                            f"{cls.set_index('class_id').loc[i, 'seats_left']} seat(s) left")
                if st.button("Assign to this class", type="primary"):
                    ui.act(lambda: db.execute("select billing.assign_class(%s, %s, %s)", (eid, int(target), me), fetch=False),
                           "Class assigned. The learner is on the roster and revenue follows the new class dates.")
