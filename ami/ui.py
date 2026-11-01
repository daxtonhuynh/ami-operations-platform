"""Formatting and small UI building blocks shared by every page (English labels, VND amounts)."""
from __future__ import annotations

import datetime as dt
from typing import Callable, Iterable

import pandas as pd
import streamlit as st

from ami import auth, config, db

MONEY = st.column_config.NumberColumn(format="localized")


# ------------------------------------------------------------------------------------------------ formatting
def vnd(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "-"
    return f"{float(x):,.0f} ₫"


def vnd_short(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "-"
    v = float(x)
    for div, unit in ((1e9, "bn"), (1e6, "M"), (1e3, "k")):
        if abs(v) >= div:
            return f"{v / div:,.{2 if div == 1e9 else 1}f}{unit} ₫"
    return f"{v:,.0f} ₫"


def date(d) -> str:
    if d is None or (isinstance(d, float) and pd.isna(d)):
        return "-"
    if isinstance(d, str):
        d = dt.date.fromisoformat(d[:10])
    return d.strftime("%a %d %b %Y")


def period_label(pid: int) -> str:
    return dt.date(pid // 100, pid % 100, 1).strftime("%b %Y")


def pct(x, digits=0) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "-"
    return f"{float(x) * 100:.{digits}f}%"


# ------------------------------------------------------------------------------------------------ page frame
def accent():
    """Short amber bar under a page title - the bar under the "i" of the AMI logo."""
    st.html(f'<div style="width:44px;height:5px;border-radius:3px;background:{config.BRAND_AMBER};margin-top:-0.6rem"></div>')


def header(title: str, caption: str | None = None):
    st.title(title, anchor=False)
    accent()
    if caption:
        st.caption(caption)
    for kind, text in st.session_state.pop("_flash", []):
        (st.success if kind == "ok" else st.warning)(text, icon=":material/check_circle:" if kind == "ok" else None)


def flash(text: str, kind: str = "ok"):
    """Message shown at the top of the page after the next rerun."""
    st.session_state.setdefault("_flash", []).append((kind, text))


def act(fn: Callable, success: str | Callable | None = None, rerun: bool = True):
    """Run a business action; show the database's message if a rule refuses it."""
    try:
        result = fn()
    except db.BusinessRuleError as e:
        st.error(str(e), icon=":material/block:")
        return None
    if success:
        flash(success(result) if callable(success) else success)
    if rerun:
        st.rerun()
    return result


def kpis(items: Iterable[tuple], columns: int | None = None):
    items = list(items)
    n = columns or (len(items) if len(items) <= 4 else 3 if len(items) <= 6 else 4)
    for start in range(0, len(items), n):
        cols = st.columns(n)
        for i, it in enumerate(items[start:start + n]):
            label, value = it[0], it[1]
            help_ = it[2] if len(it) > 2 else None
            delta = it[3] if len(it) > 3 else None
            cols[i].metric(label, value, delta=delta, help=help_, border=True)


def table(frame: pd.DataFrame, money: Iterable[str] = (), dates: Iterable[str] = (), pcts: Iterable[str] = (),
          labels: dict | None = None, key: str | None = None, select: bool = False, height="auto", hide: Iterable[str] = (),
          column_order: list | None = None):
    """Show a table; with select=True returns the selected row as a dict (or None)."""
    cfg = {}
    for c in money:
        if c in frame.columns:
            cfg[c] = st.column_config.NumberColumn((labels or {}).get(c, c.replace("_", " ").capitalize()), format="localized")
    for c in dates:
        if c in frame.columns:
            cfg[c] = st.column_config.DateColumn((labels or {}).get(c, c.replace("_", " ").capitalize()), format="DD MMM YYYY")
    for c in pcts:
        if c in frame.columns:
            cfg[c] = st.column_config.NumberColumn((labels or {}).get(c, c.replace("_", " ").capitalize()), format="percent")
    for c in frame.columns:
        if c not in cfg:
            cfg[c] = st.column_config.Column((labels or {}).get(c, c.replace("_", " ").capitalize()))
    for c in hide:
        cfg[c] = None
    order = column_order or [c for c in frame.columns if c not in set(hide)]
    frame = frame.copy()
    for c in frame.columns:                      # blank instead of "None" in text columns
        if frame[c].dtype == object and c not in cfg_money_dates(money, dates):
            frame[c] = frame[c].where(frame[c].notna(), "")
    if not select:
        st.dataframe(frame, hide_index=True, column_config=cfg, height=height, column_order=order, key=key)
        return None
    ev = st.dataframe(frame, hide_index=True, column_config=cfg, height=height, column_order=order, key=key,
                      on_select="rerun", selection_mode="single-row")
    sel = ev.selection.rows if ev and ev.selection else []
    return frame.iloc[sel[0]].to_dict() if sel else None


def cfg_money_dates(money, dates):
    return set(money) | set(dates)


def empty(text: str):
    st.info(text, icon=":material/inbox:")


def read_only_note():
    if auth.read_only():
        st.caption(":material/visibility: Read-only access: the Director sees every figure but changes nothing.")


STATUS_COLORS = {
    "OPEN": "red", "IN_PROGRESS": "orange", "RESOLVED": "green", "RISK_ACCEPTED": "violet", "CLEARED": "gray",
    "HIGH": "red", "MEDIUM": "orange", "LOW": "gray",
}


def badge(text: str, color: str | None = None):
    st.badge(text.replace("_", " ").title(), color=color or STATUS_COLORS.get(text, "blue"))


def emp_options(role_code: str | None = None, active_on: dt.date | None = None) -> pd.DataFrame:
    """Employees for pick lists (optionally only those holding a role)."""
    sql = """select distinct e.employee_id, e.full_name, e.name_code
             from hr.employee e left join hr.employee_role r using (employee_id)
             where (%(role)s::text is null or r.role_code = %(role)s)
               and (e.end_date is null or e.end_date > %(d)s) order by e.full_name"""
    return db.df(sql, {"role": role_code, "d": active_on or db.business_date()})


def choose(label: str, frame: pd.DataFrame, id_col: str, text: Callable[[dict], str], key: str | None = None,
           index: int | None = 0, placeholder: str | None = None, help: str | None = None, disabled: bool = False):
    """Select box over a dataframe; returns the chosen row as a dict (or None)."""
    recs = frame.to_dict("records")
    ids = [r[id_col] for r in recs]
    by_id = {r[id_col]: r for r in recs}
    if not ids:
        st.selectbox(label, ["(nothing to choose)"], disabled=True, key=key)
        return None
    chosen = st.selectbox(label, ids, index=index if index is None or index < len(ids) else 0,
                          format_func=lambda i: text(by_id[i]), key=key, placeholder=placeholder, help=help, disabled=disabled)
    return by_id.get(chosen)
