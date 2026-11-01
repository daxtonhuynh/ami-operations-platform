"""Printable documents: receipt (given to the payer) and payslip (given to the employee)."""
from __future__ import annotations

import io
import pathlib

from reportlab.lib import colors
from reportlab.lib.pagesizes import A5, A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONTS = pathlib.Path(__file__).parent / "assets" / "fonts"
LOGO_REVERSE = pathlib.Path(__file__).parent / "assets" / "brand" / "ami-logo-reverse.png"
NAVY, AMBER = colors.HexColor("#000080"), colors.HexColor("#FDA50F")   # AMI brand
NAVY_TINT = colors.HexColor("#EEF0FA")
_registered = False


def _fonts():
    global _registered
    if not _registered:   # DejaVu covers Vietnamese diacritics in names
        pdfmetrics.registerFont(TTFont("Body", str(FONTS / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("Bold", str(FONTS / "DejaVuSans-Bold.ttf")))
        _registered = True


def _band(c, w, h, band, margin, centre, address, title, subtitle, title_size=13):
    """Navy header band with the reverse AMI logo, centre name and address; document title on the right; amber rule below."""
    c.setFillColor(NAVY)
    c.rect(0, h - band, w, band, fill=1, stroke=0)
    c.setFillColor(AMBER)
    c.rect(0, h - band - 1.6 * mm, w, 1.6 * mm, fill=1, stroke=0)
    logo_h = band * 0.52
    logo_w = logo_h * 684 / 337
    c.drawImage(str(LOGO_REVERSE), margin, h - band / 2 - logo_h / 2, width=logo_w, height=logo_h, mask="auto")
    x = margin + logo_w + 6 * mm
    c.setFillColor(colors.white)
    c.setFont("Bold", 13)
    c.drawString(x, h - band / 2 + 1 * mm, centre)
    c.setFont("Body", 8.5)
    c.drawString(x, h - band / 2 - 4.5 * mm, address)
    c.setFont("Bold", title_size)
    c.drawRightString(w - margin, h - band / 2 + 1 * mm, title)
    c.setFont("Body", 9)
    c.drawRightString(w - margin, h - band / 2 - 4.5 * mm, subtitle)
    c.setFillColor(colors.black)


ONES = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen",
        "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def _three(n: int) -> str:
    words = []
    if n >= 100:
        words.append(ONES[n // 100] + " hundred")
        n %= 100
    if n >= 20:
        words.append(TENS[n // 10] + ("-" + ONES[n % 10] if n % 10 else ""))
    elif n:
        words.append(ONES[n])
    return " ".join(words)


def amount_in_words(n: int) -> str:
    n = int(round(n))
    if n == 0:
        return "Zero dong"
    parts = []
    for div, name in ((10 ** 9, "billion"), (10 ** 6, "million"), (10 ** 3, "thousand"), (1, "")):
        if n >= div:
            parts.append((_three(n // div) + " " + name).strip())
            n %= div
    text = " ".join(parts)
    return text[0].upper() + text[1:] + " dong"


def _money(x) -> str:
    return f"{float(x):,.0f} VND"


def receipt_pdf(r: dict, centre: str, address: str) -> bytes:
    """r: receipt_no, receipt_date, learner, student_code, payer_name, amount, method, enrollment_code, course_name,
    collected_by, status, void_reason"""
    _fonts()
    buf = io.BytesIO()
    w, h = landscape(A5)
    c = canvas.Canvas(buf, pagesize=(w, h))
    c.setTitle(f"Receipt {r['receipt_no']}")
    _band(c, w, h, 22 * mm, 14 * mm, centre, address, "RECEIPT", f"No. {r['receipt_no']}  ·  {r['receipt_date']:%d %b %Y}")
    y = h - 34 * mm
    rows = [
        ("Received from", r.get("payer_name") or r["learner"]),
        ("For learner", f"{r['learner']} ({r['student_code']})"),
        ("Enrolment", f"{r.get('enrollment_code') or 'advance payment - not yet applied'}  {r.get('course_name') or ''}".strip()),
        ("Payment method", (r.get("method") or "").replace("_", " ").title()),
        ("Collected by", r.get("collected_by") or "-"),
    ]
    for label, value in rows:
        c.setFont("Body", 9)
        c.setFillColor(colors.HexColor("#555555"))
        c.drawString(14 * mm, y, label)
        c.setFillColor(colors.black)
        c.setFont("Bold", 10.5)
        c.drawString(52 * mm, y, str(value))
        y -= 8 * mm
    c.setStrokeColor(NAVY)
    c.setFillColor(NAVY_TINT)
    c.setLineWidth(1.2)
    c.roundRect(14 * mm, y - 16 * mm, w - 28 * mm, 18 * mm, 3 * mm, fill=1)
    c.setFillColor(NAVY)
    c.setFont("Bold", 15)
    c.drawString(20 * mm, y - 6 * mm, _money(r["amount"]))
    c.setFillColor(colors.black)
    c.setFont("Body", 9)
    c.drawString(20 * mm, y - 12 * mm, amount_in_words(r["amount"]))
    c.setFont("Body", 7.5)
    c.setFillColor(colors.HexColor("#777777"))
    c.drawString(14 * mm, 10 * mm, "Tuition paid is not refundable after the class has started, except where the centre cancels "
                                   "sessions. Keep this receipt for your records.")
    c.drawRightString(w - 14 * mm, 6 * mm, "Demo document - fictitious data")
    if r.get("status") == "VOID":
        c.saveState()
        c.setFillColor(colors.Color(0.85, 0.1, 0.1, alpha=0.25))
        c.setFont("Bold", 70)
        c.translate(w / 2, h / 2)
        c.rotate(20)
        c.drawCentredString(0, -20, "VOID")
        c.restoreState()
        c.setFont("Body", 8)
        c.setFillColor(colors.HexColor("#B91C1C"))
        c.drawString(14 * mm, 15 * mm, f"Voided: {r.get('void_reason') or ''}")
    c.showPage()
    c.save()
    return buf.getvalue()


def payslip_pdf(p: dict, lines: list[dict], deductions: list[dict], centre: str, address: str) -> bytes:
    """p: full_name, employee_code, period_label, taxable_earnings, allowances, pit_withheld, other_deductions, net_pay, status"""
    _fonts()
    buf = io.BytesIO()
    w, h = A4
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Payslip {p['employee_code']} {p['period_label']}")
    _band(c, w, h, 26 * mm, 18 * mm, centre, address, f"PAYSLIP  {p['period_label']}", f"Run status: {p.get('status', '').title()}",
          title_size=14)
    y = h - 40 * mm
    c.setFont("Bold", 12)
    c.drawString(18 * mm, y, p["full_name"])
    c.setFont("Body", 9.5)
    c.drawString(18 * mm, y - 5 * mm, f"Employee {p['employee_code']}")
    y -= 16 * mm

    def row(label, value, bold=False, indent=0):
        nonlocal y
        c.setFont("Bold" if bold else "Body", 10 if bold else 9.5)
        c.drawString((18 + indent) * mm, y, label)
        c.drawRightString(w - 18 * mm, y, value)
        y -= 6.5 * mm

    def rule():
        nonlocal y
        c.setStrokeColor(colors.HexColor("#CCCCCC"))
        c.line(18 * mm, y + 3 * mm, w - 18 * mm, y + 3 * mm)
        y -= 2 * mm

    row("Earnings", "Amount", bold=True)
    rule()
    for ln in lines:
        detail = ""
        if ln.get("quantity_hours"):
            detail = f"  ({float(ln['quantity_hours']):g} h x {float(ln['rate']):,.0f})"
        label = f"{ln['earning']}{detail}"
        if ln.get("note"):
            label += f" - {ln['note']}"
        row(label[:95], _money(ln["amount"]), indent=3)
    rule()
    row("Taxable earnings", _money(p["taxable_earnings"]), bold=True)
    row("Allowances (not taxable)", _money(p["allowances"]), bold=True)
    y -= 4 * mm
    row("Deductions", "", bold=True)
    rule()
    for d in deductions:
        row(d["deduction"], "- " + _money(d["amount"]), indent=3)
    if not deductions:
        row("None", "-", indent=3)
    rule()
    y -= 2 * mm
    c.setFillColor(NAVY_TINT)
    c.rect(18 * mm, y - 4 * mm, w - 36 * mm, 13 * mm, fill=1, stroke=0)
    c.setFillColor(AMBER)
    c.rect(18 * mm, y - 4 * mm, 1.6 * mm, 13 * mm, fill=1, stroke=0)
    c.setFillColor(NAVY)
    c.setFont("Bold", 13)
    c.drawString(22 * mm, y + 1 * mm, "Net pay")
    c.drawRightString(w - 22 * mm, y + 1 * mm, _money(p["net_pay"]))
    c.setFillColor(colors.black)
    c.setFont("Body", 8.5)
    c.drawString(22 * mm, y - 9 * mm, amount_in_words(p["net_pay"]))
    c.setFont("Body", 7.5)
    c.setFillColor(colors.HexColor("#777777"))
    c.drawString(18 * mm, 12 * mm, "Personal income tax withheld under the centre's monthly rule. Questions: contact HR within 5 working days.")
    c.drawRightString(w - 18 * mm, 8 * mm, "Demo document - fictitious data")
    c.showPage()
    c.save()
    return buf.getvalue()
