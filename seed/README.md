# Demo dataset

`demo_dataset.sql` is a year of operations of a fictitious AMI Education campus, business date **31 October 2026**.
It is generated, not written: [`generate_dataset.py`](generate_dataset.py) walks the calendar from go-live (1 October 2025) one day
at a time and performs every business event through the database functions the application calls, signed in as the employee
who would do it (`ami.app_user`), so the audit trail reads like a real year.

| | |
|---|---|
| Staff | 13: director, finance, HR, academic manager (also teaches IELTS), 2 learning advisors, 5 teachers / assistants, marketing; one advisor passes probation, one teacher joins in month 5, one resigns two days before the business date |
| Classes | 46 over 13 timetable lanes (Applied English, Communication, IELTS, Practical English); level progressions, one online class cancelled for low enrolment, Tet and public holidays skipped |
| Sales | ~780 leads with activities and placement tests, lost reasons, ~540 enrolments (new and returning learners), discounts with Finance approvals and refusals |
| Money | ~1,700 receipts with prompt, late, partial and defaulting payers; voids and re-issues; daily cash closes with occasional differences; refunds; drop-outs, deferrals, cancellations, write-offs |
| Work and pay | 1,700 sessions confirmed weekly (a few cancelled and made up), advisor shifts, monthly payroll (calculate on the 2nd, approve on the 3rd, pay on the 5th), commissions, Tet bonus |
| Finance | monthly vouchers (rent, utilities, ads, books per class, cleaning, accounting), expense claims, opening capex depreciated, quarterly audit-fee accruals, a price increase, a pay-rate increase, twelve month-end closes |
| On the business date | website leads to assign, follow-ups and tests, overdue instalments, a void and a discount to approve, a cash day not closed and a difference to review, sessions to confirm, a class with no teacher, paid learners waiting for a class, the October payroll to calculate, a capital purchase to capitalise and a mis-coded expense |

```bash
createdb ami_gen
(cd database && psql -v ON_ERROR_STOP=1 -d ami_gen -f build.sql)
python seed/generate_dataset.py --dsn postgresql:///ami_gen --as-of 2026-10-31 [--seed 2025] [--password ami-demo]
bash seed/export_dataset.sh ami_gen > seed/demo_dataset.sql
```

The generator needs a local superuser (it disables triggers for the final step that moves every `now()` timestamp onto the simulated
calendar). The same seed and date always produce the same data. The export truncates and reloads every table with `COPY`, so loading it
again resets a demo; `deploy/reset_demo.sh` does both steps against a hosted database.

All names are invented Vietnamese names; phone numbers use the unassigned `0100` prefix; e-mail addresses use `example.com`.
