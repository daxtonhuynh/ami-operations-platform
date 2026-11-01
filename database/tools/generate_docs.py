#!/usr/bin/env python3
"""Generate the data-model documentation from a live database built with build.sql.

    python3 tools/generate_docs.py --db ami            # uses psql on PATH (PG* env vars respected)

Writes
    docs/DATA_DICTIONARY.md   every schema, table, column, constraint, index, trigger, view and function
    docs/ERD.md               Mermaid ER diagrams: core model + one diagram per business module
    docs/erd/*.mmd            the same diagrams as standalone Mermaid files (render with mmdc)

Everything comes from the PostgreSQL catalog, so the documentation cannot drift from the DDL.
"""
import argparse
import json
import pathlib
import re
import subprocess
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SCHEMAS = ["ref", "crm", "academic", "billing", "hr", "payroll", "finance", "ctl", "rpt", "app"]
SCHEMA_TITLES = {
    "ref": "Reference & master data", "crm": "Sales & CRM", "academic": "Academic operations",
    "billing": "Order-to-cash", "hr": "Human resources", "payroll": "Payroll", "finance": "Finance & accounting",
    "ctl": "Controls", "rpt": "Reporting views", "app": "Application: users, audit trail, cash close",
}
AUDIT_COLUMNS = {"created_at", "updated_at", "legacy_ref", "notes", "note"}

# "Who did it" columns (approver, collector, poster ...) reference hr.employee from almost every table.
# They are real foreign keys (marked FK in the diagrams) but their lines are left out of the pictures to keep them readable.
ACTOR_COLUMNS = {"approved_by", "confirmed_by", "changed_by", "assessed_by", "collected_by", "requested_by",
                 "posted_by", "executed_by", "assigned_to"}

# Business modules for the ER diagrams: (slug, title, intro, own tables drawn in full, context tables drawn with their key only)
MODULES = [
    ("sales-crm", "Sales & CRM - leads, funnel, placement tests",
     "Replaces the *Customer Master Database* workbook: one customer record per learner, guardians as a separate entity, "
     "every lead with its funnel history, activities and placement-test scores.",
     ["crm.student", "crm.guardian", "crm.student_guardian", "crm.student_availability", "crm.lead",
      "crm.lead_stage_history", "crm.lead_activity", "crm.placement_test", "crm.placement_test_score"],
     ["hr.employee", "ref.course", "ref.proficiency_level", "billing.enrollment"]),
    ("catalogue-pricing", "Product catalogue & pricing",
     "Programmes, courses, dated price lists, fees, payment-plan templates and discount programmes - the inputs of the pricing engine "
     "that the *Qualified Leads* sheet computed with nested formulas.",
     ["ref.programme", "ref.delivery_mode", "ref.course", "ref.course_price", "ref.fee", "ref.payment_plan",
      "ref.payment_plan_line", "ref.discount_programme", "ref.group_discount_tier", "ref.proficiency_scale", "ref.proficiency_level"],
     ["billing.enrollment", "billing.enrollment_discount", "billing.group_registration", "academic.class"]),
    ("academic", "Academic operations - classes, sessions, staffing",
     "Replaces *Course Administration*: classes generated from a weekly meeting pattern, every session as a row, staff assigned per class "
     "and confirmed hours per session (the source of teaching payroll).",
     ["academic.room", "academic.class", "academic.class_meeting_pattern", "academic.class_staff_assignment",
      "academic.class_session", "academic.session_staff", "academic.attendance", "academic.course_lesson", "academic.learning_resource"],
     ["ref.course", "hr.employee_role", "billing.enrollment"]),
    ("order-to-cash", "Order-to-cash - enrolments, schedules, receipts, revenue",
     "Replaces *Qualified Leads* + *Receipts Management*: priced enrolments, payment schedules, receipts allocated to schedule lines "
     "(instead of the text key 'AMIxx-Course-Class-Giai doan n'), refunds, write-offs and the accrual revenue schedule.",
     ["billing.group_registration", "billing.enrollment", "billing.enrollment_status_history", "billing.enrollment_discount",
      "billing.enrollment_charge", "billing.payment_schedule", "billing.receipt", "billing.payment_allocation",
      "billing.refund", "billing.write_off", "billing.revenue_schedule"],
     ["crm.student", "crm.guardian", "crm.lead", "academic.class", "ref.course", "ref.course_price", "ref.payment_plan",
      "ref.discount_programme", "finance.payment_voucher", "finance.fiscal_period", "finance.gl_account"]),
    ("hr-payroll", "HR & payroll",
     "Replaces *Salary Pipeline*, *Working Schedule* and the monthly payslip workbook: HR role codes, salary codes with dated rates, "
     "personal overrides, Learning Advisor shifts, payroll runs, payslips, PIT and statutory deductions, commissions.",
     ["hr.employee", "hr.employee_role", "hr.employee_rate_override", "hr.employee_fixed_pay", "hr.work_shift",
      "ref.staff_role", "ref.contract_stage", "ref.salary_code", "ref.salary_rate", "ref.earning_type", "ref.deduction_type",
      "payroll.pit_rule", "payroll.statutory_deduction_rule", "payroll.payroll_run", "payroll.payroll_line",
      "payroll.commission", "payroll.payslip", "payroll.payslip_deduction"],
     ["academic.session_staff", "billing.enrollment", "finance.fiscal_period", "finance.gl_account", "finance.cost_center"]),
    ("finance", "Finance & accounting - spend, assets, journals, P&L",
     "Replaces *Payment Control* and the P&L workbook: fiscal periods with locking, chart of accounts, P&L layout and mapping, "
     "cost centres, vendors, claims, vouchers, fixed assets with depreciation, and manual journals.",
     ["finance.fiscal_period", "finance.gl_account", "finance.cost_center", "finance.pnl_line", "finance.pnl_line_mapping",
      "finance.revenue_account_map", "finance.earning_account_map", "finance.vendor", "finance.expense_claim",
      "finance.expense_claim_line", "finance.payment_voucher", "finance.payment_voucher_line", "finance.fixed_asset",
      "finance.depreciation_schedule", "finance.journal_entry", "finance.journal_line", "ref.vat_group"],
     ["hr.employee", "academic.class", "billing.refund", "billing.revenue_schedule", "payroll.payroll_line"]),
    ("controls", "Controls - catalogue, runs, exception queue",
     "New in the relational model: each control is a check view (`ctl.v_chk_*`); a run stores the exceptions it found so they can be "
     "assigned, tracked and resolved.",
     ["ctl.control", "ctl.control_run", "ctl.control_exception"], ["hr.employee"]),
    ("application", "Application - users, audit trail, daily cash close",
     "Added for the web application: sign-in accounts mapped to the five roles, the audit trail written by triggers (BR-12) and the "
     "daily cash close that compensates for staff handling cash.",
     ["app.app_user", "app.audit_log", "app.cash_close"], ["hr.employee"]),
]
CORE = ["crm.student", "crm.guardian", "crm.student_guardian", "crm.lead", "crm.placement_test",
        "academic.class", "academic.class_session", "academic.session_staff", "academic.class_staff_assignment", "academic.attendance",
        "billing.enrollment", "billing.enrollment_charge", "billing.payment_schedule", "billing.receipt", "billing.payment_allocation",
        "billing.revenue_schedule", "billing.refund", "billing.write_off",
        "hr.employee", "hr.employee_role", "hr.work_shift",
        "payroll.payroll_run", "payroll.payroll_line", "payroll.payslip", "payroll.commission",
        "finance.fiscal_period", "finance.gl_account", "finance.pnl_line_mapping", "finance.pnl_line", "finance.cost_center",
        "finance.payment_voucher", "finance.payment_voucher_line", "finance.fixed_asset", "finance.depreciation_schedule",
        "finance.journal_entry", "finance.journal_line",
        "ref.course", "ref.course_price", "ref.payment_plan", "ref.salary_code",
        "ctl.control", "ctl.control_run", "ctl.control_exception"]
SCHEMA_COLOURS = {"ref": "#F2F2F2", "crm": "#E8F1FB", "academic": "#EAF6EC", "billing": "#FFF4E0", "hr": "#F3ECFA",
                  "payroll": "#FBEAF0", "finance": "#E6F4F4", "ctl": "#FDEDEC", "app": "#EEF0F2"}
SCHEMA_EDGE = {"ref": "#8A8A8A", "crm": "#2F6DB5", "academic": "#2E8B47", "billing": "#C77700", "hr": "#7B4BB7",
               "payroll": "#B5446E", "finance": "#13807F", "ctl": "#C0392B", "app": "#4A5560"}

CATALOG_SQL = r"""
with s as (select oid, nspname from pg_namespace where nspname = any (string_to_array('%SCHEMAS%', ','))),
rels as (
  select c.oid, s.nspname as schema, c.relname as name, c.relkind, obj_description(c.oid, 'pg_class') as comment
  from pg_class c join s on s.oid = c.relnamespace where c.relkind in ('r', 'v')),
cols as (
  select a.attrelid, json_agg(json_build_object(
           'num', a.attnum, 'name', a.attname, 'type', format_type(a.atttypid, a.atttypmod),
           'notnull', a.attnotnull, 'default', pg_get_expr(d.adbin, d.adrelid),
           'generated', a.attgenerated, 'identity', a.attidentity,
           'comment', col_description(a.attrelid, a.attnum)) order by a.attnum) as columns
  from pg_attribute a left join pg_attrdef d on d.adrelid = a.attrelid and d.adnum = a.attnum
  where a.attnum > 0 and not a.attisdropped and a.attrelid in (select oid from rels)
  group by a.attrelid),
cons as (
  select co.conrelid, json_agg(json_build_object(
           'name', co.conname, 'type', co.contype, 'def', pg_get_constraintdef(co.oid),
           'cols', (select json_agg(a.attname order by k.ord) from unnest(co.conkey) with ordinality k(attnum, ord)
                     join pg_attribute a on a.attrelid = co.conrelid and a.attnum = k.attnum),
           'ref_table', case when co.contype = 'f' then (select n.nspname || '.' || c.relname from pg_class c
                         join pg_namespace n on n.oid = c.relnamespace where c.oid = co.confrelid) end,
           'ref_cols', case when co.contype = 'f' then (select json_agg(a.attname order by k.ord)
                         from unnest(co.confkey) with ordinality k(attnum, ord)
                         join pg_attribute a on a.attrelid = co.confrelid and a.attnum = k.attnum) end,
           'deferrable', co.condeferrable) order by co.contype, co.conname) as constraints
  from pg_constraint co where co.conrelid in (select oid from rels) group by co.conrelid),
idx as (
  select i.indrelid, json_agg(pg_get_indexdef(i.indexrelid) order by ic.relname) as indexes
  from pg_index i join pg_class ic on ic.oid = i.indexrelid
  where i.indrelid in (select oid from rels)
    and not exists (select 1 from pg_constraint co where co.conindid = i.indexrelid)
  group by i.indrelid),
trg as (
  select t.tgrelid, json_agg(json_build_object('name', t.tgname, 'def', pg_get_triggerdef(t.oid),
           'function', p.pronamespace::regnamespace::text || '.' || p.proname) order by t.tgname) as triggers
  from pg_trigger t join pg_proc p on p.oid = t.tgfoid
  where not t.tgisinternal and t.tgrelid in (select oid from rels) group by t.tgrelid),
funcs as (
  select json_agg(json_build_object('schema', s.nspname, 'name', p.proname,
           'args', pg_get_function_identity_arguments(p.oid), 'returns', pg_get_function_result(p.oid),
           'language', l.lanname, 'comment', obj_description(p.oid, 'pg_proc')) order by s.nspname, p.proname) as f
  from pg_proc p join s on s.oid = p.pronamespace join pg_language l on l.oid = p.prolang
  where p.prokind = 'f'),
doms as (
  select json_agg(json_build_object('schema', s.nspname, 'name', t.typname, 'base', format_type(t.typbasetype, t.typtypmod),
           'check', (select string_agg(pg_get_constraintdef(c.oid), ' ') from pg_constraint c where c.contypid = t.oid),
           'comment', obj_description(t.oid, 'pg_type')) order by t.typname) as d
  from pg_type t join s on s.oid = t.typnamespace where t.typtype = 'd'),
schemas as (
  select json_agg(json_build_object('name', nspname, 'comment', obj_description(oid, 'pg_namespace'))) as s from s)
select json_build_object(
  'relations', (select json_agg(json_build_object(
       'schema', r.schema, 'name', r.name, 'kind', r.relkind, 'comment', r.comment,
       'columns', coalesce(c.columns, '[]'), 'constraints', coalesce(k.constraints, '[]'),
       'indexes', coalesce(i.indexes, '[]'), 'triggers', coalesce(t.triggers, '[]')) order by r.schema, r.name)
     from rels r left join cols c on c.attrelid = r.oid left join cons k on k.conrelid = r.oid
     left join idx i on i.indrelid = r.oid left join trg t on t.tgrelid = r.oid),
  'functions', (select f from funcs), 'domains', (select d from doms), 'schemas', (select s from schemas),
  'version', current_setting('server_version'))
"""


def load_catalog(db):
    sql = CATALOG_SQL.replace("%SCHEMAS%", ",".join(SCHEMAS))
    out = subprocess.run(["psql", "-X", "-At", "-d", db, "-c", sql], check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def md(text):
    return (text or "").replace("|", "\\|").replace("\n", " ")


def short_type(t):
    t = t.replace("timestamp with time zone", "timestamptz").replace("time without time zone", "time")
    t = t.replace("character varying", "varchar")
    return t


def mermaid_type(t):
    t = short_type(t).replace("ref.", "")
    t = re.sub(r"\(.*?\)", "", t).replace("[]", "_array").strip()
    return re.sub(r"[^A-Za-z0-9_]", "_", t)


def ent(fq):
    return fq.replace(".", "_")


class Model:
    def __init__(self, cat):
        self.cat = cat
        self.rel = {f"{r['schema']}.{r['name']}": r for r in cat["relations"]}
        self.tables = {k: v for k, v in self.rel.items() if v["kind"] == "r"}
        self.views = {k: v for k, v in self.rel.items() if v["kind"] == "v"}
        self.fks = []          # (child, child_cols, parent, parent_cols, nullable, unique)
        self.referenced_by = defaultdict(list)
        for fq, t in self.tables.items():
            colmap = {c["name"]: c for c in t["columns"]}
            uniques = [set(c["cols"]) for c in t["constraints"] if c["type"] in ("p", "u")]
            for c in t["constraints"]:
                if c["type"] != "f":
                    continue
                nullable = any(not colmap[x]["notnull"] for x in c["cols"])
                unique = any(u == set(c["cols"]) for u in uniques)
                self.fks.append((fq, c["cols"], c["ref_table"], c["ref_cols"], nullable, unique))
                self.referenced_by[c["ref_table"]].append((fq, c["cols"]))

    def keys(self, fq):
        t = self.tables[fq]
        out = defaultdict(set)
        for c in t["constraints"]:
            tag = {"p": "PK", "f": "FK", "u": "UK"}.get(c["type"])
            if tag:
                for col in c["cols"] or []:
                    out[col].add(tag)
        return out

    def fk_targets(self, fq):
        res = defaultdict(list)
        for child, cols, parent, pcols, *_ in self.fks:
            if child == fq:
                for c in cols:
                    res[c].append(parent)
        return res


# ------------------------------------------------------------------------------------------ data dictionary
def data_dictionary(m):
    cat = m.cat
    ncols = sum(len(t["columns"]) for t in m.tables.values())
    ncheck = sum(1 for t in m.tables.values() for c in t["constraints"] if c["type"] == "c")
    nexcl = sum(1 for t in m.tables.values() for c in t["constraints"] if c["type"] == "x")
    nuniq = sum(1 for t in m.tables.values() for c in t["constraints"] if c["type"] == "u")
    ntrg = sum(len(t["triggers"]) for t in m.tables.values())
    commented = sum(1 for t in m.tables.values() for c in t["columns"] if c["comment"])
    L = []
    w = L.append
    w("# Data dictionary")
    w("")
    w("> Generated by `database/tools/generate_docs.py` from the PostgreSQL catalog "
      f"(PostgreSQL {cat['version'].split()[0]}). Do not edit by hand - change the DDL comments and regenerate.")
    w("")
    w("| Object | Count |")
    w("|---|---:|")
    for k, v in [("Schemas", len(SCHEMAS)), ("Tables", len(m.tables)), ("Columns", ncols),
                 ("Columns with a description", commented), ("Foreign keys", len(m.fks)), ("Unique constraints", nuniq),
                 ("Check constraints", ncheck), ("Exclusion constraints (no overlapping validity periods)", nexcl),
                 ("Triggers", ntrg), ("Views (reporting + control checks)", len(m.views)),
                 ("Functions", len(cat["functions"])), ("Domains", len(cat["domains"]))]:
        w(f"| {k} | {v} |")
    w("")
    w("**Conventions** - `PK` primary key, `FK` foreign key, `UK` unique; *generated* columns are computed by PostgreSQL; "
      "`ref.money_vnd_pos` is a non-negative VND amount; `ref.pct` is a fraction (0.10 = 10%). "
      "Descriptions quote the legacy Excel field (*Legacy: ...*) where a column replaces one.")
    w("")
    w("## Contents")
    w("")
    for s in SCHEMAS:
        objs = [k for k in m.rel if k.startswith(s + ".")]
        links = ", ".join(f"[`{k.split('.', 1)[1]}`](#{anchor(k)})" for k in objs)
        w(f"- **{s}** - {SCHEMA_TITLES[s]} ({len(objs)}): {links}")
    w("- [Functions](#functions) · [Domains](#domains) · [Legacy field lineage](#legacy-field-lineage)")
    w("")
    scomment = {x["name"]: x["comment"] for x in cat["schemas"]}
    for s in SCHEMAS:
        w(f"## Schema `{s}` - {SCHEMA_TITLES[s]}")
        w("")
        if scomment.get(s):
            w(scomment[s] + ".")
            w("")
        for fq, r in m.rel.items():
            if r["schema"] != s:
                continue
            if r["kind"] == "r":
                table_section(m, fq, r, w)
            else:
                view_section(fq, r, w)
    w("## Functions")
    w("")
    w("| Function | Returns | Language | Description |")
    w("|---|---|---|---|")
    for f in cat["functions"]:
        w(f"| `{f['schema']}.{f['name']}({md(f['args'])})` | `{md(f['returns'])}` | {f['language']} | {md(f['comment'])} |")
    w("")
    w("## Domains")
    w("")
    w("| Domain | Base type | Check | Description |")
    w("|---|---|---|---|")
    for d in cat["domains"]:
        w(f"| `{d['schema']}.{d['name']}` | `{d['base']}` | {('`' + md(d['check']) + '`') if d['check'] else ''} | {md(d['comment'])} |")
    w("")
    w("## Legacy field lineage")
    w("")
    w("Every table or column whose description cites the Excel field it replaces.")
    w("")
    w("| Model object | Legacy source (Excel) |")
    w("|---|---|")
    for fq, r in m.tables.items():
        if r["comment"] and "Legacy" in r["comment"]:
            w(f"| `{fq}` | {md(r['comment'].split('Legacy', 1)[1].lstrip(': ').rstrip('.'))} |")
        for c in r["columns"]:
            if c["comment"] and "Legacy" in c["comment"]:
                w(f"| `{fq}.{c['name']}` | {md(c['comment'].split('Legacy', 1)[1].lstrip(': ').rstrip('.'))} |")
    w("")
    return "\n".join(L)


def anchor(fq):
    return re.sub(r"[^a-z0-9_ -]", "", fq.replace(".", "").lower()).replace(" ", "-")


def table_section(m, fq, r, w):
    w(f'<a id="{anchor(fq)}"></a>')
    w(f"### `{fq}`")
    w("")
    if r["comment"]:
        w(r["comment"])
        w("")
    keys = m.keys(fq)
    targets = m.fk_targets(fq)
    w("| # | Column | Type | Null | Default / generated | Key | Description |")
    w("|---:|---|---|:---:|---|---|---|")
    for c in r["columns"]:
        dflt = ""
        if c["identity"]:
            dflt = "identity"
        elif c["generated"] == "s":
            dflt = f"generated: `{md(c['default'])}`"
        elif c["default"]:
            dflt = f"`{md(c['default'])}`"
        key = ", ".join(sorted(keys.get(c["name"], []), key=["PK", "FK", "UK"].index))
        if c["name"] in targets:
            key += " → " + ", ".join(f"[`{t}`](#{anchor(t)})" for t in sorted(set(targets[c["name"]])))
        w(f"| {c['num']} | `{c['name']}` | `{short_type(c['type'])}` | {'' if c['notnull'] else '✓'} | {dflt} | {key} | {md(c['comment'])} |")
    w("")
    extra = []
    for c in r["constraints"]:
        if c["type"] == "c":
            extra.append(f"- check `{md(c['def'])}`")
        elif c["type"] == "u":
            extra.append(f"- unique `{md(c['def'])}`")
        elif c["type"] == "x":
            extra.append(f"- exclude `{md(c['def'])}`")
        elif c["type"] == "f" and len(c["cols"]) > 1:
            extra.append(f"- composite FK `{md(c['def'])}`")
        elif c["type"] == "p" and len(c["cols"]) > 1:
            extra.append(f"- composite primary key `({', '.join(c['cols'])})`")
    for t in r["triggers"]:
        when = re.search(r"(BEFORE|AFTER) (.+?) ON ", t["def"])
        extra.append(f"- trigger `{t['name']}` {when.group(1).lower() + ' ' + when.group(2).lower() if when else ''} → `{t['function']}()`")
    for i in r["indexes"]:
        extra.append(f"- index `{md(re.sub(r'^CREATE (UNIQUE )?INDEX (\\S+) ON \\S+ USING ', lambda x: (x.group(1) or '').lower() + x.group(2) + ' ', i))}`")
    refs = m.referenced_by.get(fq, [])
    if refs:
        extra.append("- referenced by " + ", ".join(f"[`{c}`](#{anchor(c)}) ({', '.join(cols)})" for c, cols in refs))
    if extra:
        w("<details><summary>Constraints, triggers, indexes</summary>")
        w("")
        w("\n".join(extra))
        w("")
        w("</details>")
        w("")


def view_section(fq, r, w):
    w(f'<a id="{anchor(fq)}"></a>')
    w(f"### `{fq}` (view)")
    w("")
    if r["comment"]:
        w(r["comment"])
        w("")
    w("Columns: " + ", ".join(f"`{c['name']}` *{short_type(c['type'])}*" for c in r["columns"]))
    w("")


# ------------------------------------------------------------------------------------------ ER diagrams
def er_block(m, own, context=(), with_attributes=True):
    own = [t for t in own if t in m.tables]
    context = [t for t in context if t in m.tables and t not in own]
    oset, cset = set(own), set(context)
    lines = ["erDiagram"]
    edges = []
    for child, cols, parent, pcols, nullable, unique in m.fks:
        if set(cols) & ACTOR_COLUMNS:
            continue
        if not ((child in oset and parent in oset | cset) or (child in cset and parent in oset)):
            continue
        left = "|o" if nullable else "||"
        right = "o|" if unique else "o{"
        edges.append(f'    {ent(parent)} {left}--{right} {ent(child)} : "{", ".join(cols)}"')
    for t in own + context:
        if not with_attributes:
            lines.append(f"    {ent(t)}")
            continue
        keys = m.keys(t)
        colmap = {c["name"]: c for c in m.tables[t]["columns"]}
        lines.append(f"    {ent(t)} {{")
        if t in oset:
            cols = [c for c in m.tables[t]["columns"] if c["name"] not in AUDIT_COLUMNS]
        else:
            pk = [c for c in m.tables[t]["constraints"] if c["type"] == "p"]
            cols = [colmap[c] for c in (pk[0]["cols"] if pk else [])]
        for c in cols:
            k = ",".join(sorted(keys.get(c["name"], []), key=["PK", "FK", "UK"].index))
            lines.append(f"        {mermaid_type(c['type'])} {c['name']}{(' ' + k) if k else ''}")
        lines.append("    }")
    lines += list(dict.fromkeys(edges))
    return "\n".join(lines)


def dot_graph(m, tables, title, compact=False, ports=False):
    """Graphviz ERD: tables clustered by schema, key columns listed, crow's-foot edges between FK and PK ports."""
    tset = [t for t in tables if t in m.tables]
    out = ['digraph ERD {',
           '  graph [rankdir=TB, splines=spline, nodesep=0.25, ranksep=1.1, fontname="Helvetica", fontsize=22, labelloc=t, '
           f'label=<<b>{title}</b>>, pad=0.4, bgcolor="white", newrank=true];',
           '  node [shape=plain, fontname="Helvetica", fontsize=11];',
           '  edge [color="#7A869A", penwidth=1.1, arrowsize=0.8, dir=both];']
    by_schema = defaultdict(list)
    for t in tset:
        by_schema[t.split(".")[0]].append(t)
    for sch, members in by_schema.items():
        out.append(f'  subgraph cluster_{sch} {{')
        out.append(f'    label=<<b>{sch}</b>  <font point-size="12">{SCHEMA_TITLES[sch].replace("&", "&amp;")}</font>>; style="rounded,filled"; '
                   f'fillcolor="{SCHEMA_COLOURS[sch]}"; color="{SCHEMA_EDGE[sch]}"; fontcolor="{SCHEMA_EDGE[sch]}"; fontsize=16;')
        for t in members:
            keys = m.keys(t)
            linked = {col for col, targets in m.fk_targets(t).items() if set(targets) & set(tset)} - ACTOR_COLUMNS
            single_uk = {cc["cols"][0] for cc in m.tables[t]["constraints"] if cc["type"] == "u" and len(cc["cols"]) == 1}
            rows = []
            for c in m.tables[t]["columns"]:
                k = keys.get(c["name"], set())
                if compact and not ("PK" in k or c["name"] in linked or c["name"] in single_uk):
                    continue
                if not compact and not k and c["name"] in AUDIT_COLUMNS:
                    continue
                tag = " ".join(x for x in ("PK", "FK", "UK") if x in k)
                style = ("<b>", "</b>") if "PK" in k else (("<i>", "</i>") if "FK" in k else ("", ""))
                rows.append(f'<tr><td port="{c["name"]}" align="left" balign="left">{style[0]}{c["name"]}{style[1]}</td>'
                            f'<td align="left"><font color="#6B7280" point-size="9">{tag}</font></td></tr>')
            if not rows:
                rows.append('<tr><td colspan="2"> </td></tr>')
            out.append(f'    {ent(t)} [label=<<table border="1" cellborder="0" cellspacing="0" cellpadding="3" color="{SCHEMA_EDGE[sch]}" bgcolor="white">'
                       f'<tr><td colspan="2" bgcolor="{SCHEMA_EDGE[sch]}" align="center"><font color="white"><b>{t.split(".")[1]}</b></font></td></tr>'
                       + "".join(rows) + '</table>>];')
        out.append('  }')
    tst = set(tset)
    for child, cols, parent, pcols, nullable, unique in m.fks:
        if child not in tst or parent not in tst or set(cols) & ACTOR_COLUMNS:
            continue
        tail = "teeodot" if unique else "crowodot"
        head = "teeodot" if nullable else "teetee"
        colour = SCHEMA_EDGE[child.split(".")[0]]
        src = f"{ent(child)}:{cols[0]}" if ports else ent(child)
        dst = f"{ent(parent)}:{pcols[0]}" if ports else ent(parent)
        out.append(f'  {src} -> {dst} [arrowtail={tail}, arrowhead={head}, color="{colour}AA"];')
    out.append('}')
    return "\n".join(out)


def erd_doc(m):
    (DOCS / "erd").mkdir(parents=True, exist_ok=True)
    L = []
    w = L.append
    w("# Entity-relationship diagrams")
    w("")
    w("> Generated by `database/tools/generate_docs.py` from the live catalog - every line below is a real foreign key. "
      "Column-level detail (types, constraints, descriptions, legacy lineage) is in [DATA_DICTIONARY.md](DATA_DICTIONARY.md).")
    w("")
    w(f"**{len(m.tables)} tables · {len(m.fks)} foreign keys · {len(m.views)} views** across 9 schemas. "
      "Entity names are `schema_table` (e.g. `billing_enrollment` = `billing.enrollment`).")
    w("")
    w("How to read the crow's-foot notation: `||` exactly one · `|o` zero or one (nullable FK) · `o{` zero or many · `o|` zero or one (unique FK). "
      "Labels are the foreign-key columns. In module diagrams, tables from another module appear with their primary key only, "
      "and links to small code tables (`ref.*` lookups) and to the employee who approved / confirmed / posted a record "
      "(`approved_by`, `confirmed_by`, `posted_by` ...) are omitted to keep the diagrams readable - those columns are still marked `FK`.")
    w("")
    w("## Contents")
    w("")
    w("1. [Core model](#core-model)")
    for i, (slug, title, *_rest) in enumerate(MODULES, 2):
        w(f"{i}. [{title}](#{slug})")
    w(f"{len(MODULES) + 2}. [Code tables](#code-tables)")
    w("")
    core_dot = dot_graph(m, CORE, "AMI Education - core relational model (key columns)", compact=True)
    (DOCS / "erd" / "core-model.dot").write_text(core_dot + "\n", encoding="utf-8")
    full_dot = dot_graph(m, list(m.tables), f"AMI Education - full relational model ({len(m.tables)} tables)", compact=True)
    (DOCS / "erd" / "full-model.dot").write_text(full_dot + "\n", encoding="utf-8")
    w("## Core model")
    w("")
    w("The transactional backbone with its key columns (**bold** = primary key, *italic* = foreign key): **lead → enrolment → payment schedule → receipt allocation → revenue schedule**, "
      "**class → session → confirmed staff hours → payroll line → payslip**, **voucher line → cost centre / GL account → P&L line**, "
      "and the **control → run → exception** queue.")
    w("")
    w("![Core ER model](../../docs/images/erd-core-model.png)")
    w("")
    w(f"The full model with all {len(m.tables)} tables (keys only) is in [erd/full-model.svg](erd/full-model.svg) - open it and zoom. "
      "Both pictures are rendered with Graphviz from [erd/core-model.dot](erd/core-model.dot) and [erd/full-model.dot](erd/full-model.dot).")
    w("")
    drawn = set()
    for i, (slug, title, intro, own, context) in enumerate(MODULES, 1):
        block = er_block(m, own, context)
        (DOCS / "erd" / f"{i:02d}-{slug}.mmd").write_text(block + "\n", encoding="utf-8")
        drawn |= set(own)
        w(f'<a id="{slug}"></a>')
        w(f"## {title}")
        w("")
        w(intro)
        w("")
        w("```mermaid")
        w(block)
        w("```")
        w("")
    w('<a id="code-tables"></a>')
    w("## Code tables")
    w("")
    w("Small reference tables with readable codes as primary keys (enumerations). They replace the drop-down lists of the workbooks.")
    w("")
    w("| Table | Description | Used by |")
    w("|---|---|---|")
    for fq, t in m.tables.items():
        if fq in drawn:
            continue
        users = sorted({c for c, _ in m.referenced_by.get(fq, [])})
        w(f"| `{fq}` | {md(t['comment'])} | {', '.join('`' + u + '`' for u in users)} |")
    w("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="ami")
    args = ap.parse_args()
    m = Model(load_catalog(args.db))
    DOCS.mkdir(exist_ok=True)
    (DOCS / "DATA_DICTIONARY.md").write_text(data_dictionary(m), encoding="utf-8")
    (DOCS / "ERD.md").write_text(erd_doc(m), encoding="utf-8")
    print(f"tables {len(m.tables)}, views {len(m.views)}, foreign keys {len(m.fks)} -> docs/DATA_DICTIONARY.md, docs/ERD.md, docs/erd/*.mmd")


if __name__ == "__main__":
    main()
