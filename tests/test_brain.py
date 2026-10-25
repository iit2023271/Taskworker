"""Unit tests: rule brain planning + invoice field extraction."""
import unittest

from taskworker.brain.rule_brain import (
    RuleBrain,
    extract_invoice_fields,
    parse_vendor_from_goal,
    pick_latest_vendor_email,
)

GOAL = ("Find the latest invoice from Acme Supplies Ltd, extract the amount "
        "and due date, enter it into our internal system, and tell me once "
        "it is done.")


class TestGoalParsing(unittest.TestCase):
    def test_vendor_parsed(self):
        self.assertEqual(parse_vendor_from_goal(GOAL), "Acme Supplies Ltd")

    def test_vendor_missing(self):
        self.assertEqual(parse_vendor_from_goal("do something"), "")


class TestExtraction(unittest.TestCase):
    PDF_TEXT = (
        "TAX INVOICE\nVendor: Acme Supplies Ltd\n"
        "Invoice number: INV-2026-1042\n"
        "Invoice date: 20 October 2026 (2026-10-20)\n"
        "Amount due: $4,850.00\nTotal: $4,850.00\n"
        "Due date: 19 November 2026 (2026-11-19)\n")

    def test_pdf_fields(self):
        self.assertEqual(extract_invoice_fields(self.PDF_TEXT), {
            "invoice_no": "INV-2026-1042",
            "amount": "$4,850.00",
            "due_date": "2026-11-19",
        })

    def test_file_path_must_not_win(self):
        # The read_file observation header contains the lower-case file name;
        # the document's own "Invoice number:" must win over it.
        text = ("PDF runs/abc/downloads/inv-2026-1042.pdf (1 pages):\n"
                + self.PDF_TEXT)
        self.assertEqual(
            extract_invoice_fields(text)["invoice_no"], "INV-2026-1042")

    def test_bare_token_without_label(self):
        text = "Please pay INV-2026-1042 total $4,850.00 due 2026-11-19"
        self.assertEqual(extract_invoice_fields(text)["invoice_no"],
                         "INV-2026-1042")


class TestVendorPick(unittest.TestCase):
    EMAILS = [
        {"id": "2", "date": "2026-10-22", "text": "Globex Corp Invoice INV-G-881"},
        {"id": "1", "date": "2026-10-20", "text": "Acme Supplies Ltd Invoice INV-2026-1042"},
        {"id": "3", "date": "2026-09-18", "text": "Acme Supplies Ltd Invoice INV-2026-1031"},
    ]

    def test_latest_acme_not_newest_overall(self):
        picked = pick_latest_vendor_email(self.EMAILS, "Acme Supplies Ltd")
        self.assertEqual(picked["id"], "1")  # not the newer Globex email

    def test_no_match(self):
        self.assertIsNone(
            pick_latest_vendor_email(self.EMAILS, "Nonexistent Co"))


class TestRuleBrainStages(unittest.TestCase):
    def _state(self, facts, steps=None, obs=None):
        return {"goal": GOAL, "facts": facts, "steps": steps or [],
                "last_observation": obs, "attempts": 0}

    def test_stage1_opens_inbox(self):
        action = RuleBrain().decide(self._state({}))
        self.assertEqual(action["tool"], "browser_navigate")
        self.assertTrue(action["args"]["url"].endswith("/inbox"))

    def test_stage2_opens_latest_vendor_email(self):
        facts = {"inbox_seen": True, "emails": TestVendorPick.EMAILS}
        action = RuleBrain().decide(self._state(facts))
        self.assertEqual(action["tool"], "browser_navigate")
        self.assertIn("/inbox/1", action["args"]["url"])

    def test_stage3_reads_pdf_before_entering(self):
        facts = {"inbox_seen": True, "email_id": "1",
                 "pdf_path": "runs/x/downloads/inv-2026-1042.pdf",
                 "invoice_no": "INV-2026-1042", "amount": "$4,850.00",
                 "due_date": "2026-11-19"}
        action = RuleBrain().decide(self._state(facts))
        self.assertEqual(action["tool"], "read_file")
        self.assertIn("inv-2026-1042.pdf", action["args"]["path"])

    def test_stage4_fills_system_form(self):
        facts = {"inbox_seen": True, "email_id": "1", "system_seen": False,
                 "invoice_no": "INV-2026-1042", "amount": "$4,850.00",
                 "due_date": "2026-11-19"}
        action = RuleBrain().decide(self._state(facts))
        self.assertEqual(action["tool"], "browser_navigate")
        self.assertTrue(action["args"]["url"].endswith("/system"))

    def test_stage5_checks_records_then_finishes(self):
        facts = {"inbox_seen": True, "submitted": True,
                 "invoice_no": "INV-2026-1042",
                 "amount": "$4,850.00", "due_date": "2026-11-19",
                 "vendor": "Acme Supplies Ltd"}
        action = RuleBrain().decide(self._state(facts))
        self.assertEqual(action["tool"], "http_get")
        self.assertIn("/system/api/records", action["args"]["url"])
        state = self._state(
            facts,
            steps=[{"action": {"tool": "http_get",
                               "args": {"url": "http://x/system/api/records"}}}],
            obs={"ok": True, "text": '[{"invoice_no": "INV-2026-1042"}]'})
        action = RuleBrain().decide(state)
        self.assertEqual(action["tool"], "finish")


if __name__ == "__main__":
    unittest.main()
