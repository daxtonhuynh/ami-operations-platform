"""Learning Advisor - new enrolment: price, instalments and revenue months are computed by the database rules
(billing.enrol) and shown as a preview before anything is saved."""
import datetime as dt

import streamlit as st

from ami import auth, db, ui

auth.require("LEARNING_ADVISOR")
me = auth.employee_id()
bd = db.business_date()
ui.header("New enrolment", "Price list, discounts and payment plan are applied by the same rules for every advisor")

# ------------------------------------------------------------------------------------------------ 1. learner
st.subheader("1 · Learner", anchor=False)
source = st.segmented_control("Who", ["Tested lead", "Returning learner"], default="Tested lead", key="enr_source")
learner = None
lead_id = None
if source == "Tested lead":
    leads = db.df("""
        select l.lead_id, l.student_id, s.full_name, s.student_code, l.programme_code, l.delivery_mode_code, l.recommended_course_id,
               pl.level_code, e.name_code as advisor
        from crm.lead l join crm.student s using (student_id)
        left join lateral (select overall_level_id from crm.placement_test t where t.lead_id = l.lead_id and t.status = 'COMPLETED'
                           order by completed_at desc limit 1) t on true
        left join ref.proficiency_level pl on pl.level_id = t.overall_level_id
        left join hr.employee e on e.employee_id = l.owner_employee_id
        where l.closed_on is null and l.stage_code = 'TESTED' order by l.owner_employee_id = %s desc, s.full_name""", (me,))
    if leads.empty:
        ui.empty("No tested lead is waiting. Record a placement test result first.")
        st.stop()
    pre = st.session_state.pop("enrol_lead_id", None)
    idx = int(leads.index[leads["lead_id"] == pre][0]) if pre in set(leads["lead_id"]) else 0
    row = ui.choose("Lead", leads, "lead_id", lambda r: f"{r['full_name']} ({r['student_code']}) · {r['programme_code']} · "
                                                       f"level {r['level_code'] or '?'} · advisor {r['advisor'] or '-'}", index=idx, key="enr_lead")
    learner, lead_id = row, int(row["lead_id"])
else:
    q = st.text_input("Search learner (name, code or phone)", key="enr_q")
    if q:
        found = db.df("""select s.student_id, s.full_name, s.student_code, null::text as programme_code, null::int as recommended_course_id,
                                (select string_agg(c.course_code || ' ' || e.status_code, ', ' order by e.enrolled_on desc)
                                   from billing.enrollment e join ref.course c using (course_id) where e.student_id = s.student_id) as history
                         from crm.student s where s.full_name ilike %(q)s or s.student_code ilike %(q)s or s.phone ilike %(q)s
                         order by s.full_name limit 30""", {"q": f"%{q}%"})
        if found.empty:
            ui.empty("No learner found.")
            st.stop()
        learner = ui.choose("Learner", found, "student_id", lambda r: f"{r['full_name']} ({r['student_code']}) · {r['history'] or 'no enrolment yet'}",
                            key="enr_student")
    else:
        st.stop()

sid = int(learner["student_id"])

# ------------------------------------------------------------------------------------------------ 2. course and class
st.subheader("2 · Course and class", anchor=False)
courses = db.lookup("select course_id, course_code, name, programme_code from ref.course where is_active order by course_id", "LA")
c1, c2, c3 = st.columns([1.6, 1, 2.4])
rec = learner.get("recommended_course_id")
course_ids = courses["course_id"].tolist()
course = c1.selectbox("Course", course_ids, index=course_ids.index(rec) if rec in course_ids else 0,
                      format_func=lambda i: f"{courses.set_index('course_id').loc[i, 'course_code']} - {courses.set_index('course_id').loc[i, 'name']}")
mode = c2.selectbox("Delivery", ["OFFLINE", "ONLINE"], format_func=str.title,
                    index=1 if learner.get("delivery_mode_code") == "ONLINE" else 0)
classes = db.df("""
    select c.class_id, c.class_code, c.start_date, c.planned_end_date, c.capacity, c.lifecycle_status,
           c.capacity - (select count(*) from billing.enrollment e where e.class_id = c.class_id
                          and e.status_code in ('WAITLISTED','REGISTERED','ACTIVE')) as seats_left,
           (select string_agg(case p.weekday when 1 then 'Mon' when 2 then 'Tue' when 3 then 'Wed' when 4 then 'Thu' when 5 then 'Fri'
                                               when 6 then 'Sat' else 'Sun' end, '/' order by p.weekday) || ' ' || to_char(min(p.start_time), 'HH24:MI')
              from academic.class_meeting_pattern p where p.class_id = c.class_id) as timetable
    from academic.class c
    where c.course_id = %s and c.delivery_mode_code = %s and c.lifecycle_status in ('OPEN','RUNNING','PLANNED')
      and c.planned_end_date >= %s
    order by c.start_date""", (int(course), mode, bd))
opts = [None] + classes["class_id"].tolist()
cinfo = classes.set_index("class_id")


def _cls(i):
    if i is None:
        return "No class yet - put the learner on the waiting list"
    r = cinfo.loc[i]
    started = " (started)" if r["start_date"] <= bd else ""
    return f"{r['class_code']} · starts {r['start_date']:%d %b}{started} · {r['timetable']} · {r['seats_left']} seat(s) left"


with_seats = [i for i, cid in enumerate(opts) if cid is not None and cinfo.loc[cid, "seats_left"] > 0]
class_id = c3.selectbox("Class", opts, index=with_seats[0] if with_seats else 0, format_func=_cls)
if class_id is not None and cinfo.loc[class_id, "seats_left"] <= 0:
    st.warning("This class is full - the database will refuse the enrolment. Choose another class or the waiting list.")

# ------------------------------------------------------------------------------------------------ 3. plan and discounts
st.subheader("3 · Payment plan and discounts", anchor=False)
plans = db.lookup("select plan_code, name from ref.payment_plan order by plan_code", "LA")
discounts = db.df("""select discount_code, name, discount_kind, discount_value, requires_approval from ref.discount_programme
                     where %s >= valid_from and (valid_to is null or %s <= valid_to) order by discount_value""", (bd, bd))
threshold = float(db.val("select setting_value from ref.app_setting where setting_key = 'discount_approval_threshold'") or 0.3)
d1, d2, d3 = st.columns([1.2, 2.2, 1])
plan = d1.selectbox("Payment plan", plans["plan_code"], format_func=lambda p: plans.set_index("plan_code").loc[p, "name"])
dsel = d2.multiselect("Discounts (at most 3)", discounts["discount_code"], max_selections=3,
                      format_func=lambda c: discounts.set_index("discount_code").loc[c, "name"]
                      + (" · needs Finance approval" if discounts.set_index("discount_code").loc[c, "requires_approval"] else ""))
deposit = d3.toggle("Take a deposit now", value=class_id is not None and cinfo.loc[class_id, "start_date"] > bd if class_id else False,
                    help="The non-refundable seat deposit is due today; the rest follows the plan from the class start.")
e1, e2 = st.columns([1, 2])
levels = db.lookup("select level_id, scale_code, level_code from ref.proficiency_level order by scale_code, level_rank", "LA")
prog = courses.set_index("course_id").loc[course, "programme_code"]
scale = "IELTS" if prog == "IELTS" else "CEFR"
lv = levels[levels["scale_code"] == scale]
target = e1.selectbox("Output commitment", [None] + lv["level_id"].tolist(),
                      format_func=lambda i: "None" if i is None else f"{scale} {lv.set_index('level_id').loc[i, 'level_code']}")
notes = e2.text_input("Notes", placeholder="e.g. siblings in the same class, special timetable needs")
doc = st.text_input("Signed enrolment form (link)", placeholder="https://drive.../enrolment-form.pdf")

call = """select billing.enrol(%s, %s::smallint, %s, %s, %s, %s, %s, %s, %s::text[], null, %s, %s::smallint, %s, %s)"""
params = (sid, int(course), mode, int(class_id) if class_id else None, plan, bd, me, lead_id, dsel,
          db.val("select billing.fee_amount('STANDARD_DEPOSIT', %s)", (bd,)) if deposit else None,
          int(target) if target else None, notes or None, doc or None)

b1, b2, _ = st.columns([1, 1, 3])
if b1.button("Preview price and schedule", icon=":material/calculate:", width="stretch"):
    st.session_state["enr_preview"] = params
confirm = b2.button("Confirm enrolment", type="primary", icon=":material/how_to_reg:", width="stretch")

if st.session_state.get("enr_preview") == params or confirm:
    try:
        price, sched, disc, rev = db.preview(
            call, params,
            ("""select list_price, discounts, group_discount, materials_fee, adjustments, net_payable from rpt.v_enrollment_pricing
                where enrollment_id = %s""", lambda k: (k,)),
            ("select seq, label, due_date, amount_due from billing.payment_schedule where enrollment_id = %s order by due_date, seq", lambda k: (k,)),
            ("""select d.discount_code, p.name, d.discount_value, d.approval_status from billing.enrollment_discount d
                join ref.discount_programme p using (discount_code) where d.enrollment_id = %s order by d.seq""", lambda k: (k,)),
            ("""select period_id, line_type, amount from billing.revenue_schedule where enrollment_id = %s order by period_id, line_type""",
             lambda k: (k,)))
    except db.BusinessRuleError as e:
        st.error(str(e), icon=":material/block:")
        st.stop()
    p = price.iloc[0]
    with st.container(border=True):
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("List price", ui.vnd(p["list_price"]))
        k2.metric("Discounts", ui.vnd(float(p["discounts"]) + float(p["group_discount"])))
        k3.metric("Materials fee", ui.vnd(p["materials_fee"]))
        k4.metric("Net payable", ui.vnd(p["net_payable"]))
        if not disc.empty and (disc["approval_status"] == "PENDING").any():
            st.warning("A discount is outside policy: the enrolment is saved at the discounted price but waits for the Finance "
                       "Manager's approval. If refused, the price goes back to list.", icon=":material/hourglass_top:")
        s1, s2 = st.columns([1.2, 1])
        with s1:
            st.markdown("**Instalments**")
            ui.table(sched, money=["amount_due"], dates=["due_date"], key="pv_sched")
        with s2:
            st.markdown("**Revenue earned per month** (contract-based, independent of when cash arrives)")
            if rev.empty:
                st.caption("Nothing is earned until the learner has a class.")
            else:
                rev["month"] = rev["period_id"].map(ui.period_label)
                ui.table(rev[["month", "line_type", "amount"]], money=["amount"], key="pv_rev")

if confirm:
    def _do():
        eid = db.execute(call, params)
        return db.val("select enrollment_code from billing.enrollment where enrollment_id = %s", (eid,))
    code = ui.act(_do, rerun=False)
    if code:
        st.session_state.pop("enr_preview", None)
        st.session_state["students_focus"] = sid
        ui.flash(f"Enrolment {code} saved. Record the first payment now.")
        st.switch_page("ami/pages/sales/students.py")
