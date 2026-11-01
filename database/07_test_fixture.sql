/* =====================================================================================
   07_test_fixture.sql - a small, hand-written synthetic scenario that exercises every table, rule and control.
   It is the fixture of the executable specification (08_tests.sql). The application demo uses the larger generated dataset
   (seed/demo_dataset.sql) instead. All people are fictitious.  As-of date: 2025-06-30.
   Several records are deliberately "wrong" so that the controls in ctl.* raise exceptions
   (marked  >> CONTROL DEMO).
   ===================================================================================== */

update ref.app_setting set setting_value = '2025-06-30' where setting_key = 'as_of_date';
select finance.ensure_periods('2024-06-01', '2025-12-31');

/* ------------------------------------------------------------------ staff */
insert into hr.employee (employee_code, full_name, name_code, gender, employment_type, home_cost_center_code, hire_date, email) values
  ('E001', 'Trần Minh Anh',    'Anh TM',  'FEMALE', 'FULL_TIME', '921010', '2024-06-01', 'anh.tm@example.com'),
  ('E002', 'Lê Thu Hà',        'Hà LT',   'FEMALE', 'PART_TIME', '921012', '2024-06-01', 'ha.lt@example.com'),
  ('E003', 'Phạm Gia Huy',     'Huy PG',  'MALE',   'PART_TIME', '921012', '2025-02-01', 'huy.pg@example.com'),
  ('E004', 'Nguyễn Ngọc Lan',  'Lan NN',  'FEMALE', 'PART_TIME', '921013', '2024-06-01', 'lan.nn@example.com'),
  ('E005', 'Võ Hoàng Nam',     'Nam VH',  'MALE',   'PART_TIME', '921017', '2024-06-01', 'nam.vh@example.com'),
  ('E006', 'Đặng Mỹ Linh',     'Linh ĐM', 'FEMALE', 'PART_TIME', '921017', '2024-09-01', 'linh.dm@example.com'),
  ('E007', 'Hồ Bảo Trâm',      'Trâm HB', 'FEMALE', 'FULL_TIME', '921014', '2024-06-01', 'tram.hb@example.com'),
  ('E008', 'Bùi Khánh Vy',     'Vy BK',   'FEMALE', 'FULL_TIME', '921013', '2024-06-01', 'vy.bk@example.com');
update finance.cost_center set manager_employee_id = (select employee_id from hr.employee where employee_code = 'E001')
where cost_center_code in ('921010','921011','921012','921014');
update finance.cost_center set manager_employee_id = (select employee_id from hr.employee where employee_code = 'E008')
where is_academic;

insert into hr.employee_role (hr_code, employee_id, role_code, contract_stage_code, salary_code, cost_center_code, effective_from)
select v.hr_code, e.employee_id, v.role, v.stage, sc.salary_code, v.cc, v.from_date::date
from (values
  ('ANHTMCEN001',  'E001', 'CENTRE_MANAGER',       'OFFICIAL',  '921010', '2024-06-01'),
  ('HALTLA001',    'E002', 'LA',                   'OFFICIAL',  '921012', '2024-06-01'),
  ('HALTTA001',    'E002', 'TA_AE_COMM',           'PROBATION', '921013', '2025-01-01'),
  ('HUYPGLA002',   'E003', 'LA',                   'PROBATION', '921012', '2025-02-01'),
  ('LANNNACAD001', 'E004', 'TEACHER_AE_COMM',      'OFFICIAL',  '921013', '2024-06-01'),
  ('NAMVHACAD002', 'E005', 'TEACHER_IELTS',        'OFFICIAL',  '921017', '2024-06-01'),
  ('LINHDMAT001',  'E006', 'AT_IELTS',             'OFFICIAL',  '921017', '2024-09-01'),
  ('TRAMHBMKT001', 'E007', 'MARKETING',            'OFFICIAL',  '921014', '2024-06-01'),
  ('VYBKACO001',   'E008', 'ACADEMIC_COORDINATOR', 'OFFICIAL',  '921013', '2024-06-01')
) as v(hr_code, emp, role, stage, cc, from_date)
join hr.employee e on e.employee_code = v.emp
left join ref.salary_code sc on sc.role_code = v.role and sc.contract_stage_code = v.stage;

insert into hr.employee_fixed_pay (employee_role_id, monthly_amount, effective_from)
select employee_role_id, v.amount, '2024-06-01' from hr.employee_role er
join (values ('ANHTMCEN001', 9000000), ('TRAMHBMKT001', 4000000), ('VYBKACO001', 5000000)) as v(hr, amount) on v.hr = er.hr_code;

-- Personal rate: the IELTS assistant was hired at 42,000/h instead of the 40,000/h standard
insert into hr.employee_rate_override (employee_role_id, hourly_rate, effective_from, reason, approved_by)
select er.employee_role_id, 42000, '2024-09-01', 'Hired with IELTS 8.0; rate agreed at offer', (select employee_id from hr.employee where employee_code = 'E001')
from hr.employee_role er where er.hr_code = 'LINHDMAT001';

-- Learning Advisor shifts in April 2025 (4-hour afternoon shifts on weekdays)
insert into hr.work_shift (employee_role_id, shift_date, start_time, end_time, deduction_hours, confirmed_by, confirmed_at)
select er.employee_role_id, d::date, '13:30', '17:30',
       case when er.hr_code = 'HUYPGLA002' and extract(day from d) = 15 then 0.5 else 0 end,
       (select employee_id from hr.employee where employee_code = 'E001'), '2025-04-30 18:00+07'
from hr.employee_role er
cross join generate_series('2025-04-01'::date, '2025-04-30'::date, interval '1 day') d
where er.hr_code in ('HALTLA001','HUYPGLA002') and extract(isodow from d) <= 5
  and (er.hr_code = 'HUYPGLA002' or extract(isodow from d) in (1, 3, 5));

/* ------------------------------------------------------------------ classes, timetable, staffing, sessions */
insert into academic.class (class_code, course_id, delivery_mode_code, batch_no, start_date, planned_end_date,
                            total_hours, hours_per_session, sessions_per_week, capacity, room_id, lifecycle_status)
select v.code, c.course_id, 'OFFLINE', v.batch, v.start_d::date, v.start_d::date, c.standard_hours,
       c.default_hours_per_session, c.default_sessions_per_week, v.cap, (select room_id from academic.room where room_name = v.room), v.lc
from (values
  ('AE_L1_150125',       'L1',       1, '2025-01-15', 12, 'Room 101', 'COMPLETED'),
  ('IE_PROGRESS_030325', 'PROGRESS', 2, '2025-03-03', 1,  'Room 102', 'COMPLETED'),   -- capacity 1 for a 2-learner class >> CONTROL DEMO (ACA-01)
  ('COM_A1_020625',      'A1',       3, '2025-06-02', 12, 'Room 201', 'RUNNING'),
  ('IE_PRO_010725',      'PRO',      3, '2025-07-01', 10, 'Room 102', 'OPEN')
) as v(code, course, batch, start_d, cap, room, lc)
join ref.course c on c.course_code = v.course;

insert into academic.class_meeting_pattern (class_id, weekday, start_time, end_time)
select c.class_id, v.wd, v.st::time, v.et::time from (values
  ('AE_L1_150125', 1, '18:00', '19:30'), ('AE_L1_150125', 3, '18:00', '19:30'),
  ('IE_PROGRESS_030325', 1, '14:00', '16:00'), ('IE_PROGRESS_030325', 2, '14:00', '16:00'),
  ('IE_PROGRESS_030325', 4, '14:00', '16:00'), ('IE_PROGRESS_030325', 6, '14:00', '16:00'),
  ('COM_A1_020625', 1, '19:00', '20:30'), ('COM_A1_020625', 3, '19:00', '20:30'), ('COM_A1_020625', 5, '19:00', '20:30'),
  ('IE_PRO_010725', 2, '18:30', '20:30'), ('IE_PRO_010725', 4, '18:30', '20:30'), ('IE_PRO_010725', 6, '18:30', '20:30')
) as v(code, wd, st, et) join academic.class c on c.class_code = v.code;

select academic.generate_sessions(class_id) from academic.class order by class_id;

insert into academic.class_staff_assignment (class_id, employee_role_id, assignment_role, effective_from)
select c.class_id, er.employee_role_id, v.arole, c.start_date from (values
  ('AE_L1_150125', 'LANNNACAD001', 'LEAD_TEACHER'), ('AE_L1_150125', 'HALTTA001', 'TEACHING_ASSISTANT'),
  ('IE_PROGRESS_030325', 'NAMVHACAD002', 'LEAD_TEACHER'), ('IE_PROGRESS_030325', 'LINHDMAT001', 'TEACHING_ASSISTANT'),
  ('COM_A1_020625', 'LANNNACAD001', 'LEAD_TEACHER'), ('COM_A1_020625', 'HALTTA001', 'TEACHING_ASSISTANT'),
  ('IE_PRO_010725', 'NAMVHACAD002', 'LEAD_TEACHER')
) as v(code, hr, arole) join academic.class c on c.class_code = v.code join hr.employee_role er on er.hr_code = v.hr;

-- Sessions up to the as-of date are delivered; staff hours confirmed by the academic coordinator
update academic.class_session set status = 'DELIVERED' where session_date <= ref.as_of_date();
insert into academic.session_staff (session_id, employee_role_id, hours, confirmed_by, confirmed_at)
select s.session_id, a.employee_role_id, s.planned_hours,
       (select employee_id from hr.employee where employee_code = 'E008'), s.session_date + time '21:00'
from academic.class_session s
join academic.class_staff_assignment a on a.class_id = s.class_id
where s.status = 'DELIVERED';
-- >> CONTROL DEMO (ACA-02): the last delivered Communication session of 20 June is still unconfirmed
delete from academic.session_staff ss using academic.class_session s join academic.class c using (class_id)
where ss.session_id = s.session_id and c.class_code = 'COM_A1_020625' and s.session_date = '2025-06-20';
update academic.class set actual_end_date = planned_end_date where lifecycle_status = 'COMPLETED';

/* ------------------------------------------------------------------ customers, guardians, leads, tests */
insert into crm.student (full_name, gender, date_of_birth, phone, school_id, grade_label, first_contact_date, legacy_ref)
select v.name, v.gender, v.dob::date, v.phone, (select school_id from ref.school where school_name = v.school), v.grade, v.first_d::date, v.ref
from (values
  ('Ngô Bảo Châu',      'FEMALE', '2014-03-12', null,           'Riverside Primary School',     'Grade 5',    '2024-12-20', 'C01'),
  ('Ngô Gia Khang',     'MALE',   '2015-08-30', null,           'Riverside Primary School',     'Grade 4',    '2024-12-20', 'C02'),
  ('Lý Minh Thư',       'FEMALE', '2014-11-02', null,           'Kim Dong Primary School',      'Grade 5',    '2024-12-28', 'C03'),
  ('Trương Quốc Bảo',   'MALE',   '2008-05-21', '0100 000 004', 'High School for the Gifted',   'Grade 11',   '2025-02-10', 'C04'),
  ('Đinh Thảo Vy',      'FEMALE', '2008-09-15', '0100 000 005', 'City High School',             'Grade 11',   '2025-02-12', 'C05'),
  ('Cao Hữu Phước',     'MALE',   '1996-01-08', '0100 000 006', null,                           'Working',    '2025-05-05', 'C06'),
  ('Tạ Ngọc Hân',       'FEMALE', '2003-07-19', '0100 000 007', 'Bac Lieu University',          'University', '2025-05-12', 'C07'),
  ('Huỳnh Đức Tài',     'MALE',   '2007-12-01', '0100 000 008', 'City High School',             'Grade 12',   '2025-06-01', 'C08'),
  ('Mai Thanh Trúc',    'FEMALE', '2011-04-04', null,           'Lotus Lower Secondary School', 'Grade 8',    '2025-04-25', 'C09'),
  ('Dương Văn Lộc',     'MALE',   '1999-10-10', '0100 000 010', null,                           'Working',    '2025-05-20', 'C10'),
  ('Kiều Anh Thư',      'FEMALE', '2013-06-06', null,           'Kim Dong Primary School',      'Grade 6',    '2025-06-10', 'C11')
) as v(name, gender, dob, phone, school, grade, first_d, ref);

insert into crm.guardian (full_name, phone, email) values
  ('Ngô Thị Hồng', '0100 100 001', 'hong.parent@example.com'),
  ('Lý Văn Sơn',   '0100 100 003', null),
  ('Mai Thị Lụa',  '0100 100 009', null),
  ('Kiều Văn Tâm', '0100 100 011', null);
insert into crm.student_guardian (student_id, guardian_id, relationship_code, is_primary_contact, is_payer)
select cu.student_id, g.guardian_id, v.rel, true, true from (values
  ('C01', 'Ngô Thị Hồng', 'MOTHER'), ('C02', 'Ngô Thị Hồng', 'MOTHER'),     -- siblings share one guardian
  ('C03', 'Lý Văn Sơn', 'FATHER'), ('C09', 'Mai Thị Lụa', 'MOTHER'), ('C11', 'Kiều Văn Tâm', 'FATHER')
) as v(cref, gname, rel) join crm.student cu on cu.legacy_ref = v.cref join crm.guardian g on g.full_name = v.gname;

insert into crm.student_availability (student_id, weekday, time_band)
select cu.student_id, v.wd, v.band from (values ('C01',1,'EVENING'),('C01',3,'EVENING'),('C06',1,'EVENING'),('C06',3,'EVENING'),('C06',5,'EVENING'))
as v(cref, wd, band) join crm.student cu on cu.legacy_ref = v.cref;

insert into crm.lead (student_id, lead_date, owner_employee_id, channel_code, referred_by_student_id, programme_code, delivery_mode_code,
                      stage_code, qualification_code, consultation_outcome_code, lost_reason_code, recommended_course_id, closed_on, legacy_ref)
select cu.student_id, v.lead_d::date, (select employee_id from hr.employee where employee_code = v.owner), v.channel,
       (select student_id from crm.student where legacy_ref = v.referrer), v.prog, 'OFFLINE', v.stage, v.qual, v.outcome, v.lost,
       (select course_id from ref.course where course_code = v.course), v.closed::date, 'L-' || v.cref
from (values
  ('C01','2024-12-20','E002','SOCIAL_MEDIA',      null, 'AE',   'TESTED',      'CONVERTED',      'SUCCESS',              null,    'L1',       '2025-01-05'),
  ('C02','2024-12-20','E002','REFERRAL_FRIEND',   'C01','AE',   'TESTED',      'CONVERTED',      'SUCCESS',              null,    'L1',       '2025-01-05'),
  ('C03','2024-12-28','E002','EVENT',             null, 'AE',   'TESTED',      'CONVERTED',      'SUCCESS',              null,    'L1',       '2025-01-10'),
  ('C04','2025-02-10','E003','SCHOOL_PARTNERSHIP',null, 'IELTS','TESTED',      'CONVERTED',      'SUCCESS',              null,    'PROGRESS', '2025-02-25'),
  ('C05','2025-02-12','E003','SCHOOL_PARTNERSHIP',null, 'IELTS','TESTED',      'CONVERTED',      'SUCCESS',              null,    'PROGRESS', '2025-02-26'),
  ('C06','2025-05-05','E002','ONLINE_ADS',        null, 'COMM', 'TESTED',      'CONVERTED',      'SUCCESS',              null,    'A1',       '2025-05-20'),
  ('C07','2025-05-12','E003','SOCIAL_MEDIA',      null, 'COMM', 'TESTED',      'CONVERTED',      'SUCCESS',              null,    'A1',       '2025-05-28'),
  ('C08','2025-06-01','E003','MOCK_TEST',         null, 'IELTS','TESTED',      'CONVERTED',      'SUCCESS',              null,    'PRO',      '2025-06-20'),
  ('C09','2025-04-25','E002','WALK_IN',           null, 'AE',   'TESTED',      'CONVERTED',      'SUCCESS',              null,    'S1',       '2025-05-10'),
  ('C10','2025-05-20','E002','REFERRAL_TEACHER',  null, 'COMM', 'NEW',         'CONVERTED',      'SUCCESS',              null,    'A1',       '2025-05-30'),  -- >> CONTROL DEMO (SAL-02): enrolled without a test
  ('C11','2025-06-10',null,  null,                null, 'AE',   'TEST_BOOKED', 'HIGH_POTENTIAL', 'PENDING',              null,    null,       null)           -- >> CONTROL DEMO (SAL-01): no owner / channel
) as v(cref, lead_d, owner, channel, referrer, prog, stage, qual, outcome, lost, course, closed)
join crm.student cu on cu.legacy_ref = v.cref;

-- one lost lead to show lost reasons
insert into crm.student (full_name, gender, grade_label, first_contact_date, legacy_ref) values ('Phan Nhật Minh', 'MALE', 'Grade 10', '2025-03-01', 'C12');
insert into crm.lead (student_id, lead_date, owner_employee_id, channel_code, programme_code, stage_code, qualification_code,
                      consultation_outcome_code, lost_reason_code, lost_reason_note, closed_on, legacy_ref)
select student_id, '2025-03-01', (select employee_id from hr.employee where employee_code = 'E003'), 'SOCIAL_MEDIA', 'IELTS',
       'DECLINED_APPOINTMENT', 'NOT_A_PROSPECT', 'PRICE_NOT_SUITABLE', 'PRICE', 'Chose a cheaper online course', '2025-03-08', 'L-C12'
from crm.student where legacy_ref = 'C12';

insert into crm.lead_activity (lead_id, activity_type, activity_at, employee_id, outcome_code, note)
select l.lead_id, v.t, v.at::timestamptz, (select employee_id from hr.employee where employee_code = v.emp), v.outcome, v.note
from (values
  ('L-C11', 'CALL', '2025-06-12 10:00+07', 'E002', 'NO_ANSWER', 'Called twice, no answer'),
  ('L-C11', 'CHAT', '2025-06-13 19:30+07', 'E002', 'PENDING',   'Parent asked for weekend schedule; test booked for 5 July'),
  ('L-C12', 'CALL', '2025-03-02 09:00+07', 'E003', 'PRICE_NOT_SUITABLE', 'Price above budget')
) as v(lref, t, at, emp, outcome, note) join crm.lead l on l.legacy_ref = v.lref;

insert into crm.placement_test (lead_id, test_type, scheduled_at, status, assessed_by, overall_level_id, completed_at)
select l.lead_id, v.ttype, v.at::timestamptz, case when v.lvl is null then 'BOOKED' else 'COMPLETED' end,
       (select employee_id from hr.employee where employee_code = 'E008'),
       (select level_id from ref.proficiency_level where scale_code = v.scale and level_code = v.lvl),
       case when v.lvl is not null then v.at::timestamptz + interval '90 minutes' end
from (values
  ('L-C01','APPLIED_ENGLISH','2024-12-29 09:30+07','CEFR','A1-'), ('L-C02','APPLIED_ENGLISH','2024-12-29 09:30+07','CEFR','A1-'),
  ('L-C03','APPLIED_ENGLISH','2025-01-04 09:30+07','CEFR','A1-'), ('L-C04','IELTS','2025-02-16 09:30+07','IELTS','5.0'),
  ('L-C05','IELTS','2025-02-16 09:30+07','IELTS','5.0'),           ('L-C06','COMMUNICATION','2025-05-11 18:00+07','CEFR','A1'),
  ('L-C07','COMMUNICATION','2025-05-18 18:00+07','CEFR','A1+'),    ('L-C08','IELTS','2025-06-08 09:30+07','IELTS','6.5'),
  ('L-C09','APPLIED_ENGLISH','2025-05-04 09:30+07','CEFR','A1-'),  ('L-C11','APPLIED_ENGLISH','2025-07-05 09:30+07','CEFR',null)
) as v(lref, ttype, at, scale, lvl) join crm.lead l on l.legacy_ref = v.lref;

insert into crm.placement_test_score (test_id, skill_code, level_id)
select t.test_id, v.skill, (select level_id from ref.proficiency_level where scale_code = 'IELTS' and level_code = v.lvl)
from (values ('L-C04','READING','5.5'),('L-C04','LISTENING','5.0'),('L-C04','WRITING','4.5'),('L-C04','SPEAKING','5.0'),
             ('L-C08','READING','7.0'),('L-C08','LISTENING','6.5'),('L-C08','WRITING','6.0'),('L-C08','SPEAKING','6.5'))
as v(lref, skill, lvl) join crm.lead l on l.legacy_ref = v.lref join crm.placement_test t on t.lead_id = l.lead_id;

/* ------------------------------------------------------------------ enrolments, discounts, pricing, schedules */
insert into billing.group_registration (group_code, registered_on, tier_code, note) values
  ('GRP-2025-001', '2025-01-05', 'GROUP_2', 'Siblings C01 + C02');

insert into billing.enrollment (student_id, lead_id, course_id, delivery_mode_code, class_id, enrolled_on, sales_owner_employee_id,
                                plan_code, course_price_id, list_price, group_id, output_commitment_level_id, status_code, status_changed_on, legacy_ref)
select cu.student_id, l.lead_id, co.course_id, 'OFFLINE', cl.class_id, v.enr::date, (select employee_id from hr.employee where employee_code = v.owner),
       v.plan, pr.course_price_id, pr.amount,
       (select group_id from billing.group_registration where group_code = v.grp),
       (select level_id from ref.proficiency_level where scale_code = v.scale and level_code = v.target),
       v.status, coalesce(v.status_d, v.enr)::date, 'EN-' || v.cref
from (values
  ('C01','L1',      'AE_L1_150125',       '2025-01-05','E002','FULL',      'GRP-2025-001','CEFR', 'A1',  'COMPLETED', null),
  ('C02','L1',      'AE_L1_150125',       '2025-01-05','E002','P50_30_20', 'GRP-2025-001','CEFR', 'A1',  'COMPLETED', null),
  ('C03','L1',      'AE_L1_150125',       '2025-01-10','E002','MONTHLY_5', null,          'CEFR', 'A1',  'DROPPED',  '2025-04-15'),  -- >> CONTROL DEMO (BIL-06)
  ('C04','PROGRESS','IE_PROGRESS_030325', '2025-02-25','E003','FULL',      null,          'IELTS','6.0', 'COMPLETED', null),
  ('C05','PROGRESS','IE_PROGRESS_030325', '2025-02-26','E003','P50_30_20', null,          'IELTS','6.0', 'COMPLETED', null),
  ('C06','A1',      'COM_A1_020625',      '2025-05-20','E002','FULL',      null,          'CEFR', 'A2',  'ACTIVE',    null),
  ('C07','A1',      'COM_A1_020625',      '2025-05-28','E003','MONTHLY_3', null,          'CEFR', 'A2',  'ACTIVE',    null),
  ('C08','PRO',     'IE_PRO_010725',      '2025-06-20','E003','FULL',      null,          'IELTS','7.0', 'REGISTERED',null),
  ('C09','S1',      null,                 '2025-05-10','E002','FULL',      null,          'CEFR', 'A1',  'WAITLISTED',null),  -- >> CONTROL DEMO (BIL-07)
  ('C10','A1',      'COM_A1_020625',      '2025-05-30','E002','FULL',      null,          'CEFR', 'A2',  'ACTIVE',    null)
) as v(cref, course, class, enr, owner, plan, grp, scale, target, status, status_d)
join crm.student cu on cu.legacy_ref = v.cref
left join crm.lead l on l.legacy_ref = 'L-' || v.cref
join ref.course co on co.course_code = v.course
left join academic.class cl on cl.class_code = v.class
cross join lateral billing.current_price(co.course_id, 'OFFLINE', 'FULL_COURSE', v.enr::date) pr;

insert into billing.enrollment_discount (enrollment_id, seq, discount_code, discount_kind, discount_value, reason, approved_by,
                                         approval_status, requested_by, decided_at)
select e.enrollment_id, v.seq, v.code, dp.discount_kind, dp.discount_value, v.reason, (select employee_id from hr.employee where employee_code = v.approver),
       case when v.approver is not null then 'APPROVED' when dp.requires_approval or dp.discount_value > 0.30 then 'PENDING' else 'NOT_REQUIRED' end,
       e.sales_owner_employee_id, case when v.approver is not null then e.enrolled_on::timestamptz end
from (values
  ('EN-C01', 1, 'EARLY_BIRD_10',     'Registered before 10 January', null),
  ('EN-C04', 1, 'SCHOLARSHIP_70',    'Top score at partner-school mock test', 'E001'),
  ('EN-C05', 1, 'PARTNER_SCHOOL_30', 'City High School student', null),           -- >> CONTROL DEMO (BIL-05): scholarship without approval
  ('EN-C07', 1, 'SALES_TACTIC_5',    'Closing offer', null)
) as v(eref, seq, code, reason, approver)
join billing.enrollment e on e.legacy_ref = v.eref join ref.discount_programme dp on dp.discount_code = v.code;

select billing.price_enrollment(enrollment_id) from billing.enrollment order by enrollment_id;

-- Deposits of 500,000 for C01, C06, C08, C09; the rest pay from the first instalment
select billing.generate_payment_schedule(e.enrollment_id,
         case when e.legacy_ref in ('EN-C01','EN-C06','EN-C08','EN-C09') then billing.fee_amount('STANDARD_DEPOSIT', e.enrolled_on) end)
from billing.enrollment e order by enrollment_id;

/* ------------------------------------------------------------------ receipts and allocations */
insert into billing.receipt (receipt_no, receipt_date, student_id, enrollment_id, payer_guardian_id, payer_name, amount, payment_method_code, collected_by, legacy_ref)
select v.no, v.d::date, cu.student_id, (select enrollment_id from billing.enrollment where legacy_ref = v.eref), (select guardian_id from crm.guardian where full_name = v.guardian), coalesce(v.guardian, cu.full_name),
       v.amount, v.method, (select employee_id from hr.employee where employee_code = v.cashier), v.eref
from (values
  ('PT0001','2025-01-05','C01', 'Ngô Thị Hồng', 500000,  'CASH',          'E002', 'EN-C01'),
  ('PT0002','2025-01-15','C01', 'Ngô Thị Hồng', 3350000, 'BANK_TRANSFER', 'E002', 'EN-C01'),
  ('PT0003','2025-01-15','C02', 'Ngô Thị Hồng', 2350000, 'BANK_TRANSFER', 'E002', 'EN-C02'),
  ('PT0004','2025-02-17','C02', 'Ngô Thị Hồng', 1290000, 'BANK_TRANSFER', 'E002', 'EN-C02'),
  ('PT0005','2025-03-15','C02', 'Ngô Thị Hồng', 860000,  'BANK_TRANSFER', 'E002', 'EN-C02'),
  ('PT0006','2025-01-15','C03', 'Lý Văn Sơn',   1100000, 'CASH',          'E002', 'EN-C03'),
  ('PT0007','2025-02-15','C03', 'Lý Văn Sơn',   900000,  'CASH',          'E002', 'EN-C03'),
  ('PT0008','2025-03-17','C03', 'Lý Văn Sơn',   900000,  'CASH',          'E002', 'EN-C03'),
  ('PT0009','2025-03-03','C04', null,           1890000, 'BANK_TRANSFER', 'E003', 'EN-C04'),
  ('PT0010','2025-03-03','C05', null,           2405000, 'BANK_TRANSFER', 'E003', 'EN-C05'),
  ('PT0011','2025-04-03','C05', null,           1323000, 'BANK_TRANSFER', 'E003', 'EN-C05'),
  ('PT0012','2025-05-20','C06', null,           500000,  'CASH',          'E002', 'EN-C06'),
  ('PT0013','2025-06-02','C06', null,           3700000, 'BANK_TRANSFER', 'E002', 'EN-C06'),
  ('PT0014','2025-06-02','C07', null,           1557000, 'CASH',          'E003', 'EN-C07'),
  ('PT0015','2025-06-20','C08', null,           500000,  'CASH',          'E003', 'EN-C08'),
  ('PT0016','2025-05-10','C09', 'Mai Thị Lụa',  500000,  'CASH',          'E002', 'EN-C09'),
  ('PT0017','2025-06-02','C10', null,           4200000, 'BANK_TRANSFER', 'E002', 'EN-C10'),
  ('PT0018','2025-06-25','C02', 'Ngô Thị Hồng', 300000,  'CASH',          'E002', null)          -- >> CONTROL DEMO (BIL-04): advance payment, not allocated
) as v(no, d, cref, guardian, amount, method, cashier, eref)
join crm.student cu on cu.legacy_ref = v.cref;

select billing.allocate_receipt(r.receipt_id, e.enrollment_id)
from billing.receipt r join billing.enrollment e on e.legacy_ref = r.legacy_ref
order by r.receipt_date, r.receipt_no;

select billing.build_revenue_schedule(enrollment_id) from billing.enrollment order by enrollment_id;

-- Daily cash close by each collector (the learning advisors count the drawer at the end of the day)
insert into app.cash_close (close_date, collector_id, expected_cash, expected_transfer, counted_cash, note, reviewed_by, reviewed_at)
select r.receipt_date, r.collected_by,
       coalesce(sum(r.amount) filter (where r.payment_method_code = 'CASH'), 0),
       coalesce(sum(r.amount) filter (where r.payment_method_code <> 'CASH'), 0),
       coalesce(sum(r.amount) filter (where r.payment_method_code = 'CASH'), 0), null,
       (select employee_id from hr.employee where employee_code = 'E001'), r.receipt_date + time '19:00'
from billing.receipt r
where r.receipt_date < '2025-06-25'                      -- >> CONTROL DEMO (BIL-09): the cash taken on 25 June was never closed
group by r.receipt_date, r.collected_by;

/* ------------------------------------------------------------------ commission, refund */
-- Commissions are accrued by payroll.calculate_run from the commission rule (3% of net tuition when fully paid).
-- >> CONTROL DEMO (PAY-02): a manual commission keyed for C05, who has not paid in full
insert into payroll.commission (enrollment_id, employee_id, amount, earned_period_id)
select e.enrollment_id, e.sales_owner_employee_id, 100000, finance.period_of(e.enrolled_on)
from billing.enrollment e where e.legacy_ref = 'EN-C05';

/* ------------------------------------------------------------------ vendors, expense claim, vouchers */
insert into finance.vendor (vendor_name, vendor_type, tax_code, default_account_code) values
  ('Private landlord (centre premises)', 'INDIVIDUAL',  null,         'E7.012'),
  ('Provincial power company',           'UTILITY',     '0100000001', 'E7.007'),
  ('Telecom provider',                   'COMPANY',     '0100000002', 'E7.016'),
  ('Book store',                         'COMPANY',     '0100000003', 'E8.001'),
  ('Online ads platform',                'MARKETPLACE', null,         'E8.036'),
  ('Electronics store',                  'COMPANY',     '0100000004', 'E3.001'),
  ('Online marketplace',                 'MARKETPLACE', null,         'E2.002');

insert into finance.expense_claim (claim_no, employee_id, cost_center_code, submitted_on, status, approved_by, approved_on)
select 'CLM-2025-001', employee_id, '921012', '2025-04-08', 'PAID', (select employee_id from hr.employee where employee_code = 'E001'), '2025-04-09'
from hr.employee where employee_code = 'E002';
insert into finance.expense_claim_line (claim_id, line_no, transaction_date, description, business_purpose, vendor_name, amount_excl_vat, vat_code)
select claim_id, 1, '2025-04-07', 'Printing of placement-test papers', 'Mock test day', 'Copy shop', 85000, 'i0'
from finance.expense_claim where claim_no = 'CLM-2025-001';

-- Voucher headers + lines (monthly running costs Jan-Jun 2025 and one-off items)
with months as (select generate_series('2025-01-01'::date, '2025-06-01'::date, interval '1 month')::date as m),
running as (
    select 'RENT' as kind, m, 'Private landlord (centre premises)' as vendor, 'Office rent ' || to_char(m, 'Mon YYYY') as descr, 13000000 as amt, 'i0' as vat, 'E7.012' as acc, '921011' as cc, false as inv from months
    union all select 'POWER', m, 'Provincial power company', 'Electricity ' || to_char(m, 'Mon YYYY'), 1650000 + 50000 * extract(month from m)::int, 'i10', 'E7.007', '921011', true from months
    union all select 'NET', m, 'Telecom provider', 'Internet ' || to_char(m, 'Mon YYYY'), 300000, 'i10', 'E7.016', '921011', true from months
    union all select 'ADS', m, 'Online ads platform', 'Facebook ads ' || to_char(m, 'Mon YYYY'), 1500000 + 250000 * (extract(month from m)::int % 3), 'i0', 'E8.036', '921014', true from months),
numbered as (select r.*, row_number() over (order by m, kind) as n from running r),
hdr as (
    insert into finance.payment_voucher (voucher_no, voucher_date, requested_by, approved_by, payee_vendor_id, funding_source, payment_method_code, has_invoice, legacy_ref)
    select 'PC' || lpad(n::text, 4, '0'), (m + 4), (select employee_id from hr.employee where employee_code = 'E002'),
           (select employee_id from hr.employee where employee_code = 'E001'),
           (select vendor_id from finance.vendor where vendor_name = vendor), 'COMPANY_ACCOUNT', 'BANK_TRANSFER', inv, kind
    from numbered returning voucher_id, voucher_no)
insert into finance.payment_voucher_line (voucher_id, line_no, description, amount_excl_vat, vat_code, recognition_period_id, cost_center_code, account_code)
select h.voucher_id, 1, n.descr, n.amt, n.vat, finance.period_of(n.m), n.cc, n.acc
from numbered n join hdr h on h.voucher_no = 'PC' || lpad(n.n::text, 4, '0');

insert into finance.payment_voucher (voucher_no, voucher_date, requested_by, approved_by, payee_vendor_id, payee_employee_id, funding_source,
                                     payment_method_code, has_invoice, claim_id, notes)
select v.no, v.d::date, (select employee_id from hr.employee where employee_code = v.req), (select employee_id from hr.employee where employee_code = 'E001'),
       (select vendor_id from finance.vendor where vendor_name = v.vendor), (select employee_id from hr.employee where employee_code = v.payee_emp),
       v.src, v.method, v.inv, (select claim_id from finance.expense_claim where claim_no = v.claim), v.note
from (values
  ('PC0101','2025-01-10','E008','Book store',         null,  'COMPANY_ACCOUNT','BANK_TRANSFER', true,  null,           'Student books Leaf 1'),
  ('PC0102','2025-01-10','E001','Electronics store',  null,  'COMPANY_ACCOUNT','BANK_TRANSFER', true,  null,           'Projector for Room 101'),
  ('PC0103','2025-03-05','E001','Electronics store',  null,  'PETTY_CASH',     'CASH',          true,  null,           'Webcam for hybrid room'),        -- >> CONTROL DEMO (EXP-02)
  ('PC0104','2025-04-09','E002',null,                 'E002','PETTY_CASH',     'CASH',          false, 'CLM-2025-001', 'Reimbursement CLM-2025-001'),
  ('PC0105','2025-05-15','E007','Online marketplace', null,  'PETTY_CASH',     'CASH',          false, null,           'Stationery'),
  ('PC0106','2025-06-03','E008','Book store',         null,  'COMPANY_ACCOUNT','BANK_TRANSFER', true,  null,           'Student books Communication A1'),
  ('PC0107','2025-06-10','E002','Online marketplace', null,  'PETTY_CASH',     'CASH',          false, null,           'Coded to a header account')     -- >> CONTROL DEMO (EXP-03)
) as v(no, d, req, vendor, payee_emp, src, method, inv, claim, note);

insert into finance.payment_voucher_line (voucher_id, line_no, description, business_purpose, amount_excl_vat, vat_code, recognition_period_id,
                                          cost_center_code, account_code, class_id)
select pv.voucher_id, 1, v.descr, v.purpose, v.amt, v.vat, v.period, v.cc, v.acc, (select class_id from academic.class where class_code = v.class)
from (values
  ('PC0101','Leaf 1 student books x 12',       'Course materials',  1680000, 'i0',  202501, '921016', 'E8.001', 'AE_L1_150125'),
  ('PC0102','Projector + installation',         'Classroom equipment',9000000, 'i10', 202501, '921011', 'E3.001', null),
  ('PC0103','USB webcam',                       'Hybrid teaching',    1500000, 'i10', 202503, '921011', 'E3.001', null),
  ('PC0104','Printing of placement-test papers','Mock test day',      85000,   'i0',  202504, '921012', 'E8.005', null),
  ('PC0105','Pens, folders and markers',        'Office supplies',    240000,  'i0',  202505, '921011', 'E2.002', null),
  ('PC0106','Communication A1 books x 3',       'Course materials',   450000,  'i0',  202506, '921015', 'E8.001', 'COM_A1_020625'),
  ('PC0107','Snacks for teachers',              'Staff refreshment',  180000,  'i0',  202506, '921013', 'E1.001', null)
) as v(no, descr, purpose, amt, vat, period, cc, acc, class)
join finance.payment_voucher pv on pv.voucher_no = v.no;

-- Refund: one cancelled Communication session refunded to C07 (contra-revenue)
insert into finance.payment_voucher (voucher_no, voucher_date, requested_by, approved_by, payee_vendor_id, payee_employee_id, funding_source, payment_method_code, has_invoice, notes)
select 'PC0108', '2025-06-27', employee_id, employee_id, null, employee_id, 'PETTY_CASH', 'CASH', false, 'Refund paid via LA to learner C07'
from hr.employee where employee_code = 'E001';
select billing.record_refund(e.enrollment_id, '2025-06-27', 100000, 'Session cancelled by the centre on 13 June',
                             (select employee_id from hr.employee where employee_code = 'E001'), true,
                             (select voucher_id from finance.payment_voucher where voucher_no = 'PC0108'))
from billing.enrollment e where e.legacy_ref = 'EN-C07';

/* ------------------------------------------------------------------ fixed asset and depreciation */
insert into finance.fixed_asset (asset_code, asset_name, capex_account_code, charge_account_code, cost_center_code, voucher_line_id,
                                 acquisition_date, cost, useful_life_months, first_charge_period_id)
select 'FA-0001', 'Projector - Room 101', 'E3.001', 'E3.004', '921011', vl.voucher_line_id, '2025-01-10', vl.amount_incl_vat, 36, 202501
from finance.payment_voucher_line vl join finance.payment_voucher v using (voucher_id) where v.voucher_no = 'PC0102';
select finance.generate_depreciation(asset_id) from finance.fixed_asset;

/* ------------------------------------------------------------------ manual journal (accrual only) */
insert into finance.journal_entry (entry_no, period_id, entry_date, basis, entry_type, description, posted_by)
select 'JE-2025-0001', 202506, '2025-06-30', 'ACCRUAL_ONLY', 'ACCRUAL', 'Accrue Q2 bookkeeping and audit fee', employee_id
from hr.employee where employee_code = 'E001';
insert into finance.journal_line (journal_entry_id, line_no, account_code, cost_center_code, debit, credit, memo)
select journal_entry_id, 1, 'E7.001', '921010', 1500000, 0, 'Audit fee Q2' from finance.journal_entry where entry_no = 'JE-2025-0001'
union all
select journal_entry_id, 2, 'B2.201', null, 0, 1500000, 'Accrued expenses' from finance.journal_entry where entry_no = 'JE-2025-0001';

/* ------------------------------------------------------------------ payroll Jan-Jun 2025 */
insert into payroll.payroll_run (period_id, run_type) select period_id, 'REGULAR' from finance.fiscal_period where period_id between 202501 and 202506;
insert into payroll.payroll_line (run_id, employee_id, earning_type_code, amount, source_type, account_code, cost_center_code, note)
select r.run_id, e.employee_id, v.et, v.amt, 'MANUAL', finance.earning_account(v.et, null, null, null), e.home_cost_center_code, v.note
from (values (202504, 'E002', 'ALLOW_PHONE', 200000, 'Phone allowance'), (202504, 'E007', 'ALLOW_LUNCH', 730000, 'Lunch allowance'),
             (202504, 'E004', 'NON_TEACHING_ACTIVITY', 300000, 'Mock-test invigilation')) as v(period, emp, et, amt, note)
join payroll.payroll_run r on r.period_id = v.period join hr.employee e on e.employee_code = v.emp;
select payroll.calculate_run(run_id) from payroll.payroll_run order by period_id;
update payroll.payroll_run set status = 'PAID', approved_by = (select employee_id from hr.employee where employee_code = 'E001'),
       approved_at = now(), paid_on = (select period_end from finance.fiscal_period p where p.period_id = payroll.payroll_run.period_id) + 5
where period_id < 202506;
update payroll.commission c set status = 'PAID' from payroll.payroll_run r where r.run_id = c.run_id and r.status = 'PAID';

/* ------------------------------------------------------------------ application users (password: demo) */
insert into app.app_user (username, full_name, role_code, employee_id, password_hash)
select v.u, e.full_name, v.r, e.employee_id, extensions.crypt('demo', extensions.gen_salt('bf', 8))
from (values ('la.ha', 'E002', 'LEARNING_ADVISOR'), ('academic.manager', 'E008', 'ACADEMIC_MANAGER'),
             ('hr.manager', 'E001', 'HR_MANAGER'), ('finance.manager', 'E001', 'FINANCE_MANAGER')) as v(u, emp, r)
join hr.employee e on e.employee_code = v.emp;

/* ------------------------------------------------------------------ close January and run the controls */
update finance.fiscal_period set status = 'CLOSED', closed_at = '2025-02-10' where period_id <= 202501;   -- books opened June 2024
select * from ctl.run_all_controls();
