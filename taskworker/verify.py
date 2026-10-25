"""Verification: did the run actually achieve the goal?

After the brain calls finish, the executor fetches the internal system's
records and checks that a record matching the facts the agent collected
(vendor + invoice_no) exists with the same amount and due date. The run
only reports success when this passes.
"""

from __future__ import annotations

import re


def parse_amount(value) -> float | None:
    """Parse "$4,850.00" / "4850.00" / 4850.0 -> 4850.0. None if unparseable."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("$", "").replace(",", "").strip()
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def normalise_date(value) -> str:
    return str(value).strip() if value is not None else ""


def verify_records(records: list, facts: dict) -> dict:
    """Pure check, easy to unit test.

    records: list of dicts from GET /system/api/records.
    facts: must contain vendor and invoice_no; amount and due_date compared
    when present.
    Returns {"passed": bool, "detail": str}.
    """
    vendor = str(facts.get("vendor", "")).strip().lower()
    invoice_no = str(facts.get("invoice_no", "")).strip()
    if not vendor or not invoice_no:
        return {"passed": False,
                "detail": "cannot verify: vendor or invoice_no missing "
                          f"from facts (vendor={vendor!r}, "
                          f"invoice_no={invoice_no!r})"}

    candidates = []
    for rec in records or []:
        rec_vendor = str(rec.get("vendor", "")).strip().lower()
        rec_no = str(rec.get("invoice_no", "")).strip()
        if rec_no == invoice_no and (not vendor or vendor in rec_vendor
                                     or rec_vendor in vendor):
            candidates.append(rec)
    if not candidates:
        return {"passed": False,
                "detail": f"no record found in the internal system for "
                          f"invoice {invoice_no} from {facts.get('vendor')}"}

    rec = candidates[-1]  # latest matching entry wins
    problems = []
    want_amount = parse_amount(facts.get("amount"))
    got_amount = parse_amount(rec.get("amount"))
    if want_amount is not None and got_amount is not None:
        if abs(want_amount - got_amount) > 0.005:
            problems.append(f"amount mismatch: system has {rec.get('amount')!r}, "
                            f"invoice says {facts.get('amount')!r}")
    elif want_amount is not None:
        problems.append(f"amount {rec.get('amount')!r} in system is not a number")
    want_due = normalise_date(facts.get("due_date"))
    got_due = normalise_date(rec.get("due_date"))
    if want_due and got_due and want_due != got_due:
        problems.append(f"due date mismatch: system has {got_due!r}, "
                        f"invoice says {want_due!r}")
    if problems:
        return {"passed": False, "detail": "; ".join(problems)}
    return {"passed": True,
            "detail": f"record for invoice {invoice_no} found in the "
                      f"internal system: amount {rec.get('amount')}, "
                      f"due {rec.get('due_date')}"}


def verify_via_api(records_url: str, facts: dict, http_get) -> dict:
    """Fetch records over HTTP and verify. ``http_get`` is a callable taking
    a URL and returning an Observation dict (keeps this module free of
    network imports, so tests can inject a stub)."""
    try:
        obs = http_get(records_url)
    except Exception as e:  # noqa: BLE001 - report transport errors as failure
        return {"passed": False, "detail": f"could not fetch records: {e}"}
    if not obs.get("ok"):
        return {"passed": False,
                "detail": f"could not fetch records: {obs.get('text', '')[:200]}"}
    data = obs.get("data", {}) or {}
    records = data.get("json", data.get("records", []))
    if isinstance(records, dict):
        records = records.get("records", [])
    if not isinstance(records, list):
        return {"passed": False,
                "detail": "records endpoint did not return a JSON list"}
    return verify_records(records, facts)
