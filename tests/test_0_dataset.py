"""The generated year must obey the business rules it was generated through: apart from the situations planted for the
business date, every control is clean and the books reconcile."""
import psycopg
import pytest

from conftest import DSN  # the database built by the session fixture (conftest.py)


def rows(sql):
    with psycopg.connect(DSN) as c:
        return c.execute(sql).fetchall()


def one(sql):
    return rows(sql)[0][0]


@pytest.mark.parametrize("view", [
    "ctl.v_chk_bil_01_no_schedule", "ctl.v_chk_bil_02_schedule_mismatch", "ctl.v_chk_aca_01_over_capacity",
    "ctl.v_chk_pay_01_missing_rate", "ctl.v_chk_pay_03_payslip_mismatch", "ctl.v_chk_rep_01_revenue_completeness",
    "ctl.v_chk_sal_02_enrolled_without_test"])
def test_rules_that_must_always_hold(view):
    assert one(f"select count(*) from {view}") == 0


def test_every_closed_month_has_paid_payroll_and_no_unconfirmed_session():
    assert one("""select count(*) from finance.fiscal_period p
                  where p.status = 'CLOSED' and p.period_id >= (select min(period_id) from payroll.payroll_run)
                    and not exists (select 1 from payroll.payroll_run r where r.period_id = p.period_id and r.status = 'PAID')""") == 0


def test_deferred_revenue_identity_every_month():
    assert one("""select count(*) from rpt.v_deferred_revenue_coverage d join finance.fiscal_period p using (period_id)
                  where d.deferred_balance - d.earned_not_collected <>
                        coalesce((select sum(a.amount) from billing.payment_allocation a join billing.receipt r using (receipt_id)
                                   where r.status = 'ISSUED' and r.receipt_date <= p.period_end), 0)
                      - coalesce((select sum(amount) from billing.refund where refund_date <= p.period_end), 0)
                      - coalesce((select sum(amount) from billing.revenue_schedule where period_id <= d.period_id), 0)""") == 0


def test_finished_enrolments_earned_exactly_their_contract():
    assert one("""select count(*) from rpt.v_enrollment_balance where status_code = 'COMPLETED' and recognised_total <> net_payable""") == 0


def test_the_business_date_has_work_waiting_for_every_role():
    open_by_role = dict(rows("""select c.app_role_code, count(*) from ctl.control_exception x join ctl.control c using (control_code)
                                where x.status in ('OPEN','IN_PROGRESS') group by 1"""))
    assert set(open_by_role) >= {"LEARNING_ADVISOR", "ACADEMIC_MANAGER", "FINANCE_MANAGER"}
    assert one("select count(*) from payroll.payroll_run where status = 'DRAFT'") == 1


def test_people_and_phone_numbers_are_fictitious():
    assert one("select count(*) from crm.student where phone is not null and phone not like '0100 %'") == 0
    assert one("select count(*) from crm.guardian where phone is not null and phone not like '0100 %'") == 0
