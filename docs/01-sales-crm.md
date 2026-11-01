# 01: Sales: CRM, enrolment and billing

**Workbook:** [`01_Customer_Management_Database.xlsx`](../workbooks/01_Customer_Management_Database.xlsx)
**Architecture blocks:** *Customer Master Database (CMD)* ✗ input · *Enrolment & Billing Database (EBD)* ✓ automated · *Receipts Management* ✗ input

## Purpose

This workbook tracks every prospective student from first contact to fully paid enrolment. It is used by the Learning Advisors (LA, the sales and student-care team). It answers three questions:
1. Where is each lead in the funnel, and who owns it?
2. What does each enrolled student owe, after discounts, and on which payment plan?
3. Which receipts have been collected against that plan, and what is still outstanding?

## Sheets

| Sheet | Role | Input / automated |
|---|---|---|
| `Customer Management Database` (table `AMI_CMD`) | Master record of every lead/student | ✗ input (LA) |
| `Qualified Leads` (table `Table2`) | Enrolment and billing record for leads who registered | Mostly ✓; course, discounts and plan are ✗ |
| `Receipts Management` (table `Table3`) | One row per receipt (`PT###`) | ✗ input (cashier) |
| `Receipt` | Printable receipt generated from a receipt number | ✓ |
| `Data validation` *(hidden)* | Drop-down lists: statuses, programmes, price list, discount programmes, payment plans | Reference |
| `Khoá học khai giảng` *(hidden)* | Snapshot of the class register from the Course Administration workbook | Reference |
| `Data scanning`, `Sheet2`, `Sheet3` *(hidden)* | PivotTables for funnel and channel analysis | ✓ |
| `Leads Qualification (2)` *(hidden)* | Earlier version of the billing sheet, kept for reference | n/a |

## 1. Customer Master Database (`AMI_CMD`)

One row per lead. Column groups:

| Group | Columns | Notes |
|---|---|---|
| Basic information | Customer code, student name, LA in charge, gender, DOB, phone, school, grade, email, programme of interest | Customer code is generated automatically: `="AMI"&STT` |
| Other information | Acquisition channel, parent name, relationship, parent phone and email, notes | Channel feeds the marketing analysis |
| Placement-test appointment | Day, date, time, **current status** | Status list: new lead → contacted → declined appointment → booked → tested / no-show |
| Placement-test results | Applied English (overall, grammar & vocabulary, writing, speaking), IELTS (overall, R/L/W/S), Communication | CEFR levels or IELTS bands |
| Lead qualification | Recommended course, **tuition (auto)**, consultation result, notes, **customer type** | Tuition = `VLOOKUP(recommended course, price list)` |
| Preferred schedule | Mon–Sun availability | Used to fill classes |

**Customer type** is the key funnel field. Its values are: low potential, high potential, registered, active student, not a prospect, completed course, dropped out mid-course, deferred.

## 2. Enrolment and billing (`Qualified Leads`)

The LA enters only the student name, class code, discount programmes and payment plan. Everything else is calculated:

```
Standard tuition   = price of the recommended course
                     (or the class price, once the student is assigned to a class)
Total tuition      = (1 − disc1% − disc2% − disc3%) × Standard tuition − group discount
Materials fee      = fixed fee if plan is "50-30-20" or "monthly", else 0
Total payable      = Total tuition + Materials fee
Deposit            = looked up from receipts: <customer code>-"Phí giữ chỗ"
Balance due        = Total payable − Deposit
```

### Payment plans

| Plan | Vietnamese | Receipt key suffix |
|---|---|---|
| Pay in full | Trả một lần | `-Hoàn thành học phí toàn khoá` |
| 50-30-20 instalments | Trả theo lộ trình 50-30-20 | `-Hoàn thành học phí theo lộ trình-50% học phí` / `30%` / `20%` |
| Monthly (up to 7 months) | Trả theo tháng | `-Hoàn thành học phí theo lộ trình-Giai đoạn 1` … `Giai đoạn 7` |

For each instalment the sheet shows the **planned** amount (input), the **paid** amount and the **payment date**. Paid amount and date are both looked up from `Receipts Management` using the composite key:

```excel
=IFERROR(VLOOKUP(
    IFS([@[Phương án thanh toán]]="Trả theo tháng",
            [@[Mã khách hàng]]&"-Hoàn thành học phí theo lộ trình-Giai đoạn 1",
        [@[Phương án thanh toán]]="Trả theo lộ trình 50-30-20",
            [@[Mã khách hàng]]&"-Hoàn thành học phí theo lộ trình-50% học phí"),
    'Receipts Management'!$D:$I, 6, 0), 0)
```

### Status columns

| Column | Logic |
|---|---|
| **Công nợ** (accounts receivable) | Balance due − everything collected. Forced to 0 for students who dropped out, deferred or are low potential |
| **Doanh thu** (collected revenue) | Deposit + full payment + all instalments collected |
| **Chi phí nợ xấu** (bad debt) | Outstanding balance written off when a student drops out or defers |
| **Tiến độ chung** (overall progress) | Fully paid / partially paid / customer type |
| **Ngày hoàn thiện học phí** (completion date) | Date of the final payment, depending on the plan |

## 3. Receipts Management and receipt generator

The cashier enters one row per receipt. Fields: receipt number `PT###`, collector, payer, student, date, amount, method (cash/transfer), payment type, instalment note, and whether materials are included. The sheet derives:

- **AMI Code** by looking up the student's customer code.
- **Code** (the composite key) `= AMI Code & "-" & payment type [& "-" & note]`. This is the key the billing sheet uses.
- **Course** by looking up the student's assigned course.

The `Receipt` sheet is a print template. Typing a receipt number into one cell fills in payer, student, course, method and the payment label (deposit / full course / instalment N). If materials were included, it shows the materials fee as a separate line.

## 4. Analysis

Hidden PivotTables on `AMI_CMD` and `Table2` break the funnel down by LA, customer type, acquisition channel, student grade and payment plan. `Data scanning` uses `GETPIVOTDATA` to group raw channels (e.g. *Facebook* + *social media*) into marketing buckets.

## Glossary

| Vietnamese | English |
|---|---|
| Học viên | Student |
| LA phụ trách | Learning Advisor in charge |
| Kiểm tra đầu vào | Placement test |
| Tình trạng hiện tại | Current status |
| Xác định loại khách hàng | Customer type |
| Tình trạng sắp lớp | Class allocation |
| Học phí tiêu chuẩn | Standard tuition |
| Chương trình giảm giá | Discount programme |
| Đăng ký theo nhóm | Group registration |
| Phí giữ chỗ | Deposit |
| Phương án thanh toán | Payment plan |
| Giai đoạn | Instalment |
| Công nợ | Accounts receivable |
| Phiếu thu | Receipt |
