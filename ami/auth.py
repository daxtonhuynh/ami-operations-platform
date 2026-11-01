"""Sign-in and the signed-in user (kept in the Streamlit session)."""
from __future__ import annotations

import streamlit as st

from ami import config, db

ROLE_LABELS = config.ROLE_LABELS


def sign_in(username: str, password: str) -> bool:
    if not username or not password:
        return False
    try:
        row = db.authenticate(username.strip().lower(), password)
    except Exception:
        return False
    if not row:
        return False
    st.session_state["user"] = dict(row)
    return True


def sign_out():
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    db.clear_cache()


def current_user() -> dict | None:
    return st.session_state.get("user")


def role() -> str | None:
    u = current_user()
    return u["role_code"] if u else None


def employee_id() -> int | None:
    u = current_user()
    return u.get("employee_id") if u else None


def read_only() -> bool:
    return role() == "DIRECTOR"


def require(*roles: str):
    """Stop the page unless the user has one of the roles (the database enforces the same rule)."""
    if role() not in roles:
        st.warning("This page belongs to another role's workspace.")
        st.stop()


def demo_mode() -> bool:
    return config.demo_mode()


def demo_password() -> str:
    return config.demo_password()
