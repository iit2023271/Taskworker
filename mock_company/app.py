"""Mock company app (Flask).

Runs the fake intranet the TaskWorker agent works against:
an inbox of emails (some with invoice PDF attachments) and an
internal system where invoice records are entered by hand.

Routes (SPEC.md):
  GET  /                        dashboard, links to /inbox and /system
  GET  /inbox                   table of emails (date, from, subject)
  GET  /inbox/<id>              email view, attachment link when present
  GET  /invoices/<file>.pdf     invoice PDF
  GET  /system                  records table + entry form
  POST /system/add              validate, append record, redirect to /system
  GET  /system/api/records      JSON list of records (verifier)
  GET  /api/inbox               JSON list of emails (fallback path)
  POST /system/api/reset        clear records (demo repeatability)

Records persist to mock_company/data/records.json.
Run:  python -m mock_company.app   (or: python -m taskworker mock)
Port: env MOCK_PORT, default 5000.
"""

import json
import os
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, render_template_string, request, send_from_directory, url_for

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
INVOICES_DIR = DATA / "invoices"
SEED_FILE = DATA / "seed.json"
RECORDS_FILE = DATA / "records.json"

app = Flask(__name__)
DATA.mkdir(parents=True, exist_ok=True)


# --- data helpers ----------------------------------------------------------

def load_emails():
    if not SEED_FILE.exists():
        return []
    with open(SEED_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_records():
    if not RECORDS_FILE.exists():
        return []
    try:
        with open(RECORDS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def save_records(records):
    with open(RECORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)


# --- templates (inline; the mock app is intentionally tiny) ----------------

BASE_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>{{ title }}</title>
<style>
body { font-family: sans-serif; max-width: 800px; margin: 2em auto; padding: 0 1em; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ccc; padding: 6px 10px; text-align: left; }
form label { display: block; margin-top: 10px; }
form input { width: 300px; padding: 4px; }
button { margin-top: 14px; padding: 6px 16px; }
pre { white-space: pre-wrap; background: #f6f6f6; padding: 1em; }
</style></head><body>
<h1>{{ title }}</h1>
{{ body | safe }}
</body></html>"""

DASHBOARD_BODY = """
<p>Welcome to the Acme internal portal (demo environment).</p>
<ul>
  <li><a href="/inbox">Inbox</a> — emails from vendors, some with invoice PDFs</li>
  <li><a href="/system">Internal system</a> — entered invoice records</li>
</ul>
"""


def render(title, body):
    return render_template_string(BASE_HTML, title=title, body=body)


# --- routes ----------------------------------------------------------------

@app.route("/")
def dashboard():
    return render("Company Portal", DASHBOARD_BODY)


@app.route("/inbox")
def inbox():
    emails = sorted(load_emails(), key=lambda e: e["date"], reverse=True)
    rows = "".join(
        f'<tr><td>{e["date"]}</td><td>{e["from"]}</td>'
        f'<td><a href="/inbox/{e["id"]}">{e["subject"]}</a></td></tr>'
        for e in emails
    )
    body = (
        '<table><tr><th>Date</th><th>From</th><th>Subject</th></tr>'
        f"{rows}</table>"
        '<p><a href="/">Back to dashboard</a></p>'
    )
    return render("Inbox", body)


@app.route("/inbox/<email_id>")
def inbox_item(email_id):
    emails = {e["id"]: e for e in load_emails()}
    email = emails.get(email_id)
    if email is None:
        abort(404, description=f"No email with id {email_id}")
    attach = ""
    if email.get("attachment"):
        attach = (
            f'<p>Attachment: <a href="/invoices/{email["attachment"]}">'
            f'{email["attachment"]}</a></p>'
        )
    body = (
        f"<p><b>From:</b> {email['from']}</p>"
        f"<p><b>Date:</b> {email['date']}</p>"
        f"<p><b>Subject:</b> {email['subject']}</p>"
        f"<pre>{email['body']}</pre>"
        f"{attach}"
        '<p><a href="/inbox">Back to inbox</a></p>'
    )
    return render(email["subject"], body)


@app.route("/invoices/<path:filename>")
def invoice_pdf(filename):
    # Only serve PDFs from the invoices directory.
    if not filename.endswith(".pdf") or "/" in filename or "\\" in filename:
        abort(404)
    path = INVOICES_DIR / filename
    if not path.is_file():
        abort(404)
    return send_from_directory(INVOICES_DIR, filename, mimetype="application/pdf")


@app.route("/system")
def system():
    records = load_records()
    rows = "".join(
        f"<tr><td>{r.get('vendor', '')}</td><td>{r.get('invoice_no', '')}</td>"
        f"<td>{r.get('amount', '')}</td><td>{r.get('due_date', '')}</td></tr>"
        for r in records
    )
    table = (
        "<table><tr><th>Vendor</th><th>Invoice no</th><th>Amount</th>"
        "<th>Due date</th></tr>"
        f"{rows}</table>" if records else "<p>No records entered yet.</p>"
    )
    form = """
    <h2>Enter an invoice</h2>
    <form method="post" action="/system/add">
      <label for="vendor">vendor</label>
      <input id="vendor" name="vendor" type="text">
      <label for="invoice_no">invoice_no</label>
      <input id="invoice_no" name="invoice_no" type="text">
      <label for="amount">amount</label>
      <input id="amount" name="amount" type="text">
      <label for="due_date">due_date</label>
      <input id="due_date" name="due_date" type="text">
      <button type="submit">Add record</button>
    </form>
    """
    body = f"{table}{form}<p><a href='/'>Back to dashboard</a></p>"
    return render("Internal System", body)


@app.route("/system/add", methods=["POST"])
def system_add():
    vendor = request.form.get("vendor", "").strip()
    invoice_no = request.form.get("invoice_no", "").strip()
    amount_raw = request.form.get("amount", "").strip()
    due_date = request.form.get("due_date", "").strip()
    missing = [name for name, val in
               (("vendor", vendor), ("invoice_no", invoice_no),
                ("amount", amount_raw), ("due_date", due_date)) if not val]
    if missing:
        return f"Missing required field(s): {', '.join(missing)}", 400
    try:
        amount = float(amount_raw.replace("$", "").replace(",", "").strip())
    except ValueError:
        return f"amount must be a number, got: {amount_raw!r}", 400
    records = load_records()
    records.append({
        "vendor": vendor,
        "invoice_no": invoice_no,
        "amount": amount,
        "due_date": due_date,
    })
    save_records(records)
    return redirect(url_for("system"))


@app.route("/system/api/records")
def api_records():
    return jsonify(load_records())


@app.route("/api/inbox")
def api_inbox():
    return jsonify(load_emails())


@app.route("/system/api/reset", methods=["POST"])
def api_reset():
    save_records([])
    return jsonify({"ok": True, "records": []})


if __name__ == "__main__":
    port = int(os.environ.get("MOCK_PORT", "5000"))
    app.run(host="127.0.0.1", port=port)
