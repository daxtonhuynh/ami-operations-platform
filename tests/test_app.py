"""End-to-end tests of the application: every page for every role, then one business day worked through the screens
(sales -> receipts -> approvals -> session confirmation -> payroll -> month-end close), each action running under the
user's database role.

    pytest -q tests            # needs PostgreSQL; builds a throw-away database "ami_apptest"
"""
from __future__ import annotations

import psycopg
import pytest
from streamlit.testing.v1 import AppTest

from conftest import DSN, ROOT


def user(username: str) -> dict:
    with psycopg.connect(DSN) as c:
        r = c.execute("select user_id, username, full_name, role_code, employee_id from app.app_user where username = %s", (username,)).fetchone()
    return dict(zip(["user_id", "username", "full_name", "role_code", "employee_id"], r))


def app_as(username: str, page: str | None = None) -> AppTest:
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=90)
    at.run()
    at.session_state["user"] = user(username)
    at.run()
    if page:
        at.switch_page(f"ami/pages/{page}.py")
        at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def q(sql, params=None):
    with psycopg.connect(DSN) as c:
        return c.execute(sql, params).fetchone()


def button(at, label):
    for b in at.button:
        if b.label == label:
            return b
    raise AssertionError(f"No button {label!r}: {[b.label for b in at.button]}")


def widget(items, label):
    for w in items:
        if w.label == label:
            return w
    raise AssertionError(f"No widget {label!r}: {[w.label for w in items]}")


def flashed(at) -> list[str]:
    return [s.value for s in at.success] + [e.value for e in at.error]


# ------------------------------------------------------------------------------------------------ sign-in and pages
def test_sign_in_with_the_demo_password():
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=60)
    at.run()
    widget(at.text_input, "Username").input("finance.manager")
    widget(at.text_input, "Password").input("ami-demo")
    button(at, "Sign in").click()
    at.run()
    assert at.session_state["user"]["role_code"] == "FINANCE_MANAGER"


def test_wrong_password_is_refused():
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=60)
    at.run()
    widget(at.text_input, "Username").input("la.nhi")
    widget(at.text_input, "Password").input("guess")
    button(at, "Sign in").click()
    at.run()
    assert "user" not in at.session_state
    assert any("wrong password" in e.value for e in at.error)


PAGES = {
    "la.nhi": ["sales/today", "sales/leads", "sales/tests", "sales/enrol", "sales/students", "sales/receipts", "sales/cash", "shared/controls"],
    "academic.manager": ["academic/today", "academic/classes", "academic/open_class", "academic/sessions", "academic/catalogue", "shared/controls"],
    "hr.manager": ["hr/today", "hr/staff", "hr/rates", "hr/shifts", "hr/payroll", "shared/controls"],
    "finance.manager": ["finance/dashboard", "finance/approvals", "finance/receivables", "finance/revenue", "finance/pnl", "finance/expenses",
                        "finance/assets", "finance/close", "shared/controls", "finance/prices", "shared/audit"],
    "director": ["finance/dashboard", "finance/pnl", "finance/revenue", "finance/receivables", "academic/classes", "shared/controls", "shared/audit"],
}


@pytest.mark.parametrize("username,page", [(u, p) for u, ps in PAGES.items() for p in ps])
def test_every_page_renders(username, page):
    at = app_as(username, page)
    assert at.title, "page has a title"
    assert not at.exception


def test_a_role_cannot_open_another_workspace():
    at = app_as("la.nhi")
    with pytest.raises(Exception):          # not in the advisor's navigation at all
        at.switch_page("ami/pages/finance/close.py")


# ------------------------------------------------------------------------------------------------ one business day, through the screens
def test_1_advisor_registers_a_new_lead():
    at = app_as("la.nhi", "sales/leads")
    widget(at.text_input, "Full name *").input("Trịnh Gia Hân")
    widget(at.text_input, "Guardian name").input("Trịnh Văn Phúc")
    widget(at.text_input, "Guardian phone").input("0100 555 777")
    widget(at.selectbox, "Programme *").select("IELTS")
    button(at, "Create lead").click()
    at.run()
    assert not at.exception
    row = q("""select s.student_code, l.stage_code, e.employee_code from crm.lead l join crm.student s using (student_id)
               join hr.employee e on e.employee_id = l.owner_employee_id where s.full_name = 'Trịnh Gia Hân'""")
    assert row[1] == "NEW" and row[2] == "E005"


def test_2_advisor_books_and_records_the_placement_test():
    lead_id = q("select l.lead_id from crm.lead l join crm.student s using (student_id) where s.full_name = 'Trịnh Gia Hân'")[0]
    at = app_as("la.nhi", "sales/leads")
    at.session_state["lead_search"] = "Trịnh Gia"
    at.run()
    at.session_state["leads_tbl"] = {"selection": {"rows": [0], "columns": [], "cells": []}}
    at.run()
    button(at, "Book test").click()
    at.run()
    assert q("select status from crm.placement_test where lead_id = %s", (lead_id,))[0] == "BOOKED"
    at = app_as("la.nhi", "sales/tests")
    ids = [r for r in at.dataframe[0].value["learner"]]
    at.session_state["booked"] = {"selection": {"rows": [ids.index("Trịnh Gia Hân")], "columns": [], "cells": []}}
    at.run()
    button(at, "Save result").click()
    at.run()
    assert q("select stage_code from crm.lead where lead_id = %s", (lead_id,))[0] == "TESTED"


def test_3_advisor_enrols_with_a_preview_then_confirms():
    lead_id = q("select l.lead_id from crm.lead l join crm.student s using (student_id) where s.full_name = 'Trịnh Gia Hân'")[0]
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=90)
    at.run()
    at.session_state["user"] = user("la.nhi")
    at.session_state["enrol_lead_id"] = lead_id
    at.run()
    at.switch_page("ami/pages/sales/enrol.py")
    at.run()
    button(at, "Preview price and schedule").click()
    at.run()
    assert not at.exception
    assert any(m.label == "Net payable" for m in at.metric), "preview shows the price"
    before = q("select count(*) from billing.enrollment")[0]
    button(at, "Confirm enrolment").click()
    at.run()
    assert q("select count(*) from billing.enrollment")[0] == before + 1
    e = q("""select e.enrollment_id, e.status_code, l.qualification_code from billing.enrollment e join crm.lead l using (lead_id)
             where e.lead_id = %s""", (lead_id,))
    assert e[2] == "CONVERTED"


def test_4_advisor_takes_the_first_payment_and_asks_for_a_void():
    eid, code = q("""select e.enrollment_id, e.enrollment_code from billing.enrollment e join crm.student s using (student_id)
                     where s.full_name = 'Trịnh Gia Hân'""")
    at = app_as("la.nhi", "sales/students")
    at.session_state["st_q"] = code
    at.run()
    at.session_state["bal"] = {"selection": {"rows": [0], "columns": [], "cells": []}}
    at.run()
    button(at, "Issue receipt").click()
    at.run()
    rno, amount = q("select receipt_no, amount from billing.receipt where enrollment_id = %s", (eid,))
    assert amount > 0
    assert q("select outstanding_receivable < net_payable from rpt.v_enrollment_balance where enrollment_id = %s", (eid,))[0]
    at = app_as("la.nhi", "sales/receipts")
    names = list(at.dataframe[0].value["receipt_no"])
    at.session_state["recs"] = {"selection": {"rows": [names.index(rno)], "columns": [], "cells": []}}
    at.run()
    widget(at.text_area, "Reason *").input("Parent paid by bank transfer, keyed as cash")
    button(at, "Request void").click()
    at.run()
    assert q("select void_requested_at is not null from billing.receipt where receipt_no = %s", (rno,))[0]


def test_5_finance_approves_the_void_and_a_discount():
    rno = q("select receipt_no from billing.receipt where void_requested_at is not null and status = 'ISSUED' order by receipt_id desc limit 1")[0]
    at = app_as("finance.manager", "finance/approvals")
    tbl = [d for d in at.dataframe if "receipt_no" in d.value.columns][0]
    at.session_state["voids"] = {"selection": {"rows": [list(tbl.value["receipt_no"]).index(rno)], "columns": [], "cells": []}}
    at.run()
    button(at, "Approve void").click()
    at.run()
    assert q("select status from billing.receipt where receipt_no = %s", (rno,))[0] == "VOID"
    pending = q("select count(*) from billing.enrollment_discount where approval_status = 'PENDING'")[0]
    at = app_as("finance.manager", "finance/approvals")
    at.session_state["disc"] = {"selection": {"rows": [0], "columns": [], "cells": []}}
    at.run()
    button(at, "Approve").click()
    at.run()
    assert q("select count(*) from billing.enrollment_discount where approval_status = 'PENDING'")[0] == pending - 1
    who = q("select app_user, db_role from app.audit_log where table_name = 'billing.receipt' and row_key = %s order by audit_id desc limit 1", (rno,))
    assert who == ("finance.manager", "FINANCE_MANAGER")


def test_6_payroll_cannot_be_approved_before_sessions_are_confirmed():
    at = app_as("hr.manager", "hr/payroll")
    button(at, "Calculate").click()
    at.run()
    assert q("select status from payroll.payroll_run where period_id = 202610")[0] == "CALCULATED"
    at = app_as("hr.manager", "hr/payroll")
    button(at, "Approve").click()
    at.run()
    assert any("not confirmed" in e.value for e in at.error), "the database refuses: sessions unconfirmed"
    assert q("select status from payroll.payroll_run where period_id = 202610")[0] == "CALCULATED"


def test_7_academic_manager_confirms_the_sessions():
    at = app_as("academic.manager", "academic/sessions")
    labels = [b.label for b in at.button if b.label.startswith("Confirm ")]
    assert labels
    button(at, labels[0]).click()
    at.run()
    left = q("""select count(*) from academic.class_session s join academic.class c using (class_id)
                where s.session_date <= '2026-10-31' and c.lifecycle_status <> 'CANCELLED' and s.status = 'SCHEDULED'""")[0]
    assert left == 0


def test_8_hr_recalculates_and_approves_payroll():
    at = app_as("hr.manager", "hr/payroll")
    button(at, "Calculate").click()
    at.run()
    at = app_as("hr.manager", "hr/payroll")
    button(at, "Approve").click()
    at.run()
    assert q("select status from payroll.payroll_run where period_id = 202610")[0] == "APPROVED"


def test_9_finance_closes_the_month_and_it_is_locked():
    at = app_as("finance.manager", "finance/close")
    button(at, "Close Oct 2026").click()
    at.run()
    assert q("select status from finance.fiscal_period where period_id = 202610")[0] == "CLOSED"
    at = app_as("la.nhi", "sales/students")
    at.session_state["st_status"] = "Overdue"
    at.run()
    at.session_state["bal"] = {"selection": {"rows": [0], "columns": [], "cells": []}}
    at.run()
    button(at, "Issue receipt").click()
    at.run()
    assert any("closed" in e.value for e in at.error), "a receipt dated in the closed month is refused"


def test_10_director_reads_but_cannot_change():
    at = app_as("director", "shared/controls")
    at.session_state["exc"] = {"selection": {"rows": [0], "columns": [], "cells": []}}
    at.run()
    assert not [b for b in at.button if b.label == "Save"], "no editing controls for the Director"
