# 02: Academic: course administration

**Workbook:** [`02_Learning_Course_Management.xlsx`](../workbooks/02_Learning_Course_Management.xlsx)
**Architecture blocks:** *Course Administration System*. Faculty assignment ✗ input · Course duration & learning schedule ✗ input

## Purpose

This workbook is the single register of every class that is open or about to open. Sales uses it to allocate students to classes. Payroll uses it to know which teacher and teaching assistant (TA) run which class. Finance uses the **course end date** to spread tuition revenue over the life of the course (see [module 05](05-pnl-revenue-recognition.md)).

## Sheets

| Sheet | Role |
|---|---|
| `Khoá học khai giảng` | Class register: one row per class |
| `AE_L1_240624`, `IE_PROGRESS_170624`, … | One roster sheet per class (sheet name = class code) |
| `Tổng quan` *(hidden)* | Programme overview: CEFR level ↔ course ↔ hours ↔ tuition |
| `Data Validation` *(hidden)* | Teacher and TA lists for drop-downs |
| `SW`, `Library` *(hidden)* | IELTS Speaking–Writing syllabus and a teaching-materials library |

## Class code convention

`<PROGRAMME>_<LEVEL>_<DDMMYY of opening>`. For example, `AE_L1_240624` = Applied English, *Leaf 1*, opened 24 June 2024. `IE_PROGRESS_170624` = IELTS *Progress 6.0+*. `COM_A1_220724` = Communication level 1.

The code is the key that links the class register, the student rosters, the billing sheet (*class allocation*) and the revenue-recognition sheet (*end day*).

## Class register logic

Inputs (✗): batch, class code, programme, course, **teacher**, **TA**, entry/exit level, total hours, hours per session, sessions per week, time slot, weekdays, start date, planned end date.

Calculated (✓):

```
Total sessions = Total hours / Hours per session
Total weeks    = Total sessions / Sessions per week
Total months   = Total weeks / 4
```

**Status** updates itself every day from `TODAY()`:

| Condition | Status shown |
|---|---|
| today < start − 10 days | Not started yet |
| start − 10 days ≤ today < start | Starts in *N* days |
| start ≤ today < end − 20 days | Running |
| end − 20 days ≤ today < end | Ends in *N* days |
| today ≥ end | Finished |

The 10-day and 20-day windows are operational triggers. The first prompts the team to confirm the class with students. The second prompts LAs to start re-enrolment conversations before the course ends.

## Class roster sheets

Each class sheet has a header block filled by `VLOOKUP` on the class code: status, number of students (`COUNTA`), teacher, TA, time slot, weekdays, start and end dates. Below it is the roster: student code, name, LA in charge, date of birth, school grade and **output commitment** (the target level promised at enrolment).

## Glossary

| Vietnamese | English |
|---|---|
| Khoá học khai giảng | Classes opening / open classes |
| Mã lớp | Class code |
| Giáo viên / Trợ giảng | Teacher / Teaching assistant |
| Trình độ đầu vào / đầu ra | Entry level / Exit level |
| Tổng số giờ học | Total course hours |
| Khung giờ / Thời gian biểu | Time slot / Weekly timetable |
| Ngày bắt đầu / Ngày dự kiến kết thúc | Start date / Planned end date |
| Cam kết đầu ra | Output (learning-outcome) commitment |
