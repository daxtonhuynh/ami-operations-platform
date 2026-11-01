# 05: Finance: P&L, cash vs accrual, deferred revenue

**Workbook:** [`05_Profit_and_Loss.xlsx`](../workbooks/05_Profit_and_Loss.xlsx)
**Architecture blocks:** *Accrual-based P&L*. Deferred revenue ✓ · Total expenses ✓. *Cash-based P&L*. Cashflow recognition ✓ · Total expenses ✓

## Why two P&Ls?

Students often pay for a whole course, or 50% of it, before the course starts. On a **cash basis** that month looks very profitable and the following months look like losses. On an **accrual basis** the tuition is earned as the course is delivered. The gap between the two is **deferred revenue**: cash already received for teaching not yet delivered. This is effectively a liability to students.

Running both views side by side answered two questions every month:
- *Can we pay our bills?* (cash P&L)
- *Is the centre actually profitable?* (accrual P&L, plus how much future teaching is pre-funded)

## Sheet map

| Layer | Sheets |
|---|---|
| Master data | `Expense Category` (about 130 codes), `Revenue Category` *(hidden)*, `Product Lines` *(hidden)*, `Cost Center` *(hidden)* |
| Inputs (snapshots of other workbooks) | `Payment Control` (vouchers), `Receipt Control` (receipts), `Salary Expense` (monthly payroll), `CMD.copy.source` + `Receipt` (receipts from the v4 CRM layout) |
| Aggregation | `Payment Control_Pivot`, `Receipt Control_Pivot`, `Receipt Control_Pivot_Accrual` *(PivotTables)* |
| Management views | `Expenses Management`, `Order Intake Mgmt_Cashflow`, `Order Intake Mgmt_Accrual` |
| Statements | `Profit and Loss_Cashflow` (Oct 2024 to Dec 2025), `Profit and Loss_Accrual` (Apr to Dec 2025), `Deferred Revenue Balance` |

## Revenue codes

Revenue is coded by **programme × delivery mode**:

| Programme | Offline | Online | Customised (1:1) | Customised online |
|---|---|---|---|---|
| Applied English (AE) | I1.0011 | I1.0014 | I1.0017 | I1.00110 |
| Communication (COMM) | I1.0012 | I1.0015 | I1.0018 | I1.00111 |
| IELTS | I1.0013 | I1.0016 | I1.0019 | I1.00112 |
| Practical English (PE) | I1.00113 | | | |

`Receipt Control` maps each receipt's course to its revenue code through `Product Lines`. It also brings in the **course end date** of the student's class from the course register ([module 02](02-course-administration.md)).

## Revenue recognition rule (accrual view)

Each receipt is spread across monthly columns (Apr to Dec 2025):

| Receipt type | Recognition |
|---|---|
| Full-course payment, or a 50% / 30% / 20% instalment | Spread **evenly** from the payment month to the course end month: `amount / (months between payment month and end month + 1)` |
| Deposit, or a monthly instalment | Recognised **in the month received** |
| Any payment received after the course has ended | Recognised **in full in the month received** |

Implemented per receipt × month as:

```excel
=IF(TEXT(R$2,"yyyymm")=TEXT($G3,"yyyymm"),                 ' payment month
    IF($G3>$Q3, $I3,                                         '   paid after course end
       IF(OR($K3="Hoàn thành học phí toàn khoá",
             AND($K3="Hoàn thành học phí theo lộ trình",
                 OR($L3="50% học phí",$L3="30% học phí",$L3="20% học phí"))),
          $I3/(DATEDIF(DATE(YEAR($G3),MONTH($G3),1),$Q3,"m")+1),
          $I3)),
    IF(AND(R$2>$G3, R$2<=$Q3, <spread-type receipt>),          ' later months up to end
       $I3/(DATEDIF(DATE(YEAR($G3),MONTH($G3),1),$Q3,"m")+1),
       0))
```
`G` = receipt date · `Q` = course end date · `I` = amount · `K` = payment type · `L` = instalment note.

`Receipt Control_Pivot` sums receipts by revenue code × receipt month, which gives **cash** revenue. `Receipt Control_Pivot_Accrual` sums the monthly columns above, which gives **accrual** revenue. The two `Order Intake` sheets lay each one out by revenue code and month. Accrual tracking starts in April 2025, so the accrual view uses cash figures for earlier months and the accrual P&L covers April to December 2025.

## P&L structure (both views)

```
REVENUE (by product line)
− Revenue deductions (refunds & discounts)
= TOTAL REVENUE AFTER DEDUCTIONS
− COST OF SALES
    Teaching cost (teachers by programme, insurance, expat teachers, overtime, training, placement tests)
    TA/AT cost (by programme)
    Non-teaching academic cost
    Programme & delivery costs (materials, Cambridge services, school partnerships, outsourcing)
= GROSS MARGIN                                   (+ % of revenue)
− STAFF COSTS (variable LA pay, fixed salaries, insurance, benefits, training, recruitment)
− MARKETING COSTS (campaign, fixed, local marketing)
− ESTABLISHMENT COSTS (depreciation, rent, utilities, IT, fit-out, maintenance)
− ADMINISTRATION COSTS (travel, telecoms, stationery, fees, sundry)
= EBIT                                           (+ % of revenue)
+ Depreciation
= EBITDA
```

Revenue lines come from the matching `Order Intake` sheet. Expense lines come from `Expenses Management`, matched on P&L code and month with `FILTER(INDEX(MATCH))`, so both statements share exactly the same cost base.

## Deferred Revenue Balance

For each month and programme:

| Line | Formula |
|---|---|
| Cash revenue | from `Order Intake Mgmt_Cashflow` |
| Accrual revenue | from `Order Intake Mgmt_Accrual` |
| **Deferred revenue** | Cash − Accrual |
| **Accrual-to-cash ratio** | Accrual ÷ Cash (a low ratio means most of the month's cash pays for future teaching) |
| Total expenses (COGS + OPEX) | from `Expenses Management` |
| **Deferred revenue coverage** | Deferred revenue − Total expenses, plus the ratio Deferred revenue ÷ Total expenses: how much of the month's cost base is funded by pre-collected tuition |

## Receipts from the v4 CRM (`CMD.copy.source` → `Receipt`)

A later version of the CRM (v4) used a wider layout: one row per student, with up to six instalments, each with its own receipt number, collector, method and date. `CMD.copy.source` mirrors that sheet. `Receipt` turns it back into a one-row-per-receipt list. For receipt number `PT###` it finds which of the seven receipt-number columns contains it and returns the matching student, class, amount, collector and date:

```excel
=INDEX('CMD.copy.source'!B:B,
   MATCH(TRUE, ISNUMBER(MATCH(A2, CHOOSE({1,2,3,4,5,6,7},
        'CMD.copy.source'!K:K, 'CMD.copy.source'!P:P, 'CMD.copy.source'!U:U, …), 0)), 0))
```
