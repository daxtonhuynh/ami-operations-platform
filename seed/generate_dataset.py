#!/usr/bin/env python3
"""Simulate a year of operations of a fictitious AMI Education campus and leave the result in a database.

Nothing is inserted behind the application's back. The simulation walks the calendar one business day at a time and
performs each business event through the same database functions the application calls - billing.enrol,
billing.record_receipt, academic.confirm_session, payroll.calculate_run, finance.close_period, ... - signed in as the
employee who would do it. Every price, instalment, revenue line, commission, payslip, control exception and audit entry
in the demo was therefore produced by the real business rules.

    createdb ami_gen
    psql -v ON_ERROR_STOP=1 -d ami_gen -f database/build.sql
    python seed/generate_dataset.py --dsn postgresql:///ami_gen --as-of 2026-10-31
    bash seed/export_dataset.sh ami_gen > seed/demo_dataset.sql

The calendar starts on the first day of the month twelve months before the business date ("go-live": the campus opens
and pre-sells its first classes) and ends on the business date, which is frozen in ref.app_setting so that the demo is
a consistent snapshot of one working day. All people, phone numbers and amounts are fictitious; the generator is
deterministic for a given --seed and --as-of.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sys
import time
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field

import psycopg

D = dt.date
ONE = dt.timedelta(days=1)

# ----------------------------------------------------------------------------------------------- people and names
FAMILY = ["Nguyễn"] * 8 + ["Trần"] * 4 + ["Lê"] * 3 + ["Phạm"] * 2 + [
    "Huỳnh", "Hoàng", "Phan", "Vũ", "Võ", "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý", "Trương", "Đinh", "Lâm",
    "Mai", "Tạ", "Châu", "Quách", "Thái", "Kiều", "Cao", "Tô", "La"]
MIDDLE_F = ["Thị", "Ngọc", "Thu", "Thanh", "Minh", "Bảo", "Gia", "Khánh", "Mỹ", "Hoài", "Phương", "Như", "Kim", "Diệu", "Tuyết", "Yến"]
MIDDLE_M = ["Văn", "Minh", "Quốc", "Gia", "Hoàng", "Đức", "Thanh", "Tuấn", "Hữu", "Công", "Bảo", "Nhật", "Anh", "Trọng", "Đăng", "Tấn"]
GIVEN_F = ["Anh", "Châu", "Chi", "Dung", "Giang", "Hà", "Hân", "Hạnh", "Hương", "Khánh", "Lan", "Linh", "Ly", "Mai", "My",
           "Ngân", "Ngọc", "Nhi", "Nhung", "Oanh", "Phương", "Quyên", "Quỳnh", "Tâm", "Thảo", "Thư", "Trâm", "Trang",
           "Trinh", "Tú", "Uyên", "Vân", "Vy", "Yến", "Diễm", "Hiền", "Hoa", "Kiều", "Loan", "Thuỳ", "Xuân", "Hằng"]
GIVEN_M = ["An", "Bảo", "Bình", "Cường", "Danh", "Duy", "Dũng", "Đạt", "Hải", "Hào", "Hiếu", "Hoàng", "Huy", "Hùng",
           "Khang", "Khoa", "Khôi", "Kiệt", "Lâm", "Lộc", "Long", "Luân", "Minh", "Nam", "Nghĩa", "Nhân", "Phát",
           "Phong", "Phúc", "Quân", "Quang", "Sang", "Sơn", "Tài", "Thắng", "Thịnh", "Tín", "Toàn", "Trí", "Trung",
           "Tuấn", "Vinh", "Vũ", "Thiện", "Khải"]

EXTRA_SCHOOLS = [("Sunrise Primary School", "PRIMARY"), ("Harbour Lower Secondary School", "LOWER_SECONDARY"),
                 ("Lakeside High School", "UPPER_SECONDARY"), ("Bac Lieu College", "UNIVERSITY")]

# Staff of the campus: code, full name, short name, gender, employment type, home cost centre, months after go-live
# hired, roles [(role, contract stage, cost centre)], fixed monthly pay, application user
STAFF = [
    ("E001", "Phạm Quốc Dũng", "Dũng PQ", "MALE", "FULL_TIME", "921010", 0, [("CENTRE_MANAGER", "OFFICIAL", "921010")], 15000000, ("director", "DIRECTOR")),
    ("E002", "Lê Thanh Hương", "Hương LT", "FEMALE", "FULL_TIME", "921010", 0, [("FINANCE_OFFICER", "OFFICIAL", "921010")], 9000000, ("finance.manager", "FINANCE_MANAGER")),
    ("E003", "Trần Ngọc Bích", "Bích TN", "FEMALE", "FULL_TIME", "921011", 0, [("HR_OFFICER", "OFFICIAL", "921011")], 7500000, ("hr.manager", "HR_MANAGER")),
    ("E004", "Võ Minh Tâm", "Tâm VM", "MALE", "FULL_TIME", "921013", 0, [("ACADEMIC_MANAGER", "OFFICIAL", "921013"), ("TEACHER_IELTS", "OFFICIAL", "921017")], 10000000, ("academic.manager", "ACADEMIC_MANAGER")),
    ("E005", "Nguyễn Yến Nhi", "Nhi NY", "FEMALE", "PART_TIME", "921012", 0, [("LA", "OFFICIAL", "921012")], None, ("la.nhi", "LEARNING_ADVISOR")),
    ("E006", "Đỗ Đăng Khoa", "Khoa ĐĐ", "MALE", "PART_TIME", "921012", 0, [("LA", "PROBATION", "921012")], None, ("la.khoa", "LEARNING_ADVISOR")),
    ("E007", "Huỳnh Thị Mai", "Mai HT", "FEMALE", "PART_TIME", "921016", 0, [("TEACHER_AE_COMM", "OFFICIAL", "921016")], None, None),
    ("E008", "Lâm Gia Bảo", "Bảo LG", "MALE", "PART_TIME", "921015", 0, [("TEACHER_AE_COMM", "OFFICIAL", "921015")], None, None),
    ("E009", "Ngô Thanh Phong", "Phong NT", "MALE", "PART_TIME", "921017", 0, [("TEACHER_IELTS", "OFFICIAL", "921017")], None, None),
    ("E010", "Trương Mỹ Duyên", "Duyên TM", "FEMALE", "PART_TIME", "921013", 0, [("TA_AE_COMM", "OFFICIAL", "921013")], None, None),
    ("E011", "Phan Hoàng Long", "Long PH", "MALE", "PART_TIME", "921017", 0, [("AT_IELTS", "OFFICIAL", "921017")], None, None),
    ("E012", "Đặng Thu Trang", "Trang ĐT", "FEMALE", "FULL_TIME", "921014", 0, [("MARKETING", "OFFICIAL", "921014")], 6500000, None),
    ("E013", "Tạ Quang Vinh", "Vinh TQ", "MALE", "PART_TIME", "921016", 4, [("TEACHER_AE_COMM", "OFFICIAL", "921016")], None, None),
]

# Teaching lanes: one room and weekly timetable that hosts one class after another. Each lane follows a course
# progression, so learners who finish a level can continue in the next class of the same lane.
#   key, room, weekdays (ISO), start, end, delivery mode, capacity, course chain, teacher, assistant, first start (days
#   after go-live), months after go-live the lane opens
LANES = [
    ("A", "Room 101", [1, 3], "17:30", "19:00", "OFFLINE", 15, ["R1", "R2", "T1", "T2"], "E007", "E010", 19, 0),
    ("B", "Room 101", [2, 4], "17:30", "19:00", "OFFLINE", 15, ["L1", "L2", "F1", "F2"], "E007", "E010", 26, 0),
    ("C", "Room 101", [6, 7], "08:00", "09:30", "OFFLINE", 15, ["S1", "B1", "E1", "N1"], "E007", "E010", 33, 0),
    ("C2", "Room 102", [6, 7], "09:45", "11:15", "OFFLINE", 15, ["R1", "R2", "T1"], "E013", None, 20, 4),
    ("K", "Room 102", [1, 3], "17:30", "19:00", "OFFLINE", 15, ["S1", "B1", "E1"], "E008", None, 30, 0),
    ("L", "Room 102", [2, 4], "17:30", "19:00", "OFFLINE", 15, ["L1", "L2", "F1"], "E013", None, 25, 4),
    ("D", "Room 102", [1, 3, 5], "19:15", "20:45", "OFFLINE", 15, ["A1", "A2", "A3", "A1", "A2", "A3"], "E008", None, 17, 0),
    ("E", "Room 102", [2, 4, 6], "19:15", "20:45", "OFFLINE", 15, ["A1", "A2", "A3", "A1", "A2", "A3"], "E008", None, 40, 0),
    ("F", "Room 201", [1, 3, 5], "18:00", "20:00", "OFFLINE", 12, ["PRE", "BASIC", "PROGRESS", "BOOST", "PRE"], "E009", "E011", 23, 0),
    ("G", "Room 201", [2, 4, 6], "18:00", "20:00", "OFFLINE", 12, ["BASIC", "PROGRESS", "BOOST", "PRO", "BASIC"], "E004", "E011", 44, 0),
    ("H", "Online room", [2, 4, 7], "20:00", "21:30", "ONLINE", 20, ["A1", "A2", "A3", "A1", "A2"], "E007", None, 54, 0),
    ("I", "Room 101", [6, 7], "14:00", "15:30", "OFFLINE", 15, ["G9", "G12", "G6", "G9"], "E009", None, 70, 0),
    ("J", "Room 201", [6, 7], "14:00", "16:00", "OFFLINE", 12, ["PROGRESS", "BOOST", "PRO"], "E004", "E011", 95, 0),
]
# who takes over a lane when its teacher leaves
COVER = {"D": "E007", "E": "E013", "K": "E013"}
CONTINUE_RATE = {"AE": 0.62, "COMM": 0.45, "IELTS": 0.42, "PE": 0.10}

CHANNELS = {
    "AE": [("SOCIAL_MEDIA", 22), ("ONLINE_ADS", 15), ("REFERRAL_PARENT", 18), ("REFERRAL_FRIEND", 10), ("WALK_IN", 10), ("EVENT", 10), ("REFERRAL_TEACHER", 4), ("OTHER", 3)],
    "COMM": [("SOCIAL_MEDIA", 30), ("ONLINE_ADS", 25), ("REFERRAL_FRIEND", 18), ("WALK_IN", 8), ("EVENT", 6), ("OTHER", 3)],
    "IELTS": [("SOCIAL_MEDIA", 22), ("ONLINE_ADS", 16), ("MOCK_TEST", 16), ("SCHOOL_PARTNERSHIP", 14), ("REFERRAL_FRIEND", 14), ("SCHOLARSHIP_EVENT", 4), ("WALK_IN", 4)],
    "PE": [("REFERRAL_PARENT", 30), ("SCHOOL_PARTNERSHIP", 25), ("SOCIAL_MEDIA", 25), ("WALK_IN", 10)],
}
PLANS = {
    "AE": [("FULL", 35), ("P50_30_20", 25), ("MONTHLY_5", 40)],
    "COMM": [("FULL", 50), ("MONTHLY_3", 35), ("P50_30_20", 15)],
    "IELTS": [("FULL", 45), ("P50_30_20", 35), ("MONTHLY_3", 20)],
    "PE": [("FULL", 40), ("MONTHLY_3", 60)],
}
TEST_TYPE = {"AE": "APPLIED_ENGLISH", "PE": "APPLIED_ENGLISH", "COMM": "COMMUNICATION", "IELTS": "IELTS"}
TARGET_LEVEL = {"PRE": "4.0", "BASIC": "5.0", "PROGRESS": "6.0", "BOOST": "6.5", "PRO": "7.0"}
ENTRY_BAND = {"PRE": ["3.0", "3.5"], "BASIC": ["4.0", "4.5"], "PROGRESS": ["5.0", "5.5"], "BOOST": ["5.5", "6.0"], "PRO": ["6.5"]}
CEFR = ["Pre-A1", "A1-", "A1", "A1+", "A2-", "A2", "A2+", "B1-", "B1", "B1+", "B2"]

CALL_NOTES = [
    "Called back after the Facebook inquiry; interested in evening classes",
    "Sent course outline and price list via Zalo",
    "Explained the instalment plans; will discuss with family",
    "Asked about class size and the teacher's experience",
    "Prefers weekend classes; checked the timetable together",
    "Parent asked whether the course follows the school curriculum",
    "Booked the placement test for the weekend",
    "Followed up after the open day",
]
DROP_REASONS = ["Moved to another city", "Timetable clashes with school extra classes", "Family financial difficulty",
                "Health reasons", "Not satisfied with progress", "Changed to online self-study", "Busy with work shifts"]
CANCEL_REASONS = ["Changed mind before the start", "Found a class closer to home", "Timetable no longer fits",
                  "Family decided to postpone"]


def ascii_name(text: str) -> str:
    text = text.replace("Đ", "D").replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def add_months(d: D, n: int) -> D:
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    last = [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return D(y, m, min(d.day, last))


def month_end(d: D) -> D:
    return add_months(d.replace(day=1), 1) - ONE


def period(d: D) -> int:
    return d.year * 100 + d.month


@dataclass
class Learner:
    student_id: int
    name: str
    programme: str
    is_child: bool
    guardian_id: int | None = None
    guardian_name: str | None = None
    school_id: int | None = None


@dataclass
class Enrolment:
    enrollment_id: int
    learner: Learner
    class_id: int | None
    course: str
    owner: str               # employee code of the Learning Advisor
    profile: str             # PROMPT / LATE / DEFAULTER / PARTIAL
    plan: str
    extra: dict = field(default_factory=dict)


class Simulation:
    def __init__(self, conn: psycopg.Connection, as_of: D, seed: int, password: str):
        self.c = conn
        self.as_of = as_of
        self.start = add_months(as_of.replace(day=1), -12)
        self.rng = random.Random(seed)
        self.password = password
        self.agenda: dict[D, list] = defaultdict(list)
        self.seq = 0
        self.today = self.start
        self.emp: dict[str, int] = {}             # employee code -> employee_id
        self.role_ids: dict[tuple, int] = {}      # (employee code, role) -> current employee_role_id
        self.users: dict[str, str] = {}           # employee code -> username
        self.user_roles: dict[str, str] = {}
        self.courses: dict[str, dict] = {}
        self.rooms: dict[str, int] = {}
        self.vendors: dict[str, int] = {}
        self.levels: dict[tuple, int] = {}
        self.lane_classes: dict[str, list] = defaultdict(list)   # lane -> [(class_id, course, start, end)]
        self.class_info: dict[int, dict] = {}
        self.voucher_no = 0
        self.claim_no = 0
        self.asset_no = 0
        self.journal_no = 0
        self.closures: set[D] = set()
        self.stats = defaultdict(int)
        self.resign_date = as_of - dt.timedelta(days=2)

    # ------------------------------------------------------------------------------------------- database helpers
    def x(self, sql, params=None):
        return self.c.execute(sql, params)

    def val(self, sql, params=None):
        row = self.c.execute(sql, params).fetchone()
        return row[0] if row else None

    def rows(self, sql, params=None):
        return self.c.execute(sql, params).fetchall()

    def act(self, emp_code: str):
        """Work as the application user of this employee (audit trail: who did it, in which role)."""
        self.x("select set_config('ami.app_user', %s, true), set_config('ami.app_role', %s, true)",
               (self.users.get(emp_code, emp_code), self.user_roles.get(emp_code, "SYSTEM")))

    def at(self, day: D, order: int, fn, *args):
        if day < self.today:
            day = self.today
        if day > self.as_of:
            return
        self.seq += 1
        self.agenda[day].append((order, self.seq, fn, args))

    def pick(self, weighted):
        items, weights = zip(*weighted)
        return self.rng.choices(items, weights=weights)[0]

    def is_open_day(self, d: D) -> bool:
        return d not in self.closures

    # ------------------------------------------------------------------------------------------- main loop
    def run(self):
        t0 = time.time()
        self.x("create temp table sim_clock (real_ts timestamptz primary key, sim_ts timestamptz not null)")
        with self.c.transaction():
            self.set_day(self.start)
            self.act("system")
            self.setup()
        d = self.start
        while d <= self.as_of:
            self.today = d
            with self.c.transaction():
                self.set_day(d)
                self.daily_routine(d)
                while self.agenda.get(d):
                    items = sorted(self.agenda.pop(d), key=lambda e: (e[0], e[1]))
                    for order, _, fn, args in items:
                        fn(*args)
                self.nightly(d)
            d += ONE
        with self.c.transaction():
            self.finish()
        print(f"Simulated {self.start} .. {self.as_of} in {time.time() - t0:.0f}s", file=sys.stderr)
        for k in sorted(self.stats):
            print(f"  {k:<28} {self.stats[k]}", file=sys.stderr)

    def set_day(self, d: D):
        self.x("update ref.app_setting set setting_value = %s where setting_key = 'as_of_date'", (d.isoformat(),))
        self.x("insert into sim_clock values (now(), %s::timestamp at time zone 'Asia/Ho_Chi_Minh') on conflict do nothing",
               (dt.datetime.combine(d, dt.time(8, 0)),))

    # ------------------------------------------------------------------------------------------- go-live set-up
    def setup(self):
        S = self.start
        # reference data (prices, rates, discounts) was loaded by the build: date it to go-live
        self.x("""update app.audit_log set occurred_at = %s::timestamp at time zone 'Asia/Ho_Chi_Minh', app_user = 'system', db_role = 'SYSTEM'
                  where occurred_at < now()""", (dt.datetime.combine(S - ONE, dt.time(9, 0)),))
        self.x("select finance.ensure_periods(%s, %s)", (S, add_months(self.as_of, 14)))
        self.x("update finance.fiscal_period set status = 'CLOSED', closed_at = now() where period_end < %s", (S,))   # books open at go-live
        self.closures = {r[0] for r in self.rows("select closure_date from academic.closure_day")}
        for code, cid, prog, hps, spw, hours in self.rows(
                "select course_code, course_id, programme_code, default_hours_per_session, default_sessions_per_week, standard_hours from ref.course"):
            self.courses[code] = {"id": cid, "programme": prog, "hours": float(hours)}
        self.rooms = {n: i for n, i in self.rows("select room_name, room_id from academic.room")}
        self.levels = {(s, l): i for s, l, i in self.rows("select scale_code, level_code, level_id from ref.proficiency_level")}
        for name, level in EXTRA_SCHOOLS:
            self.x("insert into ref.school (school_name, school_level, city) values (%s, %s, 'Bac Lieu') on conflict do nothing", (name, level))
        self.schools = {n: i for n, i in self.rows("select school_name, school_id from ref.school")}
        self.partner_schools = {i for (i,) in self.rows("select school_id from ref.school where is_partner")}

        for code, name, short, gender, etype, cc, hired_m, roles, fixed, user in STAFF:
            hire = add_months(S, hired_m) if hired_m else S - dt.timedelta(days=self.rng.randint(20, 60))
            eid = self.val("""insert into hr.employee (employee_code, full_name, name_code, gender, employment_type,
                                  home_cost_center_code, hire_date, email, phone)
                              values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning employee_id""",
                           (code, name, short, gender, etype, cc, hire,
                            ascii_name(short).lower().replace(" ", ".") + "@ami-demo.example", self.fake_phone()))
            self.emp[code] = eid
            if user:
                self.users[code], self.user_roles[code] = user
        self.act("E003")
        for code, name, short, gender, etype, cc, hired_m, roles, fixed, user in STAFF:
            hire = self.val("select hire_date from hr.employee where employee_code = %s", (code,))
            for role, stage, rcc in roles:
                rid = self.add_role(code, role, stage, rcc, max(hire, S - dt.timedelta(days=60)))
                if fixed and role not in ("TEACHER_IELTS",):
                    self.x("insert into hr.employee_fixed_pay (employee_role_id, monthly_amount, effective_from) values (%s, %s, %s)",
                           (rid, fixed, max(hire, S - dt.timedelta(days=60))))
        # personal rate: the IELTS assistant was hired with an 8.0 band at an agreed rate
        self.x("""insert into hr.employee_rate_override (employee_role_id, hourly_rate, effective_from, reason, approved_by)
                  values (%s, 45000, %s, 'IELTS 8.0 - rate agreed at offer', %s)""",
               (self.role_ids[("E011", "AT_IELTS")], S - dt.timedelta(days=30), self.emp["E001"]))
        self.x("update finance.cost_center set manager_employee_id = %s where not is_academic", (self.emp["E001"],))
        self.x("update finance.cost_center set manager_employee_id = %s where is_academic", (self.emp["E004"],))
        for code, (username, role) in [(st[0], st[9]) for st in STAFF if st[9]]:
            self.x("""insert into app.app_user (username, full_name, role_code, employee_id, password_hash)
                      select %s, full_name, %s, employee_id, extensions.crypt(%s, extensions.gen_salt('bf', 8))
                      from hr.employee where employee_code = %s""", (username, role, self.password, code))
        self.act("E002")
        for name, vtype, tax, acc in [
            ("Landlord - campus premises (individual)", "INDIVIDUAL", None, "E7.012"),
            ("Provincial power company", "UTILITY", "0100000101", "E7.007"),
            ("City water supply", "UTILITY", "0100000102", "E7.007"),
            ("Telecom provider", "COMPANY", "0100000103", "E7.016"),
            ("Online ads platform", "MARKETPLACE", None, "E8.036"),
            ("Book distributor", "COMPANY", "0100000104", "E8.001"),
            ("Electronics store", "COMPANY", "0100000105", "E3.001"),
            ("Air-conditioning supplier", "COMPANY", "0100000106", "E3.002"),
            ("Interior fit-out contractor", "COMPANY", "0100000107", "E3.003"),
            ("Cleaning service", "COMPANY", "0100000108", "E7.015"),
            ("Accounting firm", "COMPANY", "0100000109", "E7.004"),
            ("Print shop", "COMPANY", "0100000110", "E8.006"),
            ("Online marketplace", "MARKETPLACE", None, "E2.002"),
            ("Bank", "COMPANY", "0100000111", "E7.011"),
        ]:
            self.vendors[name] = self.val("""insert into finance.vendor (vendor_name, vendor_type, tax_code, default_account_code)
                                             values (%s, %s, %s, %s) returning vendor_id""", (name, vtype, tax, acc))
        # opening investment: fit-out, projectors, air conditioning (capitalised and depreciated)
        self.capex(S + dt.timedelta(days=2), "Interior fit-out contractor", "Classroom fit-out and reception desk", 68000000, "i10", "E3.003", "E3.006", 60)
        for room in ("Room 101", "Room 102", "Room 201"):
            self.capex(S + dt.timedelta(days=4), "Electronics store", f"Projector and speakers - {room}", 9500000, "i10", "E3.001", "E3.004", 36)
            self.capex(S + dt.timedelta(days=4), "Air-conditioning supplier", f"Air conditioner - {room}", 11500000, "i10", "E3.002", "E3.005", 60)
        # plan the first class of every lane and the recurring calendar
        for lane in LANES:
            key, months_after = lane[0], lane[11]
            first_start = add_months(S, months_after) + dt.timedelta(days=lane[10])
            self.at(max(S, first_start - dt.timedelta(days=42)), 10, self.open_lane_class, lane, 0, first_start)
        d = S
        while d <= self.as_of:
            self.at(d.replace(day=min(5, month_end(d).day)), 60, self.monthly_expenses, d.replace(day=1))
            d = add_months(d.replace(day=1), 1)
        self.at(add_months(S, 2), 11, self.hr_confirm_probation)
        self.at(add_months(S, 6).replace(day=1) - dt.timedelta(days=12), 60, self.price_increase, add_months(S, 6).replace(day=1))
        self.at(add_months(S, 7).replace(day=1) - dt.timedelta(days=10), 11, self.rate_increase, add_months(S, 7).replace(day=1))
        self.at(add_months(S, 6) + dt.timedelta(days=9), 60, self.capex_laptop, "Laptop for the reception desk")
        self.at(self.resign_date, 11, self.teacher_resigns)
        self.plan_today_scenarios()

    def add_role(self, emp_code, role, stage, cc, start):
        sal = self.val("select salary_code from ref.salary_code where role_code = %s and contract_stage_code = %s", (role, stage))
        suffix = self.val("select hr_code_suffix from ref.staff_role where role_code = %s", (role,))
        name = self.val("select full_name from hr.employee where employee_code = %s", (emp_code,))
        parts = ascii_name(name).upper().split()
        base = parts[-1] + "".join(p[0] for p in parts[:-1]) + suffix
        n = self.val("select count(*) from hr.employee_role where hr_code like %s", (base + "%",)) + 1
        rid = self.val("""insert into hr.employee_role (hr_code, employee_id, role_code, contract_stage_code, salary_code,
                                                        cost_center_code, effective_from)
                          values (%s, %s, %s, %s, %s, %s, %s) returning employee_role_id""",
                       (f"{base}{n:03d}", self.emp[emp_code], role, stage, sal, cc, start))
        self.role_ids[(emp_code, role)] = rid
        return rid

    def fake_phone(self):
        return f"0100 {self.rng.randint(100, 999)} {self.rng.randint(100, 999)}"

    # ------------------------------------------------------------------------------------------- HR events
    def hr_confirm_probation(self):
        """Learning Advisor Khoa passes probation: a new HR code at the official pay rate from today."""
        self.act("E003")
        old = self.role_ids[("E006", "LA")]
        self.x("update hr.employee_role set effective_to = %s where employee_role_id = %s", (self.today, old))
        self.add_role("E006", "LA", "OFFICIAL", "921012", self.today)
        self.stats["hr: probation passed"] += 1

    def rate_increase(self, effective: D):
        self.act("E003")
        self.x("update ref.salary_rate set effective_to = %s where salary_code = 'S/L.006' and effective_to is null", (effective,))
        self.x("insert into ref.salary_rate (salary_code, hourly_rate, effective_from) values ('S/L.006', 32000, %s)", (effective,))

    def teacher_resigns(self):
        """A Communication teacher leaves: running classes are handed over, his next class has no teacher yet (ACA-03)."""
        d = self.today
        self.act("E003")
        rid = self.role_ids[("E008", "TEACHER_AE_COMM")]
        self.x("update hr.employee set end_date = %s where employee_code = 'E008'", (d,))
        self.act("E004")
        for cid, start, lane in self.rows("""select c.class_id, c.start_date, c.notes from academic.class_staff_assignment a
                                             join academic.class c using (class_id)
                                             where a.employee_role_id = %s and a.effective_to is null
                                               and c.lifecycle_status in ('OPEN','RUNNING','PLANNED') order by c.class_id""", (rid,)):
            key = (lane or "").rsplit(" ", 1)[-1]
            cover = COVER.get(key, "E007")
            if start < d:
                self.x("update academic.class_staff_assignment set effective_to = %s where class_id = %s and employee_role_id = %s",
                       (d, cid, rid))
                self.x("""insert into academic.class_staff_assignment (class_id, employee_role_id, assignment_role, effective_from)
                          values (%s, %s, 'LEAD_TEACHER', %s)""", (cid, self.role_ids[(cover, "TEACHER_AE_COMM")], d))
            else:
                # >> to do for the Academic Manager: the next class of lane E has no teacher yet (control ACA-03)
                self.x("delete from academic.class_staff_assignment where class_id = %s and employee_role_id = %s", (cid, rid))
                if key != "E":
                    self.x("""insert into academic.class_staff_assignment (class_id, employee_role_id, assignment_role, effective_from)
                              values (%s, %s, 'LEAD_TEACHER', %s)""", (cid, self.role_ids[(cover, "TEACHER_AE_COMM")], start))
        self.act("E003")
        self.x("update hr.employee_role set effective_to = %s where employee_role_id = %s", (d, rid))

    # ------------------------------------------------------------------------------------------- academic
    def teacher_on(self, code: str | None, d: D):
        if code is None:
            return None
        if code == "E008" and self.today >= self.resign_date:     # has left the centre
            return None
        role = "TEACHER_IELTS" if code in ("E004", "E009") else ("AT_IELTS" if code == "E011" else
                                                                 "TA_AE_COMM" if code == "E010" else "TEACHER_AE_COMM")
        return self.role_ids[(code, role)]

    def next_start(self, d: D, weekdays) -> D:
        while d.isoweekday() not in weekdays or not self.is_open_day(d):
            d += ONE
        return d

    def open_lane_class(self, lane, idx, start: D):
        key, room, days, t0, t1, mode, cap, chain, teacher, assistant, _, _ = lane
        if idx >= len(chain):
            return
        start = self.next_start(start, days)
        course = chain[idx]
        co = self.courses[course]
        pattern = json.dumps([{"weekday": wd, "start": t0, "end": t1} for wd in days])
        while self.val("select count(*) from academic.class where class_code = academic.make_class_code(%s::smallint, %s)", (co["id"], start)):
            start = self.next_start(start + ONE, days)        # another lane starts the same course that day
        t_role = self.teacher_on(teacher, start)
        if t_role is None:                               # lane teacher has left; a colleague covers
            t_role = self.teacher_on(COVER.get(key, "E007"), start)
        self.act("E004")
        cid = self.val("""select academic.open_class(%s::smallint, %s, %s, %s::smallint, %s::smallint, %s::jsonb, %s, %s,
                                                     %s::smallint, null, %s)""",
                       (co["id"], mode, start, cap, self.rooms[room], pattern, t_role, self.teacher_on(assistant, start),
                        len(self.lane_classes[key]) + 1, f"Timetable lane {key}"))
        end = self.val("select planned_end_date from academic.class where class_id = %s", (cid,))
        prev = self.lane_classes[key][-1] if self.lane_classes[key] else None
        self.lane_classes[key].append((cid, course, start, end))
        self.class_info[cid] = {"course": course, "programme": co["programme"], "start": start, "end": end, "cap": cap,
                                "mode": mode, "lane": key, "opened": self.today}
        self.stats["classes opened"] += 1
        self.at(start - dt.timedelta(days=3), 60, self.buy_books, cid)
        self.at(self.today, 31, self.place_waitlisted, cid)
        # demand: learners continuing from the previous level, then new learners
        target = max(3, round(cap * self.rng.uniform(0.8, 1.0)))
        continuing = 0
        if key == "H" and idx == 1:                      # this online class will not reach the minimum size
            target, prev = 3, None
            self.at(start - dt.timedelta(days=5), 10, self.cancel_small_class, cid)
        if prev:
            rate = CONTINUE_RATE[co["programme"]]
            continuing = round(target * min(0.6, rate))
            self.at(max(self.today + ONE, prev[3] - dt.timedelta(days=12)), 30, self.continue_learners, prev[0], cid, rate)
        for _ in range(max(0, target - continuing)):
            lead_window = (start - self.today).days
            if self.rng.random() < 0.1:
                enrol = start + dt.timedelta(days=self.rng.randint(0, 10))       # late joiner
            else:
                enrol = start - dt.timedelta(days=int(lead_window * self.rng.betavariate(1.3, 2.6)))
            enrol = max(enrol, self.today + dt.timedelta(days=3))
            self.plan_new_learner(cid, enrol)
        # the next class of the lane starts one or two weeks after this one ends
        nxt = end + dt.timedelta(days=self.rng.randint(7, 15))
        self.at(nxt - dt.timedelta(days=self.rng.randint(35, 45)), 10, self.open_lane_class, lane, idx + 1, nxt)

    def place_waitlisted(self, cid):
        """Learners waiting for this course are offered the new class first (first come, first served)."""
        info = self.class_info[cid]
        for eid, owner in self.rows("""select e.enrollment_id, s.employee_code from billing.enrollment e
                                       join hr.employee s on s.employee_id = e.sales_owner_employee_id
                                       where e.status_code = 'WAITLISTED' and e.class_id is null and e.notes is null
                                         and e.course_id = %s and e.delivery_mode_code = %s order by e.enrolled_on, e.enrollment_id""",
                                    (self.courses[info["course"]]["id"], info["mode"])):
            if self.seats_left(cid) <= 0:
                break
            owner = "E005" if owner == "E008" else owner
            self.act(owner)
            self.x("select billing.assign_class(%s, %s, %s)", (eid, cid, self.emp[owner]))
            self.stats["waiting list placed"] += 1

    def cancel_small_class(self, cid):
        n = self.val("select count(*) from billing.enrollment where class_id = %s and status_code in ('REGISTERED','ACTIVE')", (cid,))
        if n >= 5:
            return
        self.act("E004")
        self.x("select academic.cancel_class(%s, %s)", (cid, f"Only {n} learners registered (minimum 5)"))
        self.stats["classes cancelled"] += 1
        # Sales offers another class of the same course or a full refund
        for eid, sid, course_id, owner in self.rows("""select e.enrollment_id, e.student_id, e.course_id, s.employee_code
                                                       from billing.enrollment e join hr.employee s on s.employee_id = e.sales_owner_employee_id
                                                       where e.status_code = 'WAITLISTED' and e.class_id is null
                                                         and e.status_changed_on = %s order by e.enrollment_id""", (self.today,)):
            alt = self.val("""select c.class_id from academic.class c
                              where c.course_id = %s and c.lifecycle_status in ('OPEN','RUNNING') and c.class_id <> %s
                                and c.start_date between %s and %s
                                and (select count(*) from billing.enrollment x where x.class_id = c.class_id
                                       and x.status_code in ('WAITLISTED','REGISTERED','ACTIVE')) < c.capacity
                              order by c.start_date, c.class_id limit 1""",
                           (course_id, cid, self.today - dt.timedelta(days=14), self.today + dt.timedelta(days=30)))
            self.act(owner)
            if alt and self.rng.random() < 0.7:
                self.x("select billing.assign_class(%s, %s, %s)", (eid, alt, self.emp[owner]))
                self.stats["moved to another class"] += 1
            else:
                self.x("select billing.change_enrollment_status(%s, 'CANCELLED', %s, 'Class cancelled by the centre')", (eid, self.today))
                paid = self.val("select collected - refunded from rpt.v_enrollment_balance where enrollment_id = %s", (eid,))
                if paid and paid > 0:
                    self.at(self.today + dt.timedelta(days=2), 61, self.refund, eid, int(paid), "Class cancelled by the centre - full refund", False)

    def buy_books(self, cid):
        info = self.class_info[cid]
        if info["programme"] == "PE" or self.val("select lifecycle_status from academic.class where class_id = %s", (cid,)) == "CANCELLED":
            return
        n = self.val("select count(*) from billing.enrollment where class_id = %s and status_code in ('REGISTERED','ACTIVE')", (cid,))
        if n == 0:
            return
        price = {"AE": 145000, "COMM": 165000, "IELTS": 210000}[info["programme"]]
        cc = {"AE": "921016", "COMM": "921015", "IELTS": "921017"}[info["programme"]]
        code = self.val("select class_code from academic.class where class_id = %s", (cid,))
        self.voucher("Book distributor", [(f"Student books {info['course']} x {n + 1}", (n + 1) * price, "i0", "E8.001", cc, cid, period(self.today))],
                     requested="E004", invoice=True, method="BANK_TRANSFER", note=f"Books for {code}")

    def confirm_sessions(self, upto: D, everything=False):
        """Academic Manager confirms delivered sessions (hours for payroll); a few were cancelled and get a make-up."""
        self.act("E004")
        for sid, cid, sdate, st, et, room in self.rows("""
                select s.session_id, s.class_id, s.session_date, s.start_time, s.end_time, s.room_id
                from academic.class_session s join academic.class c using (class_id)
                where s.session_date <= %s and c.lifecycle_status <> 'CANCELLED'
                  and (s.status = 'SCHEDULED' or (s.status = 'MAKE_UP' and not exists
                       (select 1 from academic.session_staff ss where ss.session_id = s.session_id)))
                order by s.session_date, s.start_time, s.session_id""", (upto,)):
            if self.rng.random() < 0.015 and sdate < upto - dt.timedelta(days=2):
                self.x("select academic.confirm_session(%s, false, %s)", (sid, self.emp["E004"]))
                mk = sdate + dt.timedelta(days=14)
                while not self.is_open_day(mk):
                    mk += ONE
                if mk > self.today and self.val("select lifecycle_status from academic.class where class_id = %s", (cid,)) in ("OPEN", "RUNNING"):
                    self.x("select academic.add_make_up_session(%s, %s, %s, %s)", (cid, mk, st, et))
                self.stats["sessions cancelled (make-up)"] += 1
            else:
                self.x("select academic.confirm_session(%s, true, %s)", (sid, self.emp["E004"]))
                self.stats["sessions confirmed"] += 1

    # ------------------------------------------------------------------------------------------- sales: learners and leads
    def new_person(self, programme: str, course: str):
        gender = self.rng.choice(["FEMALE", "MALE"])
        fam = self.rng.choice(FAMILY)
        mid = self.rng.choice(MIDDLE_F if gender == "FEMALE" else MIDDLE_M)
        given = self.rng.choice(GIVEN_F if gender == "FEMALE" else GIVEN_M)
        name = f"{fam} {mid} {given}"
        y = self.today.year
        if programme == "AE":
            age = self.rng.randint(6, 12); grade = f"Grade {max(1, age - 5)}"
            school = self.rng.choice(["Riverside Primary School", "Kim Dong Primary School", "Sunrise Primary School", "Lotus Lower Secondary School"])
        elif programme == "PE":
            g = {"G6": 6, "G9": 9, "G12": 12}[course]; age = g + 5; grade = f"Grade {g}"
            school = self.rng.choice(["Lotus Lower Secondary School", "Harbour Lower Secondary School"] if g < 10 else ["City High School", "Lakeside High School"])
        elif programme == "IELTS":
            age = self.rng.randint(15, 23)
            grade = f"Grade {age - 5}" if age <= 17 else "University"
            school = self.rng.choice(["City High School", "High School for the Gifted", "Lakeside High School"]) if age <= 17 else \
                self.rng.choice(["Bac Lieu University", "Bac Lieu College"])
        else:
            age = self.rng.randint(17, 34)
            grade = "University" if age <= 22 else "Working"
            school = self.rng.choice(["Bac Lieu University", "Bac Lieu College"]) if age <= 22 else None
        dob = D(y - age, self.rng.randint(1, 12), self.rng.randint(1, 28))
        child = age < 16
        email = None if child else f"{ascii_name(given).lower()}.{ascii_name(fam).lower()}{self.rng.randint(10, 99)}@example.com"
        sid = self.val("""insert into crm.student (full_name, gender, date_of_birth, phone, email, school_id, grade_label, first_contact_date)
                          values (%s, %s, %s, %s, %s, %s, %s, %s) returning student_id""",
                       (name, gender, dob, None if child else self.fake_phone(), email, self.schools.get(school), grade, self.today))
        lr = Learner(sid, name, programme, child, school_id=self.schools.get(school))
        if child:
            pg = self.rng.random() < 0.68
            pname = f"{fam} {self.rng.choice(MIDDLE_F if pg else MIDDLE_M)} {self.rng.choice(GIVEN_F if pg else GIVEN_M)}"
            gid = self.val("insert into crm.guardian (full_name, phone) values (%s, %s) returning guardian_id", (pname, self.fake_phone()))
            self.x("""insert into crm.student_guardian (student_id, guardian_id, relationship_code, is_primary_contact, is_payer)
                      values (%s, %s, %s, true, true)""", (sid, gid, "MOTHER" if pg else "FATHER"))
            lr.guardian_id, lr.guardian_name = gid, pname
        return lr

    def owner_for(self, d: D) -> str:
        return "E005" if self.rng.random() < 0.56 else "E006"

    def plan_new_learner(self, cid: int, enrol: D, lost: bool = False):
        info = self.class_info[cid]
        lead_day = enrol - dt.timedelta(days=self.rng.randint(4, 21))
        lead_day = max(lead_day, self.today)
        ctx = {"class_id": cid, "programme": info["programme"], "course": info["course"], "owner": self.owner_for(lead_day),
               "enrol": max(enrol, lead_day + dt.timedelta(days=2))}
        test_day = lead_day + dt.timedelta(days=max(1, min(7, (ctx["enrol"] - lead_day).days - 1)))
        self.at(lead_day, 20, self.create_lead, ctx)
        self.at(lead_day + dt.timedelta(days=1), 21, self.book_test, ctx, test_day)
        self.at(test_day, 22, self.complete_test, ctx)
        self.at(ctx["enrol"], 30, self.enrol_new, ctx)
        # for every learner who enrols, about one other inquiry does not convert
        if self.rng.random() < 1.05:
            lctx = dict(ctx, owner=self.owner_for(lead_day))
            self.at(lead_day + dt.timedelta(days=self.rng.randint(-6, 6)), 20, self.lost_lead, lctx)

    def create_lead(self, ctx):
        self.act(ctx["owner"])
        lr = self.new_person(ctx["programme"], ctx["course"])
        channel = self.pick(CHANNELS[ctx["programme"]])
        ctx["learner"] = lr
        ctx["lead_id"] = self.val("""insert into crm.lead (student_id, lead_date, owner_employee_id, channel_code, programme_code,
                                         delivery_mode_code, stage_code, next_follow_up_on, created_at)
                                     values (%s, %s, %s, %s, %s, %s, 'NEW', %s, now()) returning lead_id""",
                                  (lr.student_id, self.today, self.emp[ctx["owner"]], channel, ctx["programme"],
                                   self.class_info[ctx["class_id"]]["mode"], self.today + ONE))
        self.stats["leads"] += 1

    def book_test(self, ctx, test_day: D):
        if "lead_id" not in ctx:
            return
        self.act(ctx["owner"])
        self.x("""insert into crm.lead_activity (lead_id, activity_type, activity_at, employee_id, outcome_code, note)
                  values (%s, %s, %s, %s, 'PENDING', %s)""",
               (ctx["lead_id"], self.rng.choice(["CALL", "CHAT"]), dt.datetime.combine(self.today, dt.time(self.rng.randint(9, 20), 0)),
                self.emp[ctx["owner"]], self.rng.choice(CALL_NOTES)))
        ctx["test_id"] = self.val("""insert into crm.placement_test (lead_id, test_type, scheduled_at, status)
                                     values (%s, %s, %s, 'BOOKED') returning test_id""",
                                  (ctx["lead_id"], TEST_TYPE[ctx["programme"]], dt.datetime.combine(test_day, dt.time(9, 30))))
        self.x("update crm.lead set stage_code = 'TEST_BOOKED', qualification_code = 'HIGH_POTENTIAL', next_follow_up_on = %s where lead_id = %s",
               (test_day, ctx["lead_id"]))

    def complete_test(self, ctx):
        if "test_id" not in ctx:
            return
        self.act("E004")
        if ctx["programme"] == "IELTS":
            lvl = self.levels[("IELTS", self.rng.choice(ENTRY_BAND[ctx["course"]]))]
        else:
            lvl = self.levels[("CEFR", self.rng.choice(CEFR[1:6]))]
        self.x("""update crm.placement_test set status = 'COMPLETED', assessed_by = %s, overall_level_id = %s,
                  completed_at = scheduled_at + interval '90 minutes' where test_id = %s""", (self.emp["E004"], lvl, ctx["test_id"]))
        if ctx["programme"] == "IELTS":
            for skill in ("READING", "LISTENING", "WRITING", "SPEAKING"):
                self.x("insert into crm.placement_test_score (test_id, skill_code, level_id) values (%s, %s, %s)",
                       (ctx["test_id"], skill, lvl))
        self.act(ctx["owner"])
        self.x("""update crm.lead set stage_code = 'TESTED', recommended_course_id = %s, consultation_outcome_code = 'PENDING',
                  next_follow_up_on = %s where lead_id = %s""",
               (self.courses[ctx["course"]]["id"], self.today + ONE, ctx["lead_id"]))
        self.stats["placement tests"] += 1

    def lost_lead(self, ctx):
        self.act(ctx["owner"])
        lr = self.new_person(ctx["programme"], ctx["course"])
        channel = self.pick(CHANNELS[ctx["programme"]])
        lead = self.val("""insert into crm.lead (student_id, lead_date, owner_employee_id, channel_code, programme_code, stage_code,
                                                 next_follow_up_on, created_at)
                           values (%s, %s, %s, %s, %s, 'NEW', %s, now()) returning lead_id""",
                        (lr.student_id, self.today, self.emp[ctx["owner"]], channel, ctx["programme"], self.today + ONE))
        self.stats["leads"] += 1
        path = self.pick([("NO_RESPONSE", 35), ("DECLINED", 20), ("NO_SHOW", 15), ("TESTED", 30)])
        close = self.today + dt.timedelta(days=self.rng.randint(3, 16))
        self.at(self.today + ONE, 21, self.progress_lost_lead, lead, ctx["owner"], path, ctx["programme"])
        self.at(close, 23, self.close_lost_lead, lead, ctx["owner"], path)

    def progress_lost_lead(self, lead, owner, path, programme):
        self.act(owner)
        outcome = {"NO_RESPONSE": self.rng.choice(["NO_ANSWER", "PHONE_OFF"])}.get(path, "PENDING")
        self.x("""insert into crm.lead_activity (lead_id, activity_type, activity_at, employee_id, outcome_code, note)
                  values (%s, 'CALL', %s, %s, %s, %s)""",
               (lead, dt.datetime.combine(self.today, dt.time(self.rng.randint(9, 20))), self.emp[owner], outcome,
                "No answer, will try again" if path == "NO_RESPONSE" else self.rng.choice(CALL_NOTES)))
        stage = {"NO_RESPONSE": "CONTACTED_NO_RESPONSE", "DECLINED": "DECLINED_APPOINTMENT", "NO_SHOW": "TEST_BOOKED", "TESTED": "TEST_BOOKED"}[path]
        self.x("update crm.lead set stage_code = %s, next_follow_up_on = %s where lead_id = %s", (stage, self.today + dt.timedelta(days=3), lead))
        if path in ("NO_SHOW", "TESTED"):
            tday = self.today + dt.timedelta(days=self.rng.randint(1, 4))
            tid = self.val("insert into crm.placement_test (lead_id, test_type, scheduled_at) values (%s, %s, %s) returning test_id",
                           (lead, TEST_TYPE[programme], dt.datetime.combine(tday, dt.time(9, 30))))
            self.at(tday, 22, self.finish_lost_test, lead, tid, path, programme)

    def finish_lost_test(self, lead, tid, path, programme):
        self.act("E004")
        if path == "NO_SHOW":
            self.x("update crm.placement_test set status = 'NO_SHOW' where test_id = %s", (tid,))
            self.x("update crm.lead set stage_code = 'NO_SHOW' where lead_id = %s", (lead,))
            return
        lvl = self.levels[("IELTS", "4.5")] if programme == "IELTS" else self.levels[("CEFR", self.rng.choice(CEFR[1:5]))]
        self.x("""update crm.placement_test set status = 'COMPLETED', assessed_by = %s, overall_level_id = %s,
                  completed_at = scheduled_at + interval '90 minutes' where test_id = %s""", (self.emp["E004"], lvl, tid))
        self.x("update crm.lead set stage_code = 'TESTED' where lead_id = %s", (lead,))

    def close_lost_lead(self, lead, owner, path):
        self.act(owner)
        outcome, reason = {
            "NO_RESPONSE": ("NO_ANSWER", "NO_NEED"),
            "DECLINED": self.rng.choice([("PRICE_NOT_SUITABLE", "PRICE"), ("NO_SUITABLE_TIMESLOT", "SCHEDULE"), ("LOCATION_TOO_FAR", "OTHER")]),
            "NO_SHOW": ("NO_NEED_YET", "NO_NEED"),
            "TESTED": self.rng.choice([("PRICE_NOT_SUITABLE", "PRICE"), ("NO_SUITABLE_TIMESLOT", "SCHEDULE"),
                                       ("PROGRAMME_NOT_SUITABLE", "PROGRAMME_FIT"), ("NO_NEED_YET", "NO_NEED")]),
        }[path]
        qual = "NOT_A_PROSPECT" if path in ("DECLINED", "NO_RESPONSE") else "LOW_POTENTIAL"
        self.x("""update crm.lead set qualification_code = %s, consultation_outcome_code = %s, lost_reason_code = %s,
                  closed_on = %s, next_follow_up_on = null where lead_id = %s""", (qual, outcome, reason, self.today, lead))

    # ------------------------------------------------------------------------------------------- sales: enrolment and money
    def seats_left(self, cid):
        return self.val("""select c.capacity - (select count(*) from billing.enrollment e where e.class_id = c.class_id
                                                  and e.status_code in ('WAITLISTED','REGISTERED','ACTIVE'))
                           from academic.class c where c.class_id = %s""", (cid,))

    def enrol_new(self, ctx):
        if "lead_id" not in ctx:
            return
        cid = ctx["class_id"]
        info = self.class_info[cid]
        if self.val("select lifecycle_status from academic.class where class_id = %s", (cid,)) in ("CANCELLED", "COMPLETED") \
                or self.seats_left(cid) <= 0 or self.today > info["start"] + dt.timedelta(days=14):
            # class full / gone: another class of the same course, else the waiting list for the next intake
            alt = self.val("""select c.class_id from academic.class c
                              where c.course_id = %s and c.delivery_mode_code = %s and c.lifecycle_status in ('OPEN','RUNNING')
                                and c.start_date between %s and %s order by c.start_date, c.class_id limit 1""",
                           (self.courses[info["course"]]["id"], info["mode"], self.today - dt.timedelta(days=10), self.today + dt.timedelta(days=30)))
            if alt and self.seats_left(alt) > 0:
                self.do_enrol(ctx["learner"], alt, info["course"], ctx["owner"], info["mode"], ctx["lead_id"])
            elif self.rng.random() < 0.3:
                self.do_enrol(ctx["learner"], None, info["course"], ctx["owner"], info["mode"], ctx["lead_id"])
            else:                                        # no seat and no other class that suits: the lead is lost
                self.act(ctx["owner"])
                self.x("""update crm.lead set qualification_code = 'LOW_POTENTIAL', consultation_outcome_code = 'NO_SUITABLE_TIMESLOT',
                          lost_reason_code = 'SCHEDULE', lost_reason_note = 'Class full; next intake did not suit', closed_on = %s,
                          next_follow_up_on = null where lead_id = %s""", (self.today, ctx["lead_id"]))
            return
        self.do_enrol(ctx["learner"], cid, info["course"], ctx["owner"], info["mode"], ctx["lead_id"])

    def do_enrol(self, lr: Learner, cid, course, owner, mode, lead_id=None, returning=False, extra_discounts=(), plan=None, notes=None):
        programme = self.courses[course]["programme"]
        start = self.class_info[cid]["start"] if cid else None
        plan = plan or self.pick(PLANS[programme])
        discounts = list(extra_discounts)
        if returning:
            discounts.append("RETURNING_5")
        if start and (start - self.today).days >= 21 and self.rng.random() < 0.7:
            discounts.append("EARLY_BIRD_10")
        if programme in ("IELTS", "PE") and lr.school_id in self.partner_schools and self.rng.random() < 0.45:
            discounts.append("PARTNER_SCHOOL_30")
        elif not returning and self.rng.random() < 0.08:
            discounts.append("SALES_TACTIC_5")
        deposit = 500000 if (start and (start - self.today).days >= 7 and self.rng.random() < 0.55) else None
        target = None
        if programme == "IELTS":
            target = self.levels[("IELTS", TARGET_LEVEL[course])]
        elif programme in ("AE", "COMM"):
            target = self.levels[("CEFR", self.rng.choice(["A2", "A2+", "B1-"]))]
        self.act(owner)
        eid = self.val("""select billing.enrol(%s, %s::smallint, %s, %s, %s, %s, %s, %s, %s::text[], null, %s, %s::smallint, %s,
                                               %s)""",
                       (lr.student_id, self.courses[course]["id"], mode, cid, plan, self.today, self.emp[owner], lead_id,
                        discounts, deposit, target, notes, f"https://drive.example/ami/enrolment-forms/{lr.student_id}"))
        if lead_id:
            self.x("""insert into crm.lead_activity (lead_id, activity_type, activity_at, employee_id, outcome_code, note)
                      values (%s, 'MEETING', %s, %s, 'SUCCESS', 'Enrolment form signed at the centre')""",
                   (lead_id, dt.datetime.combine(self.today, dt.time(17, 30)), self.emp[owner]))
        self.stats["enrolments"] += 1
        profile = self.pick([("PROMPT", 62), ("LATE", 24), ("PARTIAL", 7), ("DEFAULTER", 7)])
        en = Enrolment(eid, lr, cid, course, owner, profile, plan)
        if self.val("select count(*) from billing.enrollment_discount where enrollment_id = %s and approval_status = 'PENDING'", (eid,)):
            self.at(self.today + dt.timedelta(days=self.rng.randint(1, 3)), 15, self.decide_discount, en)
        self.plan_payments(en)
        self.plan_life_events(en)
        return en

    def plan_payments(self, en: Enrolment):
        lines = self.rows("select seq, line_type, due_date, amount_due from billing.payment_schedule where enrollment_id = %s order by due_date, seq",
                          (en.enrollment_id,))
        paid_lines = 0
        for seq, ltype, due, amount in lines:
            if ltype == "DEPOSIT":
                self.at(self.today, 40, self.pay, en, "line")
                continue
            if en.profile == "DEFAULTER" and paid_lines >= 1:
                if self.rng.random() < 0.6:                  # reminders work in the end: paid two to three months late
                    self.at(due + dt.timedelta(days=self.rng.randint(35, 95)), 40, self.pay, en, "line")
                continue
            if en.plan == "FULL" and self.rng.random() < 0.55:
                day = self.today
            elif en.profile in ("PROMPT", "PARTIAL"):
                day = due - dt.timedelta(days=self.rng.randint(0, 4))
            else:
                day = due + dt.timedelta(days=self.rng.randint(3, 26))
            day = max(day, self.today)
            if en.profile == "PARTIAL" and self.rng.random() < 0.6:
                self.at(day, 40, self.pay, en, "half")
                self.at(day + dt.timedelta(days=self.rng.randint(6, 18)), 40, self.pay, en, "line")
            else:
                self.at(day, 40, self.pay, en, "line")
            paid_lines += 1

    def pay(self, en: Enrolment, how: str):
        st = self.val("select status_code from billing.enrollment where enrollment_id = %s", (en.enrollment_id,))
        if st in ("DROPPED", "CANCELLED", "DEFERRED"):
            return
        open_amt = self.val("""select remaining from rpt.v_schedule_line_status where enrollment_id = %s and remaining > 0
                               order by due_date, seq limit 1""", (en.enrollment_id,))
        if not open_amt:
            return
        amount = int(open_amt)
        if how == "half":
            amount = int(round(amount / 2, -3))
        collector = en.owner if self.rng.random() < 0.75 else ("E006" if en.owner == "E005" else "E005")
        method = self.pick([("CASH", 50), ("BANK_TRANSFER", 45), ("CARD", 5)] if en.learner.is_child else
                           [("CASH", 35), ("BANK_TRANSFER", 60), ("CARD", 5)])
        self.act(collector)
        payer = en.learner.guardian_name or en.learner.name
        rid = self.val("select billing.record_receipt(%s, %s, %s, %s, %s, %s, %s, %s)",
                       (en.learner.student_id, en.enrollment_id, self.today, amount, method, self.emp[collector], payer, en.learner.guardian_id))
        self.stats["receipts"] += 1
        if self.rng.random() < 0.012 and self.today < self.as_of - dt.timedelta(days=1):
            self.at(self.today + ONE, 41, self.void_and_reissue, rid, collector)

    def void_and_reissue(self, rid, collector):
        """A receipt keyed with the wrong payment method is voided (Finance approves) and issued again."""
        r = self.c.execute("select receipt_date, student_id, enrollment_id, amount, payment_method_code, payer_name, payer_guardian_id from billing.receipt where receipt_id = %s", (rid,)).fetchone()
        self.act(collector)
        self.x("select billing.request_receipt_void(%s, %s, %s)", (rid, self.emp[collector], "Wrong payment method keyed"))
        self.act("E002")
        self.x("select billing.decide_receipt_void(%s, true, %s)", (rid, self.emp["E002"]))
        self.act(collector)
        method = "BANK_TRANSFER" if r[4] == "CASH" else "CASH"
        self.x("select billing.record_receipt(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
               (r[1], r[2], r[0], r[3], method, self.emp[collector], r[5], r[6], "Re-issued after void"))
        self.stats["receipts voided"] += 1

    def decide_discount(self, en: Enrolment):
        self.act("E002")
        for seq, code in self.rows("select seq, discount_code from billing.enrollment_discount where enrollment_id = %s and approval_status = 'PENDING' order by seq desc", (en.enrollment_id,)):
            ok = code != "PARTNER_SCHOOL_30" or self.rng.random() < 0.85
            self.x("select billing.decide_discount(%s, %s::smallint, %s, %s, %s)",
                   (en.enrollment_id, seq, ok, self.emp["E002"], "Partner-school letter checked" if ok else "No partner-school confirmation"))
            self.stats["discounts approved" if ok else "discounts rejected"] += 1

    def plan_life_events(self, en: Enrolment):
        if not en.class_id:
            return
        info = self.class_info[en.class_id]
        length = (info["end"] - info["start"]).days
        r = self.rng.random()
        if (info["start"] - self.today).days >= 10 and r < 0.04:
            self.at(info["start"] - dt.timedelta(days=self.rng.randint(1, 6)), 35, self.cancel_enrolment, en)
        elif (en.profile == "DEFAULTER" and r < 0.55) or r < 0.045:
            self.at(info["start"] + dt.timedelta(days=int(length * self.rng.uniform(0.25, 0.7))), 35, self.drop_out, en)
        elif r < 0.065:
            self.at(info["start"] + dt.timedelta(days=int(length * self.rng.uniform(0.1, 0.35))), 35, self.defer, en)

    def cancel_enrolment(self, en: Enrolment):
        if self.val("select status_code from billing.enrollment where enrollment_id = %s", (en.enrollment_id,)) != "REGISTERED":
            return
        self.act(en.owner)
        self.x("select billing.change_enrollment_status(%s, 'CANCELLED', %s, %s)", (en.enrollment_id, self.today, self.rng.choice(CANCEL_REASONS)))
        self.stats["cancellations"] += 1
        kept = self.val("select collected - refunded from rpt.v_enrollment_balance where enrollment_id = %s", (en.enrollment_id,))
        if kept and kept > 500000:                       # tuition paid beyond the non-refundable deposit goes back
            self.at(self.today + dt.timedelta(days=self.rng.randint(2, 6)), 61, self.refund, en.enrollment_id, int(kept) - 500000,
                    "Cancelled before the start - tuition refunded, deposit kept", False)

    def drop_out(self, en: Enrolment):
        if self.val("select status_code from billing.enrollment where enrollment_id = %s", (en.enrollment_id,)) != "ACTIVE":
            return
        self.act(en.owner)
        self.x("select billing.change_enrollment_status(%s, 'DROPPED', %s, %s)", (en.enrollment_id, self.today, self.rng.choice(DROP_REASONS)))
        self.stats["drop-outs"] += 1

    def defer(self, en: Enrolment):
        if self.val("select status_code from billing.enrollment where enrollment_id = %s", (en.enrollment_id,)) != "ACTIVE":
            return
        self.act(en.owner)
        self.x("select billing.change_enrollment_status(%s, 'DEFERRED', %s, 'Exam period at school - continues in a later class')",
               (en.enrollment_id, self.today))
        self.stats["deferrals"] += 1
        self.at(self.today + dt.timedelta(days=self.rng.randint(30, 80)), 31, self.resume, en)

    def resume(self, en: Enrolment):
        cid = self.val("""select c.class_id from academic.class c
                          where c.course_id = %s and c.lifecycle_status in ('OPEN','RUNNING') and c.start_date >= %s - 21
                            and (select count(*) from billing.enrollment x where x.class_id = c.class_id
                                   and x.status_code in ('WAITLISTED','REGISTERED','ACTIVE')) < c.capacity
                          order by c.start_date, c.class_id limit 1""", (self.courses[en.course]["id"], self.today))
        if cid:
            self.act(en.owner)
            self.x("select billing.assign_class(%s, %s, %s)", (en.enrollment_id, cid, self.emp[en.owner]))
            en.class_id = cid
            self.stats["deferred learners resumed"] += 1
            for _ in range(2):
                self.at(self.today + dt.timedelta(days=self.rng.randint(0, 20)), 40, self.pay, en, "line")

    def continue_learners(self, prev_cid, cid, rate):
        """Learners finishing a level are offered the next class of the lane (returning-student discount)."""
        if self.val("select lifecycle_status from academic.class where class_id = %s", (cid,)) == "CANCELLED":
            return
        info = self.class_info[cid]
        for eid, sid, name, owner, gid, gname, school in self.rows("""
                select e.enrollment_id, s.student_id, s.full_name, so.employee_code, g.guardian_id, g.full_name, s.school_id
                from billing.enrollment e join crm.student s using (student_id)
                join hr.employee so on so.employee_id = e.sales_owner_employee_id
                left join crm.student_guardian sg on sg.student_id = s.student_id and sg.is_payer
                left join crm.guardian g on g.guardian_id = sg.guardian_id
                where e.class_id = %s and e.status_code = 'ACTIVE' order by e.enrollment_id""", (prev_cid,)):
            if self.rng.random() >= rate or self.seats_left(cid) <= 0:
                continue
            if owner == "E008":
                owner = "E005"
            lr = Learner(sid, name, info["programme"], gid is not None, gid, gname, school)
            day = self.today + dt.timedelta(days=self.rng.randint(0, 10))
            self.at(day, 30, self.do_enrol_returning, lr, cid, info["course"], owner, info["mode"])

    def do_enrol_returning(self, lr, cid, course, owner, mode):
        if self.seats_left(cid) <= 0 or self.today > self.class_info[cid]["start"] + dt.timedelta(days=7):
            return
        if self.val("select count(*) from billing.enrollment where student_id = %s and class_id = %s", (lr.student_id, cid)):
            return
        self.do_enrol(lr, cid, course, owner, mode, returning=True)
        self.stats["re-enrolments"] += 1

    def refund(self, eid, amount, reason, reduce_contract):
        self.act("E002")
        v = self.voucher(None, [], requested="E005", invoice=False, method="BANK_TRANSFER", payee_emp="E005",
                         note=f"Refund to learner (enrolment {eid}): {reason}")
        self.x("select billing.record_refund(%s, %s, %s, %s, %s, %s, %s)", (eid, self.today, amount, reason, self.emp["E002"], reduce_contract, v))
        self.stats["refunds"] += 1

    # ------------------------------------------------------------------------------------------- daily routine
    def daily_routine(self, d: D):
        dow = d.isoweekday()
        # Learning Advisor shifts (HR pays them by the hour)
        if self.is_open_day(d):
            shifts = []
            if dow <= 5:
                shifts.append(("E005", "13:30", "21:00"))
            if dow == 6:
                shifts.append(("E005", "08:00", "12:00"))
                shifts.append(("E005", "14:00", "18:00"))
            if dow in (2, 3, 4, 5, 6):
                shifts.append(("E006", "17:00", "21:00"))
            if dow in (6, 7):
                shifts.append(("E006", "08:00", "12:00"))
            for emp, t0, t1 in shifts:
                status = "ABSENT" if self.rng.random() < 0.015 else "WORKED"
                ded = 0.5 if status == "WORKED" and self.rng.random() < 0.03 else 0
                self.x("""insert into hr.work_shift (employee_role_id, shift_date, start_time, end_time, deduction_hours, status)
                          values (%s, %s, %s, %s, %s, %s)""", (self.role_ids[(emp, "LA")], d, t0, t1, ded, status))
        # Mondays: last week's sessions confirmed (Academic), shifts confirmed (HR), controls reviewed
        if dow == 1:
            self.confirm_sessions(d - ONE)
            self.review_commissions()
            self.act("E003")
            self.x("""update hr.work_shift set confirmed_by = %s, confirmed_at = now()
                      where confirmed_at is null and shift_date < %s""", (self.emp["E003"], d))
        # month-end calendar
        started = add_months(d.replace(day=1), -1) >= self.start      # last month was a month of operations
        if d.day == 1 and started:
            prev = d - ONE
            self.confirm_sessions(prev, everything=True)
            self.act("E003")
            self.x("update hr.work_shift set confirmed_by = %s, confirmed_at = now() where confirmed_at is null and shift_date <= %s",
                   (self.emp["E003"], prev))
        if d.day == 2 and started:
            self.payroll_calculate(add_months(d.replace(day=1), -1))
        if d.day == 3 and started:
            self.payroll_approve(add_months(d.replace(day=1), -1))
        if d.day == 5 and started:
            self.payroll_pay(add_months(d.replace(day=1), -1))
        if d == month_end(d) or (d == self.as_of - dt.timedelta(days=1)):
            self.payroll_prepare(d.replace(day=1))
        if d.day == 24:
            self.expense_claims(d)
        if d.day == 9 and d > add_months(self.start, 1) - ONE:
            self.month_end_close(add_months(d.replace(day=1), -1))

    def nightly(self, d: D):
        # end of day: every collector closes the cash drawer (today's drawer is still open in the snapshot)
        if d < self.as_of:
            for emp_code in ("E005", "E006"):
                if d == self.as_of - ONE and emp_code == "E006":
                    continue                                     # >> to do: Khoa forgot to close yesterday's cash
                cash = self.val("""select coalesce(sum(amount), 0) from billing.receipt where receipt_date = %s and collected_by = %s
                                   and status = 'ISSUED' and payment_method_code = 'CASH'""", (d, self.emp[emp_code]))
                n = self.val("select count(*) from billing.receipt where receipt_date = %s and collected_by = %s", (d, self.emp[emp_code]))
                if not n:
                    continue
                counted, note = int(cash), None
                r = self.rng.random()
                if (r < 0.04 and cash > 0) or (d == self.as_of - dt.timedelta(days=2) and emp_code == "E005" and cash > 0):
                    counted = int(cash) - self.rng.choice([10000, 20000, 50000])
                    note = "Short at count - change given twice to a parent"
                self.act(emp_code)
                ccid = self.val("select app.close_cash(%s, %s, %s, %s)", (d, self.emp[emp_code], counted, note))
                if note and d < self.as_of - dt.timedelta(days=3):
                    self.at(d + dt.timedelta(days=self.rng.randint(1, 3)), 16, self.review_cash, ccid)
        self.act("system")
        self.x("select academic.sync_class_statuses(%s)", (d,))
        self.x("select billing.sync_enrollment_statuses(%s)", (d,))
        if d.isoweekday() == 7 or d >= self.as_of - dt.timedelta(days=1):
            self.x("select ctl.run_all_controls()")
            self.work_exceptions(d)

    def review_commissions(self):
        """HR works control PAY-02: commission on learners who later dropped out or cancelled. Not yet paid -> cancelled;
        already paid -> accepted (the commission policy has no claw-back once the learner had paid in full)."""
        self.act("E003")
        for xid, cmid, status, run in self.rows("""select x.exception_id, c.commission_id, c.status, c.run_id
                                                  from ctl.control_exception x join payroll.commission c on c.commission_id = x.entity_id
                                                  where x.control_code = 'PAY-02' and x.status in ('OPEN','IN_PROGRESS') order by x.exception_id"""):
            if status == "ACCRUED" and run is None:
                self.x("update payroll.commission set status = 'CANCELLED' where commission_id = %s", (cmid,))
                self.x("""update ctl.control_exception set status = 'RESOLVED', resolved_at = now(), assigned_to = %s,
                          resolution_note = 'Commission cancelled before payroll: the learner left before the course was earned'
                          where exception_id = %s""", (self.emp["E003"], xid))
            else:
                self.x("""update ctl.control_exception set status = 'RISK_ACCEPTED', resolved_at = now(), assigned_to = %s,
                          resolution_note = 'Commission already paid; the policy has no claw-back once the learner had paid in full'
                          where exception_id = %s""", (self.emp["E003"], xid))

    def review_cash(self, ccid):
        self.act("E002")
        self.x("select app.review_cash_close(%s, %s)", (ccid, self.emp["E002"]))

    def work_exceptions(self, d: D):
        """Owners work their queues: collections in progress, accepted risks with a justification."""
        self.act("E005")
        for (xid,) in self.rows("select exception_id from ctl.control_exception where control_code = 'BIL-03' and status = 'OPEN' and assigned_to is null order by exception_id"):
            if self.rng.random() < 0.5:
                self.x("""update ctl.control_exception set status = 'IN_PROGRESS', assigned_to = %s,
                          resolution_note = 'Reminder sent; parent promised to pay this week' where exception_id = %s""",
                       (self.emp[self.rng.choice(["E005", "E006"])], xid))

    # ------------------------------------------------------------------------------------------- payroll
    def payroll_prepare(self, month: D):
        pid = period(month)
        if self.val("select count(*) from payroll.payroll_run where period_id = %s", (pid,)):
            return
        self.act("E003")
        run = self.val("insert into payroll.payroll_run (period_id, run_type) values (%s, 'REGULAR') returning run_id", (pid,))
        lines = []
        for code in ("E005", "E006"):
            lines.append((code, "ALLOW_PHONE", 200000, "Phone allowance"))
        for code, *_ in [s for s in STAFF if s[4] == "FULL_TIME"]:
            lines.append((code, "ALLOW_LUNCH", 730000, "Lunch allowance"))
        if month.month == 1:                                   # paid early February, before Lunar New Year
            for s in STAFF:
                if s[8]:
                    lines.append((s[0], "OTHER_INCOME", s[8], "Lunar New Year bonus (13th month)"))
                elif s[0] not in ("E008",) or month < self.resign_date:
                    lines.append((s[0], "OTHER_INCOME", 1000000, "Lunar New Year bonus"))
        tests = self.val("""select count(*) from crm.placement_test where status = 'COMPLETED'
                            and completed_at >= %s and completed_at < %s""", (month, add_months(month, 1)))
        if tests:
            lines.append(("E009", "NON_TEACHING_ACTIVITY", 40000 * tests, f"Placement-test marking ({tests} tests)"))
        for code, et, amount, note in lines:
            if code == "E013" and month < add_months(self.start, 4):
                continue
            self.x("""insert into payroll.payroll_line (run_id, employee_id, earning_type_code, amount, source_type, account_code, cost_center_code, note)
                      select %s, e.employee_id, %s, %s, 'MANUAL', finance.earning_account(%s, null, null, null), e.home_cost_center_code, %s
                      from hr.employee e where e.employee_code = %s""", (run, et, amount, et, note, code))

    def payroll_calculate(self, month: D):
        self.payroll_prepare(month)
        self.act("E003")
        self.x("select payroll.calculate_run(run_id) from payroll.payroll_run where period_id = %s and status in ('DRAFT','CALCULATED')", (period(month),))

    def payroll_approve(self, month: D):
        self.act("E003")
        self.x("select payroll.approve_run(run_id, %s) from payroll.payroll_run where period_id = %s and status = 'CALCULATED'",
               (self.emp["E003"], period(month)))

    def payroll_pay(self, month: D):
        self.act("E002")
        self.x("select payroll.mark_run_paid(run_id, %s) from payroll.payroll_run where period_id = %s and status = 'APPROVED'",
               (self.today, period(month)))

    # ------------------------------------------------------------------------------------------- finance
    def voucher(self, vendor, lines, requested="E002", invoice=True, method="BANK_TRANSFER", note=None, payee_emp=None,
                funding="COMPANY_ACCOUNT", claim_id=None):
        self.act("E002")
        self.voucher_no += 1
        no = f"PC{self.voucher_no:04d}"
        vid = self.val("""insert into finance.payment_voucher (voucher_no, voucher_date, requested_by, approved_by, payee_vendor_id,
                                payee_employee_id, funding_source, payment_method_code, has_invoice, invoice_no, claim_id, notes)
                          values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning voucher_id""",
                       (no, self.today, self.emp[requested], self.emp["E002"], self.vendors.get(vendor) if vendor else None,
                        self.emp[payee_emp] if payee_emp else None, funding, method, invoice,
                        f"{self.rng.randint(1, 9999999):07d}" if invoice else None, claim_id, note))
        line_ids = []
        for i, (descr, amount, vat, acc, cc, cid, pid) in enumerate(lines, 1):
            line_ids.append(self.val("""insert into finance.payment_voucher_line (voucher_id, line_no, description, amount_excl_vat, vat_code,
                                            recognition_period_id, cost_center_code, account_code, class_id)
                                        values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning voucher_line_id""",
                                     (vid, i, descr, round(amount), vat, pid, cc, acc, cid)))
        self.stats["payment vouchers"] += 1
        self._last_lines = line_ids
        return vid

    def capex(self, day, vendor, descr, amount, vat, capex_acc, charge_acc, life, capitalise=True):
        keep = self.today
        self.today = day
        self.voucher(vendor, [(descr, amount, vat, capex_acc, "921011", None, period(day))], invoice=True)
        line = self._last_lines[0]
        if capitalise:
            self.asset_no += 1
            cost = self.val("select amount_incl_vat from finance.payment_voucher_line where voucher_line_id = %s", (line,))
            aid = self.val("""insert into finance.fixed_asset (asset_code, asset_name, capex_account_code, charge_account_code, cost_center_code,
                                  voucher_line_id, acquisition_date, cost, useful_life_months, first_charge_period_id)
                              values (%s, %s, %s, %s, '921011', %s, %s, %s, %s, %s) returning asset_id""",
                           (f"FA-{self.asset_no:04d}", descr, capex_acc, charge_acc, line, day, cost, life, period(day)))
            self.x("select finance.generate_depreciation(%s)", (aid,))
        self.today = keep

    def capex_laptop(self, descr):
        self.capex(self.today, "Electronics store", descr, 14500000, "i10", "E3.001", "E3.004", 36)

    def monthly_expenses(self, month: D):
        pid = period(month)
        prev = period(add_months(month, -1))
        m = month.month
        hot = m in (3, 4, 5, 6)
        self.voucher("Landlord - campus premises (individual)", [(f"Campus rent {month:%b %Y}", 13000000, "i0", "E7.012", "921011", None, pid)],
                     invoice=False, note="Lease contract on file; individual landlord issues no VAT invoice")
        if month > self.start:
            self.voucher("Provincial power company", [(f"Electricity {add_months(month, -1):%b %Y}", self.rng.randint(32, 46) * 100000 if hot else self.rng.randint(22, 31) * 100000, "i10", "E7.007", "921011", None, prev)])
            self.voucher("City water supply", [(f"Water {add_months(month, -1):%b %Y}", self.rng.randint(25, 42) * 10000, "i8", "E7.007", "921011", None, prev)])
        self.voucher("Telecom provider", [(f"Internet and phone {month:%b %Y}", 650000, "i10", "E7.016", "921011", None, pid)])
        self.voucher("Cleaning service", [(f"Cleaning {month:%b %Y}", 1800000, "i0", "E7.015", "921011", None, pid)])
        self.voucher("Accounting firm", [(f"Bookkeeping and tax filing {month:%b %Y}", 2500000, "i10", "E7.004", "921010", None, pid)])
        intake = m in (8, 9, 12, 1, 5, 6)
        self.voucher("Online ads platform", [(f"Facebook / Google ads {month:%b %Y}", self.rng.randint(45, 70) * 100000 if intake else self.rng.randint(22, 35) * 100000, "i10", "E8.036", "921014", None, pid)],
                     requested="E012")
        if intake:
            self.voucher("Print shop", [("Flyers and standees for the open day", self.rng.randint(18, 30) * 100000, "i10", "E8.020", "921014", None, pid)], requested="E012")
            self.voucher(None, [("Open day: snacks, gifts, decoration", self.rng.randint(15, 25) * 100000, "i0", "E8.027", "921014", None, pid)],
                         requested="E012", invoice=False, method="CASH", funding="PETTY_CASH", payee_emp="E012")
        self.voucher("Online marketplace", [("Stationery and whiteboard markers", self.rng.randint(9, 19) * 10000, "i0", "E2.002", "921011", None, pid)],
                     requested="E003", invoice=False, method="CASH", funding="PETTY_CASH")
        self.voucher("Print shop", [("Photocopies - worksheets and tests", self.rng.randint(4, 9) * 100000, "i10", "E8.005", "921013", None, pid)], requested="E004")
        self.voucher("Bank", [("Bank and card fees", self.rng.randint(8, 18) * 10000, "i0", "E7.011", "921010", None, pid)], invoice=False)
        if m in (3, 9):
            self.voucher(None, [("Teacher training workshop", 3500000, "i0", "E8.032", "921013", None, pid)], requested="E004",
                         invoice=False, method="BANK_TRANSFER", payee_emp="E004")

    def expense_claims(self, d: D):
        for code in ("E005", "E006"):
            self.act(code)
            self.claim_no += 1
            items = [("Printing of placement tests", "Placement tests", "Print shop", self.rng.randint(5, 15) * 10000, "E8.005"),
                     ("Taxi to partner school", "School presentation", "Taxi", self.rng.randint(6, 16) * 10000, "E8.002")]
            items = items[: self.rng.randint(1, 2)]
            cl = self.val("""insert into finance.expense_claim (claim_no, employee_id, cost_center_code, submitted_on, status)
                             values (%s, %s, '921012', %s, 'SUBMITTED') returning claim_id""", (f"CLM-{d:%Y}-{self.claim_no:03d}", self.emp[code], d))
            for i, (descr, purpose, vend, amount, acc) in enumerate(items, 1):
                self.x("""insert into finance.expense_claim_line (claim_id, line_no, transaction_date, description, business_purpose,
                                                                   vendor_name, amount_excl_vat, vat_code)
                          values (%s, %s, %s, %s, %s, %s, %s, 'i0')""", (cl, i, d - dt.timedelta(days=self.rng.randint(1, 15)), descr, purpose, vend, amount))
            if d + dt.timedelta(days=2) <= self.as_of:
                self.at(d + dt.timedelta(days=2), 62, self.pay_claim, cl, code, items)

    def pay_claim(self, cl, code, items):
        self.act("E002")
        self.x("update finance.expense_claim set status = 'APPROVED', approved_by = %s, approved_on = %s where claim_id = %s", (self.emp["E002"], self.today, cl))
        self.voucher(None, [(f"Reimbursement: {descr}", amount, "i0", acc, "921012", None, period(self.today)) for descr, _, _, amount, acc in items],
                     requested=code, invoice=False, method="CASH", funding="PETTY_CASH", payee_emp=code, claim_id=cl,
                     note="Expense claim reimbursement (receipts attached to the claim)")
        self.x("update finance.expense_claim set status = 'PAID' where claim_id = %s", (cl,))

    def price_increase(self, effective: D):
        """Finance raises Applied English offline prices by 5% (dated price list: old enrolments keep their price)."""
        self.act("E002")
        for cpid, course_id, amount in self.rows("""select p.course_price_id, p.course_id, p.amount from ref.course_price p join ref.course c using (course_id)
                                                     where c.programme_code = 'AE' and p.delivery_mode_code = 'OFFLINE'
                                                       and p.price_basis = 'FULL_COURSE' and p.effective_to is null
                                                     order by p.course_price_id"""):
            self.x("update ref.course_price set effective_to = %s where course_price_id = %s", (effective, cpid))
            self.x("""insert into ref.course_price (course_id, delivery_mode_code, price_basis, amount, effective_from)
                      values (%s, 'OFFLINE', 'FULL_COURSE', %s, %s)""", (course_id, round(float(amount) * 1.05 / 50000) * 50000, effective))

    def month_end_close(self, month: D):
        """Finance closes last month: write-offs, accruals, risk decisions, then the period lock."""
        pid = period(month)
        if self.val("select status from finance.fiscal_period where period_id = %s", (pid,)) != "OPEN":
            return
        self.act("E002")
        end = month_end(month)
        self.x("select ctl.run_all_controls()")
        for eid, out in self.rows("""select b.enrollment_id, b.outstanding_receivable from rpt.v_enrollment_balance b
                                     join billing.enrollment e using (enrollment_id)
                                     where b.status_code in ('DROPPED','CANCELLED') and b.outstanding_receivable > 0
                                       and e.status_changed_on <= %s order by b.enrollment_id""", (end - dt.timedelta(days=20),)):
            self.x("select billing.write_off_balance(%s, %s, %s, %s, %s)",
                   (eid, end, out, "Dropped out; reminders unanswered for 30 days - written off", self.emp["E002"]))
            self.stats["write-offs"] += 1
        if month.month in (3, 6, 9, 12):
            self.journal_no += 1
            je = self.val("""insert into finance.journal_entry (entry_no, period_id, entry_date, basis, entry_type, description, posted_by)
                             values (%s, %s, %s, 'ACCRUAL_ONLY', 'ACCRUAL', %s, %s) returning journal_entry_id""",
                          (f"JE-{month:%Y}-{self.journal_no:04d}", pid, end, f"Accrue Q{(month.month - 1) // 3 + 1} audit fee", self.emp["E002"]))
            self.x("""insert into finance.journal_line (journal_entry_id, line_no, account_code, cost_center_code, debit, credit, memo)
                      values (%s, 1, 'E7.001', '921010', 4500000, 0, 'Audit fee for the quarter'),
                             (%s, 2, 'B2.201', null, 0, 4500000, 'Accrued expenses')""", (je, je))
        self.x("""update ctl.control_exception x set status = 'RISK_ACCEPTED', resolved_at = now(), assigned_to = %s,
                         resolution_note = 'Individual landlord: no VAT invoice is issued. Signed lease and payment proof on file.'
                  from finance.payment_voucher v where x.control_code = 'EXP-01' and x.entity_id = v.voucher_id
                   and x.status in ('OPEN','IN_PROGRESS') and v.payee_vendor_id = %s""", (self.emp["E002"], self.vendors["Landlord - campus premises (individual)"]))
        self.x("""update ctl.control_exception x set status = 'RISK_ACCEPTED', resolved_at = now(), assigned_to = %s,
                         resolution_note = 'Small petty-cash purchases: supplier receipts kept, no VAT invoice available.'
                  where x.control_code = 'EXP-01' and x.status in ('OPEN','IN_PROGRESS')""", (self.emp["E002"],))
        for (ccid,) in self.rows("select cash_close_id from app.cash_close where reviewed_at is null and difference <> 0 and close_date <= %s order by 1", (end,)):
            self.x("select app.review_cash_close(%s, %s)", (ccid, self.emp["E002"]))
        self.x("select finance.close_period(%s, %s)", (pid, self.emp["E002"]))
        self.stats["months closed"] += 1

    # ------------------------------------------------------------------------------------------- the business date
    def plan_today_scenarios(self):
        """Situations waiting for each role on the business date (the to-do lists of the demo)."""
        a = self.as_of
        self.at(a - dt.timedelta(days=46), 30, self.waitlist_without_class, "PROGRESS", 2)     # >> BIL-07: paid, no class yet
        self.at(a - dt.timedelta(days=12), 30, self.waitlist_without_class, "PROGRESS", 1)
        self.at(a - dt.timedelta(days=3), 42, self.advance_payment)                          # >> BIL-04
        self.at(a - dt.timedelta(days=6), 60, self.capex_not_capitalised)                    # >> EXP-02
        self.at(a - dt.timedelta(days=4), 60, self.miscoded_spend)                           # >> EXP-03
        self.at(a, 20, self.unassigned_web_leads)                                            # >> SAL-01
        self.at(a, 41, self.pending_void)                                                    # >> Finance approval
        self.at(a - ONE, 30, self.pending_discount)                                          # >> BIL-05
        self.at(a - dt.timedelta(days=2), 43, self.desk_payment, "E005")                     # >> BIL-09 (cash difference)
        self.at(a - ONE, 43, self.desk_payment, "E006")                                      # >> BIL-09 (day not closed)

    def waitlist_without_class(self, course, n):
        for _ in range(n):
            owner = self.owner_for(self.today)
            ctx_class = None
            self.act(owner)
            lr = self.new_person("IELTS", course)
            lead = self.val("""insert into crm.lead (student_id, lead_date, owner_employee_id, channel_code, programme_code, stage_code)
                               values (%s, %s, %s, 'MOCK_TEST', 'IELTS', 'TESTED') returning lead_id""",
                            (lr.student_id, self.today - dt.timedelta(days=5), self.emp[owner]))
            tid = self.val("""insert into crm.placement_test (lead_id, test_type, scheduled_at, status, assessed_by, overall_level_id, completed_at)
                              values (%s, 'IELTS', %s, 'COMPLETED', %s, %s, %s) returning test_id""",
                           (lead, dt.datetime.combine(self.today - dt.timedelta(days=3), dt.time(9, 30)), self.emp["E004"],
                            self.levels[("IELTS", "5.5")], dt.datetime.combine(self.today - dt.timedelta(days=3), dt.time(11, 0))))
            en = self.do_enrol(lr, ctx_class, course, owner, "OFFLINE", lead, plan="FULL",
                               notes="Can only attend weekday mornings - waiting for a morning class")
            self.at(self.today, 40, self.pay, en, "line")

    def desk_payment(self, collector):
        """A parent comes to the desk and pays an overdue instalment in cash."""
        row = self.c.execute("""select l.enrollment_id, e.student_id, s.full_name, g.guardian_id, g.full_name, l.remaining
                                from rpt.v_schedule_line_status l join billing.enrollment e using (enrollment_id)
                                join crm.student s using (student_id)
                                left join crm.student_guardian sg on sg.student_id = s.student_id and sg.is_payer
                                left join crm.guardian g on g.guardian_id = sg.guardian_id
                                where l.remaining > 0 and l.is_billable and l.due_date <= %s
                                order by l.days_overdue desc, l.schedule_line_id limit 1""", (self.today,)).fetchone()
        if not row:
            return
        self.act(collector)
        self.x("select billing.record_receipt(%s, %s, %s, %s, 'CASH', %s, %s, %s)",
               (row[1], row[0], self.today, int(row[5]), self.emp[collector], row[4] or row[2], row[3]))

    def advance_payment(self):
        row = self.c.execute("""select e.student_id, s.full_name from billing.enrollment e join crm.student s using (student_id)
                                where e.status_code = 'ACTIVE' and e.course_id in (select course_id from ref.course where programme_code = 'AE')
                                order by e.enrollment_id desc limit 1""").fetchone()
        if not row:
            return
        self.act("E005")
        self.x("select billing.record_receipt(%s, null, %s, 1500000, 'CASH', %s, %s, null, %s)",
               (row[0], self.today, self.emp["E005"], row[1], "Advance for the next level - enrolment form not signed yet"))

    def capex_not_capitalised(self):
        self.capex(self.today, "Electronics store", "Laptop for the academic office", 13900000, "i10", "E3.001", "E3.004", 36, capitalise=False)

    def miscoded_spend(self):
        self.voucher("Online marketplace", [("Refreshments for the teachers' meeting", 180000, "i0", "E1.001", "921013", None, period(self.today))],
                     requested="E004", invoice=False, method="CASH", funding="PETTY_CASH")

    def unassigned_web_leads(self):
        self.act("E005")
        for prog in ("IELTS", "AE"):
            lr = self.new_person(prog, "PRE" if prog == "IELTS" else "R1")
            self.x("""insert into crm.lead (student_id, lead_date, programme_code, stage_code, notes)
                      values (%s, %s, %s, 'NEW', 'Website contact form - not yet assigned to an advisor')""", (lr.student_id, self.today, prog))
            self.stats["leads"] += 1

    def pending_void(self):
        rid = self.val("""select receipt_id from billing.receipt where receipt_date = %s and status = 'ISSUED' and collected_by = %s
                          order by receipt_id desc limit 1""", (self.today - ONE, self.emp["E005"]))
        if rid:
            self.act("E005")
            self.x("select billing.request_receipt_void(%s, %s, %s)", (rid, self.emp["E005"], "Parent paid by bank transfer, keyed as cash"))

    def pending_discount(self):
        cid = self.val("""select c.class_id from academic.class c join ref.course co using (course_id)
                          where co.programme_code = 'IELTS' and c.lifecycle_status = 'OPEN' and c.start_date > %s
                          order by c.start_date, c.class_id limit 1""", (self.today,))
        if not cid or self.seats_left(cid) <= 0:
            return
        self.act("E006")
        lr = self.new_person("IELTS", self.class_info[cid]["course"])
        self.x("update crm.student set school_id = %s, grade_label = 'Grade 11' where student_id = %s", (self.schools["City High School"], lr.student_id))
        lr.school_id = self.schools["City High School"]
        lead = self.val("""insert into crm.lead (student_id, lead_date, owner_employee_id, channel_code, programme_code, stage_code)
                           values (%s, %s, %s, 'SCHOOL_PARTNERSHIP', 'IELTS', 'TESTED') returning lead_id""",
                        (lr.student_id, self.today - dt.timedelta(days=6), self.emp["E006"]))
        self.x("""insert into crm.placement_test (lead_id, test_type, scheduled_at, status, assessed_by, overall_level_id, completed_at)
                  values (%s, 'IELTS', %s, 'COMPLETED', %s, %s, %s)""",
               (lead, dt.datetime.combine(self.today - dt.timedelta(days=4), dt.time(9, 30)), self.emp["E004"],
                self.levels[("IELTS", "5.0")], dt.datetime.combine(self.today - dt.timedelta(days=4), dt.time(11, 0))))
        self.act("E006")
        eid = self.val("""select billing.enrol(%s, %s::smallint, 'OFFLINE', %s, 'P50_30_20', %s, %s, %s,
                                               array['PARTNER_SCHOOL_30','EARLY_BIRD_10'], null, 500000)""",
                       (lr.student_id, self.courses[self.class_info[cid]["course"]]["id"], cid, self.today, self.emp["E006"], lead))
        en = Enrolment(eid, lr, cid, self.class_info[cid]["course"], "E006", "PROMPT", "P50_30_20")
        self.pay(en, "line")

    # ------------------------------------------------------------------------------------------- wrap-up
    def finish(self):
        """Freeze the business date and move every timestamp written by now() onto the simulated calendar."""
        self.x("update ref.app_setting set setting_value = %s where setting_key = 'as_of_date'", (self.as_of.isoformat(),))
        self.x("insert into sim_clock values (now(), %s::timestamp at time zone 'Asia/Ho_Chi_Minh') on conflict do nothing",
               (dt.datetime.combine(self.as_of, dt.time(8, 0)),))              # this transaction belongs to the business date
        self.act("system")
        self.x("select * from app.run_daily_jobs(%s)", (self.as_of,))
        self.x("set local session_replication_role = replica")            # timestamp fix-up only: no triggers, no audit rows
        cols = self.rows("""select table_schema, table_name, column_name from information_schema.columns c
                            join information_schema.tables t using (table_schema, table_name)
                            where t.table_type = 'BASE TABLE' and c.data_type = 'timestamp with time zone'
                              and table_schema in ('crm','academic','billing','hr','payroll','finance','ctl','app')
                              and not (table_name = 'audit_log' and column_name = 'occurred_at')""")
        for schema, table, col in cols:
            self.x(f"""update {schema}.{table} x set {col} = k.sim_ts + ((abs(hashtext(x.ctid::text)) % 600) * interval '1 minute')
                       from sim_clock k where x.{col} = k.real_ts""")
        self.x("""update app.audit_log a set occurred_at = k.sim_ts + (r.n * interval '7 seconds')
                  from (select audit_id, occurred_at, row_number() over (partition by occurred_at order by audit_id) as n from app.audit_log) r
                  join sim_clock k on k.real_ts = r.occurred_at
                  where a.audit_id = r.audit_id""")
        # sign-ins are not part of the history
        self.x("update app.app_user set last_login_at = null")
        self.x("delete from app.audit_log where table_name = 'app.app_user' and action = 'UPDATE'")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dsn", required=True, help="database built with database/build.sql (and nothing else)")
    ap.add_argument("--as-of", type=D.fromisoformat, default=dt.date.today(), help="business date of the snapshot (default: today)")
    ap.add_argument("--seed", type=int, default=2025, help="random seed (same seed + date = same data)")
    ap.add_argument("--password", default="ami-demo", help="password of the demo accounts")
    args = ap.parse_args()
    with psycopg.connect(args.dsn, autocommit=True) as conn:
        if conn.execute("select count(*) from billing.enrollment").fetchone()[0]:
            sys.exit("The database already holds operating data: build a fresh one with database/build.sql")
        Simulation(conn, args.as_of, args.seed, args.password).run()


if __name__ == "__main__":
    main()
