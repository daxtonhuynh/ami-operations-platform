# 04: Finance: expense management

**Workbooks:** [`04_Payment_Control.xlsx`](../workbooks/04_Payment_Control.xlsx) → [`05_Profit_and_Loss.xlsx`](../workbooks/05_Profit_and_Loss.xlsx)
**Architecture blocks:** *Reimbursement System* ✗ input → *Expenses Management System*. Operating expenses ✓ · Staffing expenses ✓

## Purpose

Every payment leaving the company is recorded once, as a coded voucher. The coding is complete enough that the P&L can be produced automatically by month, by cost center and by expense category.

## Payment Control workbook

| Sheet | Role |
|---|---|
| `Payment Management` (table `Table3`) | Voucher register: one row per payment voucher `PC###` |
| `Expense Reimbursement Form` | Claim form staff fill in for out-of-pocket purchases (invoice, description, business purpose, vendor, amount, VAT group) |
| `Data Validation` | Drop-down lists. Cost centers and expense categories are pulled from the P&L workbook, so both files always share the same chart of accounts |
| `Payment` *(hidden)* | Printable voucher template |

### Voucher fields

Voucher no. · person in charge · transaction date · invoice no. · description · business purpose · payee · **amount excl. VAT** · **VAT group** · total incl. VAT · content · **expense recognition date** · **cost center** · **expense category** · source of funds.

```excel
Total incl. VAT = Amount × IF(VAT="i0",100%, IF(VAT="i8",108%, IF(VAT="i10",110%)))
```

Two dates are kept. The **transaction date** is when the cash moves. The **expense recognition date** is the month the cost belongs to. The P&L uses the recognition date.

### Cost centers

| Code | Department |
|---|---|
| 921010 | AMI Management |
| 921011 | AMI Central (shared facility costs) |
| 921012 | Learning Advisor Team |
| 921013 | Academic Team Central |
| 921014 | Marketing Team |
| 921015 / 921016 / 921017 | Communication / Applied English / IELTS programmes |

### Expense categories (about 130 codes)

| Group | Examples |
|---|---|
| E0 | Refunds & discounts (revenue deductions) |
| E1 | People: teacher and TA pay by programme, LA variable pay, fixed salaries, insurance, bonuses, placement tests |
| E2 | Paper and stationery |
| E3 | IT and office equipment, fit-out (with allocation lines) |
| E4 | Depreciation |
| E5 | Cambridge services, outsourcing |
| E6 | Bad debts |
| E7 | Rent, utilities, repairs, recruitment, audit, bank charges |
| E8 | Marketing, events, materials for students, travel, training, admin |

## How expenses reach the P&L

1. `Payment Control` (in the P&L workbook) is a mirror of the voucher register. In production it was a live SharePoint link; here it is a static snapshot.
2. `Payment Control_Pivot` sums **total incl. VAT** by expense category × **recognition month**.
3. `Expenses Management` lays out every P&L code by month (Oct 2024 to Dec 2025). Each cell uses
   ```excel
   =IFERROR(SUM(FILTER(INDEX(Pivot!$A:$AA, MATCH(code&" - "&category, Pivot!$A:$A, 0), ),
                       Pivot!$A$5:$AA$5 = D$4)), 0)
   ```
4. Payroll lines (teacher, TA/AT, LA, fixed salaries, foreign teachers, commission and overtime) come from `Salary Expense` with `FILTER(…, month = column month)`. That sheet is the monthly output of the [payroll workbook](03-payroll.md).

## Glossary

| Vietnamese | English |
|---|---|
| Phiếu chi | Payment voucher |
| Người phụ trách | Person in charge |
| Thời gian giao dịch | Transaction date |
| Thời gian ghi nhận chi phí | Expense recognition date |
| Mục đích kinh doanh | Business purpose |
| Thông tin bên nhận | Payee |
| Nhóm thuế | VAT group |
| Nguồn tiền | Source of funds |
