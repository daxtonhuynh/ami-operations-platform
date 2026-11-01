"""Database access.

Every statement runs inside a transaction opened with the signed-in user's database role:

    SET LOCAL ROLE ami_<role>;
    SELECT set_config('ami.app_user', <username>, true), set_config('ami.app_role', <ROLE>, true);

so PostgreSQL itself decides what the user may read and do (grants, row-level security), and the audit trail records
who did what. Business actions are calls to database functions (billing.enrol, billing.record_receipt, ...); when a
rule is broken the function raises an exception whose message is shown to the user as it is.
"""
from __future__ import annotations

import contextlib
import datetime as dt
from typing import Any

import pandas as pd
import psycopg
import streamlit as st
from psycopg import errors
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from ami import config


class BusinessRuleError(Exception):
    """A rule of the business refused the action (raised by the database)."""


@st.cache_resource(show_spinner=False)
def _pool() -> ConnectionPool:
    # prepare_threshold=None: no server-side prepared statements, so the app also works behind a transaction pooler.
    return ConnectionPool(config.database_url(), min_size=1, max_size=6, open=True, timeout=20,
                          kwargs={"prepare_threshold": None, "connect_timeout": 10, "application_name": "ami-operations"})


def _user() -> dict | None:
    return st.session_state.get("user")


@contextlib.contextmanager
def session(as_user: dict | None | bool = True):
    """A transaction as the signed-in user (default), as another user dict, or with no role (as_user=False)."""
    user = _user() if as_user is True else (as_user or None)
    with _pool().connection() as conn:
        conn.row_factory = dict_row
        with conn.transaction():
            if user:
                role = config.DB_ROLES[user["role_code"]]           # fixed whitelist: never user input
                conn.execute(f"set local role {role}")
                conn.execute("select set_config('ami.app_user', %s, true), set_config('ami.app_role', %s, true)",
                             (user["username"], user["role_code"]))
            yield conn


def _friendly(e: Exception) -> str:
    diag = getattr(e, "diag", None)
    msg = (diag.message_primary if diag and diag.message_primary else str(e)).strip()
    if isinstance(e, errors.InsufficientPrivilege):
        return "Your role is not allowed to do this. " + msg
    if isinstance(e, errors.UniqueViolation):
        if "enrollment_one_active_per_class" in msg:
            return "This learner already has an active enrolment in that class (BR-02)."
        return "This record already exists. " + (diag.message_detail or "" if diag else "")
    if isinstance(e, errors.ForeignKeyViolation):
        return "A referenced record does not exist or is still in use. " + (diag.message_detail or "" if diag else "")
    if isinstance(e, errors.CheckViolation):
        return f"The values break a rule of the data model ({diag.constraint_name if diag else 'check'})."
    if isinstance(e, errors.ExclusionViolation):
        return "The dates overlap an existing entry (only one valid version per date is allowed)."
    return msg


def df(sql: str, params: Any = None) -> pd.DataFrame:
    with session() as conn:
        cur = conn.execute(sql, params)
        rows = cur.fetchall()
        cols = [c.name for c in cur.description] if cur.description else []
    frame = pd.DataFrame(rows, columns=cols)
    for c in frame.columns:                         # Decimal -> float for display and charts
        if frame[c].dtype == object and len(frame) and frame[c].map(lambda v: v.__class__.__name__ == "Decimal").any():
            frame[c] = pd.to_numeric(frame[c], errors="coerce")
    return frame


def rows(sql: str, params: Any = None) -> list[dict]:
    with session() as conn:
        return conn.execute(sql, params).fetchall()


def one(sql: str, params: Any = None) -> dict | None:
    with session() as conn:
        return conn.execute(sql, params).fetchone()


def val(sql: str, params: Any = None):
    r = one(sql, params)
    return next(iter(r.values())) if r else None


def execute(sql: str, params: Any = None, fetch: bool = True):
    """Run a business action. Raises BusinessRuleError with the database's own message when a rule refuses it."""
    try:
        with session() as conn:
            cur = conn.execute(sql, params)
            if fetch and cur.description:
                r = cur.fetchone()
                return next(iter(r.values())) if r else None
            return None
    except psycopg.Error as e:
        raise BusinessRuleError(_friendly(e)) from e
    finally:
        clear_cache()


@contextlib.contextmanager
def write():
    """Several statements in one transaction (e.g. a learner, a guardian and a lead). All or nothing."""
    try:
        with session() as conn:
            yield conn
    except psycopg.Error as e:
        raise BusinessRuleError(_friendly(e)) from e
    finally:
        clear_cache()


def preview(sql: str, params: Any, *queries: tuple[str, Any]) -> list[pd.DataFrame]:
    """Run an action, read its effects, then roll everything back (e.g. price and schedule of an enrolment)."""
    out = []
    try:
        with session() as conn:
            res = conn.execute(sql, params).fetchone()
            key = next(iter(res.values())) if res else None
            for q, p in queries:
                cur = conn.execute(q, p(key) if callable(p) else p)
                out.append(pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description]))
            raise _Rollback
    except _Rollback:
        return out
    except psycopg.Error as e:
        raise BusinessRuleError(_friendly(e)) from e


class _Rollback(Exception):
    pass


def authenticate(username: str, password: str) -> dict | None:
    with session(as_user=False) as conn:
        return conn.execute("select * from app.authenticate(%s, %s)", (username, password)).fetchone()


@st.cache_data(ttl=60, show_spinner=False)
def business_date() -> dt.date:
    with session(as_user=False) as conn:
        return conn.execute("select ref.as_of_date() as d").fetchone()["d"]


@st.cache_data(ttl=300, show_spinner=False)
def lookup(sql: str, role_code: str, params: tuple = ()) -> pd.DataFrame:
    """Cached reference lists (courses, staff, rooms...). Keyed by role so grants still apply."""
    return df(sql, params or None)


def clear_cache():
    lookup.clear()
