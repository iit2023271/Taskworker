"""Regenerate the mock company seed data.

Writes:
  mock_company/data/seed.json            - the 5 inbox emails
  mock_company/data/invoices/*.pdf       - one PDF per invoice (fpdf2)

Run:  python -m mock_company.seed        (from the project root)
       or:  python seed.py               (from mock_company/)
Seed data is fixed by SPEC.md - do not change the invoice numbers,
amounts or dates here without updating the spec and the tests.
"""

import json
from datetime import date
from pathlib import Path

from fpdf import FPDF

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
INVOICES_DIR = DATA / "invoices"

# --- Invoices (SPEC.md) ---------------------------------------------------
# amount is stored as a number; amount_str is the exact display string.
INVOICES = [
    {
        "vendor": "Acme Supplies Ltd",
        "invoice_no": "INV-2026-1042",
        "issued": date(2026, 10, 20),
        "amount": 4850.00,
        "amount_str": "$4,850.00",
        "due": date(2026, 11, 19),
        "file": "inv-2026-1042.pdf",
        "description": "Managed IT services - October 2026",
    },
    {
        "vendor": "Acme Supplies Ltd",
        "invoice_no": "INV-2026-1031",
        "issued": date(2026, 9, 18),
        "amount": 3920.50,
        "amount_str": "$3,920.50",
        "due": date(2026, 10, 18),
        "file": "inv-2026-1031.pdf",
        "description": "Managed IT services - September 2026",
    },
    {
        "vendor": "Globex Corp",
        "invoice_no": "INV-G-881",
        "issued": date(2026, 10, 22),
        "amount": 1150.00,
        "amount_str": "$1,150.00",
        "due": date(2026, 11, 21),
        "file": "inv-g-881.pdf",
        "description": "Cloud hosting - October 2026",
    },
]

# --- Inbox (SPEC.md): 5 emails; the latest Acme email (2026-10-20)
# carries INV-2026-1042. Globex INV-G-881 (2026-10-22) is the distractor:
# newer overall, but the wrong vendor. --------------------------------------
EMAILS = [
    {
        "id": "1",
        "date": "2026-10-20",
        "from": "billing@acmesupplies.com",
        "from_name": "Acme Supplies Ltd",
        "subject": "Invoice INV-2026-1042 - October services",
        "body": (
            "Hello,\n\n"
            "Please find attached invoice INV-2026-1042 for $4,850.00 "
            "for managed IT services in October 2026.\n\n"
            "Amount due: $4,850.00\n"
            "Due date: 19 November 2026 (2026-11-19)\n\n"
            "Please arrange payment by the due date.\n\n"
            "Accounts team\nAcme Supplies Ltd"
        ),
        "attachment": "inv-2026-1042.pdf",
    },
    {
        "id": "2",
        "date": "2026-10-22",
        "from": "accounts@globexcorp.com",
        "from_name": "Globex Corp",
        "subject": "Invoice INV-G-881 - Cloud hosting October",
        "body": (
            "Hello,\n\n"
            "Please find attached invoice INV-G-881 for $1,150.00 "
            "for cloud hosting in October 2026.\n\n"
            "Amount due: $1,150.00\n"
            "Due date: 21 November 2026 (2026-11-21)\n\n"
            "Kind regards,\nGlobex Corp Accounts"
        ),
        "attachment": "inv-g-881.pdf",
    },
    {
        "id": "3",
        "date": "2026-09-18",
        "from": "billing@acmesupplies.com",
        "from_name": "Acme Supplies Ltd",
        "subject": "Invoice INV-2026-1031 - September services",
        "body": (
            "Hello,\n\n"
            "Please find attached invoice INV-2026-1031 for $3,920.50 "
            "for managed IT services in September 2026.\n\n"
            "Amount due: $3,920.50\n"
            "Due date: 18 October 2026 (2026-10-18)\n\n"
            "Accounts team\nAcme Supplies Ltd"
        ),
        "attachment": "inv-2026-1031.pdf",
    },
    {
        "id": "4",
        "date": "2026-10-15",
        "from": "support@acmesupplies.com",
        "from_name": "Acme Supplies Ltd",
        "subject": "Reminder: updated payment terms",
        "body": (
            "Hello,\n\n"
            "A quick note that our payment terms are now net 30 days "
            "from the invoice date. No action needed on existing invoices.\n\n"
            "Acme Supplies Ltd Support"
        ),
        "attachment": None,
    },
    {
        "id": "5",
        "date": "2026-10-08",
        "from": "hello@globexcorp.com",
        "from_name": "Globex Corp",
        "subject": "Welcome to the Globex vendor portal",
        "body": (
            "Hello,\n\n"
            "Welcome to the Globex vendor portal. You can view invoices "
            "and payment history once your account is activated.\n\n"
            "Globex Corp"
        ),
        "attachment": None,
    },
]


def _long_date(d: date) -> str:
    """'19 November 2026' style date."""
    return f"{d.day} {d.strftime('%B')} {d.year}"


def make_invoice_pdf(inv: dict, path: Path) -> None:
    """One-page invoice PDF. The vendor, invoice number, amount and due
    date (in BOTH '19 November 2026' and '2026-11-19' forms) are plain
    text so pypdf can extract them."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "TAX INVOICE", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 12)
    lines = [
        f"Vendor: {inv['vendor']}",
        f"Invoice number: {inv['invoice_no']}",
        f"Invoice date: {_long_date(inv['issued'])} ({inv['issued'].isoformat()})",
        f"Description: {inv['description']}",
        f"Amount due: {inv['amount_str']}",
        f"Total: {inv['amount_str']}",
        f"Due date: {_long_date(inv['due'])} ({inv['due'].isoformat()})",
        "",
        "Please pay by the due date shown above.",
        f"Thank you for your business - {inv['vendor']}",
    ]
    for line in lines:
        if line == "":
            pdf.ln(8)
        else:
            # new_x="LMARGIN": after a multi_cell fpdf2 leaves the cursor at
            # the RIGHT end of the cell; without this every line after the
            # first is drawn starting at the right margin, off the page.
            pdf.multi_cell(w=pdf.epw, h=8, text=line, new_x="LMARGIN")
    pdf.output(str(path))


def main() -> None:
    INVOICES_DIR.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)

    for inv in INVOICES:
        make_invoice_pdf(inv, INVOICES_DIR / inv["file"])

    with open(DATA / "seed.json", "w", encoding="utf-8") as f:
        json.dump(EMAILS, f, indent=2)

    # Start with an empty records file if none exists (never wipe existing
    # records on a re-seed).
    records_path = DATA / "records.json"
    if not records_path.exists():
        with open(records_path, "w", encoding="utf-8") as f:
            json.dump([], f)

    print(f"Wrote {DATA / 'seed.json'} ({len(EMAILS)} emails)")
    for inv in INVOICES:
        print(f"Wrote {INVOICES_DIR / inv['file']} "
              f"({inv['vendor']} {inv['invoice_no']} {inv['amount_str']})")


if __name__ == "__main__":
    main()
