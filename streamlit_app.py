"""AMI Operations Platform - entry point.

    streamlit run streamlit_app.py

Signs the user in, then shows only the workspace of their role:
Learning Advisors enter sales and receipts; the Academic Manager runs classes; the HR Manager runs time and
payroll; the Finance Manager runs spend, revenue, reporting and the month-end close.
"""
import streamlit as st

from ami import auth, config, db, ui

st.set_page_config(page_title="AMI Operations", page_icon=config.ICON, layout="wide",
                   initial_sidebar_state="expanded")

DEMO_ACCOUNTS = [
    ("la.nhi", "Learning Advisor", "Leads, tests, enrolments and receipts - the data-entry desk"),
    ("academic.manager", "Academic Manager", "Opens classes, assigns teachers, confirms sessions"),
    ("hr.manager", "HR Manager", "Staff, pay rates, shifts and the monthly payroll"),
    ("finance.manager", "Finance Manager", "Expenses, collections, revenue recognition, P&L and month-end close"),
    ("director", "Director", "Read-only view of the whole business"),
]


def login_page():
    left, right = st.columns([1.1, 1], gap="large")
    with left:
        st.image(config.LOGO, width=150)
        st.title("Operations platform", anchor=False)
        ui.accent()
        st.markdown("**One database for an English centre's whole operating cycle** - from the first inquiry to the "
                    "month-end P&L. Each role works in its own workspace; every action passes the same business rules "
                    "in PostgreSQL, so a learner, a payment or an hour taught is entered once and reused everywhere.")
        st.markdown("""
- **Sales & receipts** (Learning Advisors): leads, placement tests, enrolment pricing, instalments, receipts
- **Academic** (Academic Manager): classes, timetables, teachers, session confirmation, rosters
- **HR & payroll** (HR Manager): HR codes, dated pay rates, shifts, payroll runs and payslips
- **Finance** (Finance Manager): expenses, collections, revenue recognition, cash vs accrual P&L, controls, period close
""")
        try:
            bd = db.business_date()
            st.caption(f"Business date of this demo: **{ui.date(bd)}** · all people and amounts are fictitious")
        except Exception as e:  # database not reachable yet (the details are in the app logs)
            st.error(f"The demo database is not reachable right now ({e}). If the demo was idle for a while it may be "
                     "waking up: reload the page in a minute.", icon=":material/cloud_off:")
            st.stop()
    with right:
        with st.container(border=True):
            st.subheader("Sign in", anchor=False)
            with st.form("login"):
                username = st.text_input("Username", autocomplete="username")
                password = st.text_input("Password", type="password", autocomplete="current-password")
                if st.form_submit_button("Sign in", type="primary", width="stretch"):
                    if auth.sign_in(username, password):
                        st.rerun()
                    st.error("Unknown username or wrong password.")
        if auth.demo_mode():
            with st.container(border=True):
                st.subheader("Try a role", anchor=False)
                st.caption(f"Demo accounts share the password `{auth.demo_password()}`.")
                for username, role, text in DEMO_ACCOUNTS:
                    c1, c2 = st.columns([1, 1.3], vertical_alignment="center")
                    if c1.button(role, key=f"demo-{username}", width="stretch", icon=":material/login:"):
                        if auth.sign_in(username, auth.demo_password()):
                            st.rerun()
                        st.error("The demo account is not available.")
                    c2.caption(text)


user = auth.current_user()
if not user:
    st.navigation([st.Page(login_page, title="Sign in", icon=":material/login:")], position="hidden").run()
    st.stop()

st.logo(config.LOGO_REVERSE, size="large", icon_image=config.ICON)
nav = st.navigation(config.pages_for(user["role_code"]), position="sidebar")
with st.sidebar:
    st.markdown(f"**{user['full_name']}**  \n{auth.ROLE_LABELS[user['role_code']]}")
    st.caption(f"Business date: {ui.date(db.business_date())}")
    if st.button("Sign out", icon=":material/logout:", width="stretch"):
        auth.sign_out()
        st.rerun()
nav.run()
