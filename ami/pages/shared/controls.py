"""Control centre / my exceptions: the rules the business checks every night and the queue of records that fail them.
Each role sees the controls it owns (row-level security in the database); Finance and the Director see all of them."""
import streamlit as st

from ami import auth, db, ui

user = auth.current_user()
if not user:
    st.stop()
me = auth.employee_id()
role = user["role_code"]
everything = role in ("FINANCE_MANAGER", "DIRECTOR")
ui.header("Control centre" if everything else "My exceptions",
          "Each control is a business rule checked automatically. A failing record stays here until it is fixed, "
          "resolved with a note, or the risk is accepted")
ui.read_only_note()

ctl = db.df("""
    select c.control_code, c.name, c.domain, c.severity, c.business_rule, c.app_role_code as owner, c.rule, c.frequency,
           count(x.*) filter (where x.status = 'OPEN') as open, count(x.*) filter (where x.status = 'IN_PROGRESS') as in_progress,
           count(x.*) filter (where x.status = 'RISK_ACCEPTED') as accepted,
           (select max(r.executed_at) from ctl.control_run r where r.control_code = c.control_code) as last_run
    from ctl.control c left join ctl.control_exception x on x.control_code = c.control_code
    where c.is_active and (%(all)s or c.app_role_code = %(role)s)
    group by c.control_code order by c.control_code""", {"all": everything, "role": role})

top = st.columns([3, 1])
top[0].caption(f"{len(ctl)} control(s) · {int(ctl['open'].sum() + ctl['in_progress'].sum())} open exception(s)")
if top[1].button("Run controls now", icon=":material/refresh:", width="stretch"):
    ui.act(lambda: db.execute("select sum(exceptions) from ctl.run_all_controls()"), "Controls re-run on the current data.")

show = ctl.copy()
show["owner"] = show["owner"].str.replace("_", " ").str.title()
show["last_run"] = show["last_run"].dt.tz_convert("Asia/Ho_Chi_Minh").dt.strftime("%d %b %H:%M")
ui.table(show[["control_code", "name", "severity", "business_rule", "owner", "open", "in_progress", "accepted", "last_run", "rule"]],
         key="ctl", height=min(36 * (len(show) + 1) + 4, 420),
         labels={"business_rule": "BR", "in_progress": "In progress", "accepted": "Risk accepted"})

st.subheader("Exception queue", anchor=False)
f1, f2, f3 = st.columns([2, 2.4, 1.2])
codes = f1.multiselect("Controls", ctl["control_code"], format_func=lambda c: f"{c} {ctl.set_index('control_code').loc[c, 'name']}")
statuses = f2.pills("Status", ["OPEN", "IN_PROGRESS", "RESOLVED", "RISK_ACCEPTED", "CLEARED"], selection_mode="multi",
                    default=["OPEN", "IN_PROGRESS"], format_func=lambda s: s.replace("_", " ").title())
sev = f3.pills("Severity", ["HIGH", "MEDIUM", "LOW"], selection_mode="multi", format_func=str.title)
exc = db.df("""
    select x.exception_id, x.control_code, c.name as control, x.severity, x.entity_ref as record, x.status,
           x.opened_at::date as opened, e.name_code as assigned_to, x.resolution_note as note, x.detail::text as detail
    from ctl.control_exception x join ctl.control c using (control_code)
    left join hr.employee e on e.employee_id = x.assigned_to
    where (%(codes)s::text[] is null or x.control_code = any(%(codes)s)) and (%(st)s::text[] is null or x.status = any(%(st)s))
      and (%(sev)s::text[] is null or x.severity = any(%(sev)s))
    order by case x.severity when 'HIGH' then 1 when 'MEDIUM' then 2 else 3 end, x.opened_at limit 500""",
              {"codes": codes or None, "st": statuses or None, "sev": sev or None})
if exc.empty:
    ui.empty("No exception matches. Every record passes these rules.")
    st.stop()
sel = ui.table(exc, dates=["opened"], hide=["exception_id"], key="exc", select=True, height=360)
if sel and not auth.read_only():
    xid = int(sel["exception_id"])
    st.markdown(f"**{sel['control_code']} · {sel['record']}** - {sel['control']}")
    st.json(sel["detail"], expanded=False)
    with st.form("work"):
        c1, c2 = st.columns([1, 2])
        new = c1.radio("Set status", ["IN_PROGRESS", "RESOLVED", "RISK_ACCEPTED"],
                       format_func=lambda s: {"IN_PROGRESS": "I'm on it", "RESOLVED": "Resolved (explain)",
                                              "RISK_ACCEPTED": "Accept the risk (justify)"}[s])
        note = c2.text_area("Note", value=sel["note"] or "", placeholder="What was done, or why the risk is acceptable")
        st.caption("Tip: fixing the underlying data clears the exception automatically at the next control run.")
        if st.form_submit_button("Save", type="primary"):
            def _upd():
                db.execute("""update ctl.control_exception set status = %s, assigned_to = coalesce(assigned_to, %s),
                              resolution_note = nullif(%s, ''), resolved_at = case when %s in ('RESOLVED','RISK_ACCEPTED') then now() end
                              where exception_id = %s""", (new, me, note.strip(), new, xid), fetch=False)
            ui.act(_upd, "Exception updated.")
