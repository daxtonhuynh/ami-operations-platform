"""Settings and the role -> workspace map.

Settings come from Streamlit secrets (.streamlit/secrets.toml or the hosting platform) or environment variables:

    DATABASE_URL   postgresql://ami_app.<project>:<password>@<pooler-host>:5432/postgres   (required in production)
    DEMO_MODE      "true" shows the one-click demo accounts on the sign-in page
    DEMO_PASSWORD  password shared by the demo accounts (must match the generated dataset)
"""
from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

# AMI Education brand (logo colours): navy for structure and actions, amber for accents.
BRAND_NAVY, BRAND_AMBER = "#000080", "#FDA50F"
BRAND_DIR = Path(__file__).parent / "assets" / "brand"
LOGO = str(BRAND_DIR / "ami-logo.png")                  # full colour, for light backgrounds
LOGO_REVERSE = str(BRAND_DIR / "ami-logo-reverse.png")  # white and amber, for the navy sidebar and PDF headers
ICON = str(BRAND_DIR / "ami-icon.png")                  # square mark: favicon and collapsed sidebar

ROLE_LABELS = {
    "LEARNING_ADVISOR": "Learning Advisor",
    "ACADEMIC_MANAGER": "Academic Manager",
    "HR_MANAGER": "HR Manager",
    "FINANCE_MANAGER": "Finance Manager",
    "DIRECTOR": "Director (read only)",
}

# Database group role used for every transaction of an application role (see database/06_security.sql).
DB_ROLES = {
    "LEARNING_ADVISOR": "ami_learning_advisor",
    "ACADEMIC_MANAGER": "ami_academic_manager",
    "HR_MANAGER": "ami_hr_manager",
    "FINANCE_MANAGER": "ami_finance_manager",
    "DIRECTOR": "ami_director",
}


def setting(name: str, default: str | None = None) -> str | None:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # no secrets file
        pass
    return os.environ.get(name, default)


def database_url() -> str:
    return setting("DATABASE_URL", "postgresql:///ami_demo")


def demo_mode() -> bool:
    return (setting("DEMO_MODE", "true") or "").lower() in ("1", "true", "yes", "on")


def demo_password() -> str:
    return setting("DEMO_PASSWORD", "ami-demo")


def _page(path: str, title: str, icon: str, default: bool = False):
    return st.Page(f"ami/pages/{path}.py", title=title, icon=f":material/{icon}:", default=default,
                   url_path=path.replace("/", "-"))


def pages_for(role_code: str):
    """The workspace of each role: sections and pages shown in the sidebar."""
    if role_code == "LEARNING_ADVISOR":
        return {
            "": [_page("sales/today", "My day", "today", default=True)],
            "Sales": [_page("sales/leads", "Leads", "person_search"),
                      _page("sales/tests", "Placement tests", "quiz"),
                      _page("sales/enrol", "New enrolment", "how_to_reg")],
            "Receipts": [_page("sales/students", "Students & balances", "account_balance_wallet"),
                         _page("sales/receipts", "Receipt register", "receipt_long"),
                         _page("sales/cash", "Daily cash close", "point_of_sale")],
            "Controls": [_page("shared/controls", "My exceptions", "rule")],
        }
    if role_code == "ACADEMIC_MANAGER":
        return {
            "": [_page("academic/today", "Academic overview", "today", default=True)],
            "Classes": [_page("academic/classes", "Classes & rosters", "groups"),
                        _page("academic/open_class", "Open a class", "add_circle"),
                        _page("academic/sessions", "Confirm sessions", "event_available")],
            "Catalogue": [_page("academic/catalogue", "Courses & calendar", "menu_book")],
            "Controls": [_page("shared/controls", "My exceptions", "rule")],
        }
    if role_code == "HR_MANAGER":
        return {
            "": [_page("hr/today", "HR overview", "today", default=True)],
            "People": [_page("hr/staff", "Staff & HR codes", "badge"),
                       _page("hr/rates", "Pay rates", "payments"),
                       _page("hr/shifts", "Advisor shifts", "schedule")],
            "Payroll": [_page("hr/payroll", "Payroll runs", "request_quote")],
            "Controls": [_page("shared/controls", "My exceptions", "rule")],
        }
    if role_code == "FINANCE_MANAGER":
        return {
            "": [_page("finance/dashboard", "Finance dashboard", "monitoring", default=True),
                 _page("finance/approvals", "Approvals", "task_alt")],
            "Revenue": [_page("finance/receivables", "Receivables & collections", "account_balance"),
                        _page("finance/revenue", "Revenue & deferred", "stacked_line_chart"),
                        _page("finance/pnl", "P&L: cash vs accrual", "table_chart")],
            "Spend": [_page("finance/expenses", "Expenses & vouchers", "shopping_cart"),
                      _page("finance/assets", "Fixed assets", "inventory_2")],
            "Close & control": [_page("finance/close", "Month-end close", "lock_clock"),
                                _page("shared/controls", "Control centre", "rule"),
                                _page("finance/prices", "Prices & settings", "sell"),
                                _page("shared/audit", "Audit trail", "history")],
        }
    if role_code == "DIRECTOR":
        return {
            "": [_page("finance/dashboard", "Business dashboard", "monitoring", default=True)],
            "Finance": [_page("finance/pnl", "P&L: cash vs accrual", "table_chart"),
                        _page("finance/revenue", "Revenue & deferred", "stacked_line_chart"),
                        _page("finance/receivables", "Receivables", "account_balance")],
            "Operations": [_page("academic/classes", "Classes & rosters", "groups"),
                           _page("shared/controls", "Control centre", "rule"),
                           _page("shared/audit", "Audit trail", "history")],
        }
    raise ValueError(f"Unknown role {role_code}")
