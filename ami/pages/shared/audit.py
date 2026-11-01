"""Audit trail (BR-12): who changed a financially significant record, when, in which role, before and after."""
import datetime as dt
import json

import pandas as pd
import streamlit as st

from ami import auth, db, ui

auth.require("FINANCE_MANAGER", "DIRECTOR")
bd = db.business_date()
ui.header("Audit trail", "Written by database triggers on every insert, update and delete of the audited tables - the application cannot skip it")

c1, c2, c3, c4 = st.columns([1.3, 1, 1.5, 1])
rng = c1.date_input("Dates", value=(bd - dt.timedelta(days=6), bd))
d0, d1 = (rng if isinstance(rng, tuple) and len(rng) == 2 else (rng, rng)) if rng else (bd, bd)
users = db.df("select distinct app_user from app.audit_log where app_user is not null order by 1")
who = c2.multiselect("User", users["app_user"])
tables = db.df("select distinct table_name from app.audit_log order by 1")
tbl = c3.multiselect("Table", tables["table_name"])
action = c4.pills("Action", ["INSERT", "UPDATE", "DELETE"], selection_mode="multi", format_func=str.title)
log = db.df("""
    select audit_id, occurred_at, app_user, db_role, table_name, action, row_key, old_row::text as old_row, new_row::text as new_row
    from app.audit_log
    where occurred_at >= (%(d0)s::timestamp at time zone 'Asia/Ho_Chi_Minh')
      and occurred_at < ((%(d1)s::date + 1)::timestamp at time zone 'Asia/Ho_Chi_Minh')
      and (%(who)s::text[] is null or app_user = any(%(who)s)) and (%(tbl)s::text[] is null or table_name = any(%(tbl)s))
      and (%(act)s::text[] is null or action = any(%(act)s))
    order by occurred_at desc, audit_id desc limit 1000""",
              {"d0": d0, "d1": d1, "who": who or None, "tbl": tbl or None, "act": action or None})
st.caption(f"{len(log)} change(s)")
if log.empty:
    ui.empty("No change in this selection.")
    st.stop()
show = log.copy()
show["occurred_at"] = show["occurred_at"].dt.tz_convert("Asia/Ho_Chi_Minh").dt.strftime("%d %b %Y %H:%M:%S")
sel = ui.table(show, hide=["audit_id", "old_row", "new_row"], key="log", select=True, height=380,
               labels={"app_user": "User", "db_role": "Role", "row_key": "Record"})
if sel:
    old = json.loads(sel["old_row"]) if sel["old_row"] else {}
    new = json.loads(sel["new_row"]) if sel["new_row"] else {}
    keys = sorted(set(old) | set(new))
    changes = [{"field": k, "before": None if k not in old else json.dumps(old.get(k), ensure_ascii=False),
                "after": None if k not in new else json.dumps(new.get(k), ensure_ascii=False)}
               for k in keys if old.get(k) != new.get(k)]
    st.markdown(f"**{sel['action'].title()} on {sel['table_name']} · {sel['row_key']}** by {sel['app_user'] or 'system'} ({sel['db_role']})")
    ui.table(pd.DataFrame(changes), key="diff")
