"""RuleBrain: offline goal-directed planner.

Not a fixed script: it keeps a subgoal checklist derived from the goal text
(vendor parsed from "from <Vendor>") and picks the next action from memory
facts + the last observation:

  1. no inbox seen            -> open {mock}/inbox (fallback: GET /api/inbox)
  2. inbox seen, none chosen  -> open the latest email from the vendor
  3. email seen with PDF link -> read the downloaded PDF
                                 (fallback: extract from the email body)
  4. amount + due date + invoice no known -> open /system, fill each
     field, submit (the approval gate applies)
  5. submitted                -> GET /system/api/records, compare, finish

Retries: a failed tool is retried once, then an alternative route is tried
(browser <-> HTTP API). If both routes fail, it asks the user.

Nothing about the demo answer is hardcoded: vendor, invoice number, amount
and dates all come from observations. The extraction helpers in this module
are also used by the executor so the verifier sees the same facts whichever
brain drove the run.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from .base import Brain

MONTHS = {name: i + 1 for i, name in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"])}
MONTHS_ABBR = {name[:3]: i + 1 for i, name in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"])}


# ---------------------------------------------------------------------------
# goal parsing
# ---------------------------------------------------------------------------

def parse_vendor_from_goal(goal: str) -> str:
    """Vendor named in '... invoice from <Vendor> ...'."""
    match = re.search(r"from\s+([^,;]+?)(?:,|\s+extract|\s+and\s+enter|\s*$)",
                      goal or "", re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


# ---------------------------------------------------------------------------
# field extraction from free text (invoice PDFs, email bodies, pages)
# ---------------------------------------------------------------------------

def _to_iso_date(year: str, month: str, day: str) -> str:
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def extract_invoice_fields(text: str) -> dict:
    """Regex-extract invoice_no, amount and due_date from text.

    Amount: prefers a $ figure on a line mentioning total / amount due /
    balance due; otherwise the largest $ figure. Due date: prefers a date
    on a line mentioning 'due'; otherwise the latest ISO date found.
    """
    found: dict = {}
    if not text:
        return found

    # -- invoice number ----------------------------------------------------
    # Labeled forms first ("Invoice number: INV-..."), then bare INV tokens.
    # Matches that are part of a file path (preceded by "/", followed by
    # ".pdf") are skipped — the observation header contains the downloaded
    # file name, whose lower-case "inv-..." must not win over the document.
    def _clean(value: str) -> str:
        return re.sub(r"\s+", "-", value.strip())

    for pattern in (r"Invoice\s+(?:No\.?|#|Number)\s*[:#]?\s*"
                    r"([A-Za-z0-9][A-Za-z0-9\-]*)",
                    r"\bINV[-\s]?[A-Z0-9][A-Z0-9\-]*\d\b"):
        for match in re.finditer(pattern, text, re.IGNORECASE):
            start = match.start(1) if match.lastindex else match.start(0)
            if start > 0 and text[start - 1] == "/":
                continue
            end = match.end(1) if match.lastindex else match.end(0)
            if text[end:end + 4].lower() == ".pdf":
                continue
            value = _clean(match.group(1) if match.lastindex
                           else match.group(0))
            if re.search(r"\d", value):
                found["invoice_no"] = value
                break
        if found.get("invoice_no"):
            break

    # -- amount ------------------------------------------------------------
    amounts = []  # (value, is_total_line)
    for line in text.splitlines():
        for m in re.finditer(r"\$([\d,]+\.\d{2})", line):
            value = float(m.group(1).replace(",", ""))
            total_line = bool(re.search(
                r"total|amount due|balance due|amount payable",
                line, re.IGNORECASE))
            amounts.append((value, total_line))
    if amounts:
        totals = [v for v, t in amounts if t]
        picked = max(totals) if totals else max(v for v, _ in amounts)
        found["amount"] = f"${picked:,.2f}"

    # -- due date ----------------------------------------------------------
    due: str | None = None
    iso_dates = re.findall(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    for line in text.splitlines():
        if not re.search(r"\bdue\b", line, re.IGNORECASE):
            continue
        m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", line)
        if m:
            due = _to_iso_date(*m.groups())
            break
        m = re.search(r"\b(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\b", line)
        if m and m.group(2).capitalize() in MONTHS:
            due = _to_iso_date(m.group(3), MONTHS[m.group(2).capitalize()],
                               m.group(1))
            break
        m = re.search(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),\s*(\d{4})\b", line)
        if m and m.group(1).capitalize()[:3] in MONTHS_ABBR:
            due = _to_iso_date(m.group(3),
                               MONTHS_ABBR[m.group(1).capitalize()[:3]],
                               m.group(2))
            break
    if due is None and iso_dates:
        due = _to_iso_date(*max(iso_dates))
    if due is None:
        for pattern, groups in (
                (r"\b(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\b", "dmy"),
                (r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),\s*(\d{4})\b", "mdy")):
            m = re.search(pattern, text)
            if not m:
                continue
            if groups == "dmy" and m.group(2).capitalize() in MONTHS:
                due = _to_iso_date(m.group(3),
                                   MONTHS[m.group(2).capitalize()], m.group(1))
                break
            if groups == "mdy" and m.group(1).capitalize()[:3] in MONTHS_ABBR:
                due = _to_iso_date(m.group(3),
                                   MONTHS_ABBR[m.group(1).capitalize()[:3]],
                                   m.group(2))
                break
    if due:
        found["due_date"] = due
    return found


# ---------------------------------------------------------------------------
# observation -> facts (shared with the executor)
# ---------------------------------------------------------------------------

def _parse_inbox_rows(text: str, links: list) -> list:
    """Turn an inbox page into email candidates.

    Rows are recognised by a YYYY-MM-DD date starting a run of lines; links
    to /inbox/<id> appear in the same document order, so they are zipped
    with the rows. If the counts do not line up, ids stay unknown and the
    brain falls back to the JSON inbox API. The "Links:" / "Forms:" trailer
    the browser appends to its observation is cut off first, so it is not
    mistaken for another row.
    """
    # cut off the browser's appended Links:/Forms: trailer
    cut = len(text)
    for marker in ("\nLinks:", "\nForms:", "\nDownloaded PDFs:"):
        pos = text.find(marker)
        if pos != -1:
            cut = min(cut, pos)
    text = text[:cut]
    rows: list[dict] = []
    current = None
    for line in text.splitlines():
        match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", line)
        if match:
            if current:
                rows.append(current)
            current = {"date": match.group(1), "text": line.strip()}
        elif current and line.strip():
            current["text"] += " " + line.strip()
    if current:
        rows.append(current)
    email_links = []
    for link in links or []:
        m = re.search(r"/inbox/(\d+)", link.get("href", ""))
        if m:
            email_links.append({"id": m.group(1), "href": link["href"],
                                "text": link.get("text", "")})
    emails = []
    for i, row in enumerate(rows):
        entry = {"date": row["date"], "text": row["text"],
                 "from": row["text"], "subject": row["text"]}
        if i < len(email_links):
            entry["id"] = email_links[i]["id"]
            entry["href"] = email_links[i]["href"]
            entry["text"] = row["text"] + " " + email_links[i]["text"]
        emails.append(entry)
    return emails


def _vendor_tokens(vendor: str) -> list:
    """Significant words of a vendor name for matching.

    The inbox shows the sender's email address (billing@acmesupplies.com),
    not the display name, so match on name words like 'acme' instead of
    requiring the full name. Generic suffixes are dropped.
    """
    stop = {"ltd", "ltd.", "inc", "inc.", "corp", "corp.", "co", "co.",
            "company", "the", "and", "llc", "llp", "group"}
    return [w for w in re.split(r"[^A-Za-z0-9]+", (vendor or "").lower())
            if len(w) >= 3 and w not in stop]


def pick_latest_vendor_email(emails: list, vendor: str) -> dict | None:
    """Latest email from the vendor.

    Matches any significant word of the vendor name (the inbox lists the
    sender's email address, not the display name). Among matches, prefers
    emails that look like invoices (subject/body mentions invoice), then
    takes the latest date.
    """
    tokens = _vendor_tokens(vendor)
    if not tokens:
        return None
    candidates = []
    for e in emails:
        haystack = " ".join(str(e.get(k, "") or "")
                            for k in ("text", "from", "subject")).lower()
        if any(t in haystack for t in tokens):
            candidates.append(e)
    if not candidates:
        return None
    invoicelike = [e for e in candidates
                   if "invoice" in (e.get("text", "") or "").lower()
                   or re.search(r"\binv[-\s]", (e.get("text", "") or ""),
                                re.IGNORECASE)]
    pool = invoicelike or candidates
    return max(pool, key=lambda e: e.get("date", ""))


def extract_observation_facts(obs: dict, goal: str,
                              last_action: dict | None = None) -> dict:
    """Pull durable facts out of one observation.

    Returns a dict of fact key -> value for the executor to store in memory.
    """
    facts: dict = {}
    if not obs:
        return facts
    text = obs.get("text", "") or ""
    data = obs.get("data", {}) or {}
    url = data.get("url", "") or ""

    vendor = parse_vendor_from_goal(goal)
    if vendor:
        facts.setdefault("vendor", vendor)

    if re.search(r"/inbox/?$", url):
        facts["inbox_seen"] = True
        emails = _parse_inbox_rows(text, data.get("links", []))
        if emails:
            facts["emails"] = emails
    if re.search(r"/api/inbox", url):
        facts["inbox_seen"] = True
        records = data.get("json")
        if isinstance(records, list):
            facts["emails"] = [
                {"id": str(r.get("id", "")), "date": r.get("date", ""),
                 "from": r.get("from", ""), "subject": r.get("subject", ""),
                 "text": f"{r.get('date', '')} {r.get('from', '')} "
                         f"{r.get('from_name', '')} {r.get('subject', '')} "
                         f"{r.get('body', '')}",
                 "href": f"/inbox/{r.get('id', '')}"}
                for r in records]
        elif isinstance(records, dict) and isinstance(
                records.get("emails"), list):
            facts["emails"] = records["emails"]

    match = re.search(r"/inbox/(\d+)", url)
    if match:
        facts["email_id"] = match.group(1)
        facts["email_seen"] = True
        facts["email_body"] = text

    if data.get("pdf"):
        facts["pdf_path"] = data["pdf"]

    # Invoice fields only come from an actual invoice source (an email page
    # or a file read) — never from a list page, where the first invoice
    # number / latest date in the table would be a false positive.
    is_invoice_source = (
        re.search(r"/inbox/\d+", url) is not None
        or str(data.get("path", "")).lower().endswith(".pdf")
        or (last_action or {}).get("tool") == "read_file")
    if is_invoice_source:
        fields = extract_invoice_fields(text)
        for key in ("invoice_no", "amount", "due_date"):
            if fields.get(key):
                facts[key] = fields[key]

    if re.search(r"/system/?$", url):
        facts["system_seen"] = True
    if last_action and last_action.get("tool") in ("browser_submit", "http_post"):
        target = str(last_action.get("args", {}).get("url", ""))
        if obs.get("ok") and ("system/add" in target or
                              "Form submitted" in text):
            facts["submitted"] = True
    return facts


# ---------------------------------------------------------------------------
# the brain
# ---------------------------------------------------------------------------

class RuleBrain(Brain):
    name = "rule"

    def __init__(self, mock_url: str = "http://127.0.0.1:5000"):
        self.mock_url = mock_url.rstrip("/")
        self._vendor: str | None = None
        self._reentered = False  # already retried the system entry once

    # -- helpers -----------------------------------------------------------
    def _vendor_of(self, goal: str) -> str:
        if self._vendor is None:
            self._vendor = parse_vendor_from_goal(goal)
        return self._vendor or ""

    @staticmethod
    def _act(tool: str, args: dict, reasoning: str) -> dict:
        return {"tool": tool, "args": args, "reasoning": reasoning}

    def _retry(self, action: dict) -> dict:
        retry = dict(action)
        retry["reasoning"] = f"retrying after failure: {action.get('reasoning', '')}"
        return retry

    def _typed_fields(self, steps: list) -> set:
        """Form labels already filled on the current /system visit."""
        typed = set()
        for step in steps:
            action = step.get("action", {})
            if action.get("tool") == "browser_navigate" and \
                    str(action.get("args", {}).get("url", "")).rstrip("/").endswith("/system"):
                typed = set()
            if action.get("tool") == "browser_type":
                typed.add(str(action.get("args", {}).get("label", "")).lower())
        return typed

    def _form_post_action(self, facts: dict) -> dict:
        return self._act("http_post", {
            "url": f"{self.mock_url}/system/add",
            "form": {
                "vendor": facts.get("vendor", ""),
                "invoice_no": facts.get("invoice_no", ""),
                "amount": facts.get("amount", ""),
                "due_date": facts.get("due_date", ""),
            }}, "browser form failed; entering the record via form POST")

    # -- failure handling --------------------------------------------------
    def _alternative(self, last_action: dict, facts: dict) -> dict:
        """Second failure on the same subgoal: try the other route."""
        tool = last_action.get("tool")
        args = last_action.get("args", {})
        url = str(args.get("url", ""))
        if tool == "browser_navigate" and url.rstrip("/").endswith("/inbox"):
            return self._act("http_get", {"url": f"{self.mock_url}/api/inbox"},
                             "browser inbox failed; reading the inbox JSON API")
        if tool == "http_get" and url.rstrip("/").endswith("/api/inbox"):
            return self._act("browser_navigate",
                             {"url": f"{self.mock_url}/inbox"},
                             "inbox API failed; going back to the browser inbox")
        if tool == "browser_navigate" and "/inbox/" in url:
            return self._act("http_get", {"url": url},
                             "browser email view failed; fetching the email page")
        if tool == "read_file":
            if facts.get("amount") and facts.get("due_date"):
                return self._system_action(facts, [])
            return self._act("ask_user", {
                "question": "I could not read the invoice PDF. What is the "
                            "invoice amount and due date?"},
                "the invoice PDF could not be read")
        if tool in ("browser_navigate", "browser_submit") and \
                url.rstrip("/").endswith("/system"):
            return self._form_post_action(facts)
        if tool == "browser_submit":
            return self._form_post_action(facts)
        if tool == "http_post":
            return self._act("ask_user", {
                "question": "Entering the record into the internal system "
                            "failed twice. Should I keep trying, or enter it "
                            "manually?"},
                "both entry routes failed")
        return self._act("ask_user", {
            "question": f"The step {tool} failed twice. How should I proceed?"},
            "out of automatic alternatives")

    # -- main progression --------------------------------------------------
    def _system_action(self, facts: dict, steps: list) -> dict:
        """Stage 4: get the record into /system (browser form, field by field)."""
        typed = self._typed_fields(steps)
        fields = [("vendor", facts.get("vendor", "")),
                  ("invoice_no", facts.get("invoice_no", "")),
                  ("amount", facts.get("amount", "")),
                  ("due_date", facts.get("due_date", ""))]
        if not facts.get("system_seen"):
            return self._act("browser_navigate",
                             {"url": f"{self.mock_url}/system"},
                             "opening the internal system to enter the invoice")
        for label, value in fields:
            if label not in typed and value:
                return self._act("browser_type",
                                 {"label": label, "text": str(value)},
                                 f"filling the {label} field")
        return self._act("browser_submit", {},
                         "submitting the invoice record")

    def decide(self, state: dict) -> dict:
        goal = state.get("goal", "")
        facts = state.get("facts", {}) or {}
        steps = state.get("steps", []) or []
        obs = state.get("last_observation")
        attempts = state.get("attempts", 0)
        vendor = self._vendor_of(goal)

        # --- failure handling: retry once, then an alternative route ------
        if obs is not None and not obs.get("ok", True) and steps:
            last = steps[-1].get("action", {})
            if last.get("tool") == "ask_user":
                # the user channel itself failed: stop instead of asking again
                return self._act("finish", {
                    "summary": "Stopped: could not reach the user for "
                               "guidance, so the task cannot proceed safely."},
                    "the user channel failed; stopping instead of asking again")
            if attempts <= 1:
                return self._retry(last)
            return self._alternative(last, facts)

        # --- stage 1: find the inbox --------------------------------------
        if not facts.get("inbox_seen") and not facts.get("emails"):
            return self._act("browser_navigate",
                             {"url": f"{self.mock_url}/inbox"},
                             "opening the inbox to find the invoice email")

        # --- stage 2: pick the latest email from the vendor --------------
        if facts.get("emails") and not facts.get("email_id"):
            emails = facts["emails"]
            if not any(e.get("id") for e in emails):
                return self._act("http_get",
                                 {"url": f"{self.mock_url}/api/inbox"},
                                 "inbox rows have no usable links; "
                                 "reading the inbox JSON API")
            email = pick_latest_vendor_email(emails, vendor)
            if email is None:
                return self._act("ask_user", {
                    "question": f"I found {len(emails)} emails but none "
                                f"from {vendor or 'the vendor named in the task'}. "
                                "Should I use the newest email instead?"},
                    "no email from the vendor in the inbox")
            href = email.get("href") or f"/inbox/{email.get('id', '')}"
            url = urljoin(self.mock_url + "/", href)
            return self._act("browser_navigate",
                             {"url": url},
                             f"opening the latest {vendor} email "
                             f"({email.get('date', '')})")

        # --- stage 3: read the invoice ------------------------------------
        have_fields = all(facts.get(k) for k in
                          ("invoice_no", "amount", "due_date"))
        # The invoice PDF is the source of truth: when one was downloaded,
        # read it even if the email body already mentioned the figures
        # (the PDF read overwrites those facts with the document's values).
        pdf_read = any(s.get("action", {}).get("tool") == "read_file"
                       for s in steps)
        if facts.get("email_id") and (not have_fields or
                                      (facts.get("pdf_path") and not pdf_read)):
            if facts.get("pdf_path") and not pdf_read:
                return self._act("read_file", {"path": facts["pdf_path"]},
                                 "reading the invoice PDF")
            links = []
            if obs:
                links = (obs.get("data", {}) or {}).get("links", [])
            for link in links:
                if link.get("href", "").lower().endswith(".pdf"):
                    return self._act(
                        "browser_navigate",
                        {"url": urljoin(self.mock_url + "/",
                                        link["href"])},
                        "opening the attached invoice PDF")
            if facts.get("email_body"):
                return self._act("ask_user", {
                    "question": "The email has no invoice PDF attached. "
                                "What are the invoice number, amount and due date?"},
                    "no PDF attached to the email")
            return self._act("browser_read", {},
                             "re-reading the email to find the attachment")

        # --- stage 4: enter the record ------------------------------------
        if have_fields and not facts.get("submitted"):
            return self._system_action(facts, steps)

        # --- stage 5: check the system, then finish -----------------------
        if facts.get("submitted"):
            if not any(s.get("action", {}).get("tool") == "http_get" and
                       "/system/api/records" in
                       str(s.get("action", {}).get("args", {}).get("url", ""))
                       for s in steps):
                return self._act("http_get",
                                 {"url": f"{self.mock_url}/system/api/records"},
                                 "checking the internal system for the record")
            records_text = (obs or {}).get("text", "") or ""
            if facts.get("invoice_no") and facts["invoice_no"] in records_text:
                return self._act("finish", {
                    "summary": f"Entered invoice {facts.get('invoice_no')} "
                               f"from {facts.get('vendor')} "
                               f"({facts.get('amount')}, due "
                               f"{facts.get('due_date')}) into the internal "
                               "system and confirmed it is listed there."},
                    "record confirmed in the internal system")
            if not self._reentered:
                self._reentered = True
                return self._act("browser_navigate",
                                 {"url": f"{self.mock_url}/system"},
                                 "record not found after submitting; "
                                 "re-entering it once")
            return self._act("ask_user", {
                "question": "I submitted the invoice but it does not appear "
                            "in the internal system. Should I try again?"},
                "record missing after submission")

        # --- nothing matches: ask ------------------------------------------
        return self._act("ask_user", {
            "question": "I am not sure how to proceed with this task. "
                        "What should I do next?"},
            "no subgoal matches the current state")
