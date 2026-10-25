"""Unit tests: verifier + approval gate."""
import unittest

from taskworker.approval import Approver, is_write_action
from taskworker.verify import parse_amount, verify_records

FACTS = {"vendor": "Acme Supplies Ltd", "invoice_no": "INV-2026-1042",
         "amount": "$4,850.00", "due_date": "2026-11-19"}
RECORD = {"vendor": "Acme Supplies Ltd", "invoice_no": "INV-2026-1042",
          "amount": 4850.0, "due_date": "2026-11-19"}


class TestVerify(unittest.TestCase):
    def test_pass(self):
        result = verify_records([RECORD], FACTS)
        self.assertTrue(result["passed"])

    def test_wrong_amount_fails(self):
        bad = dict(RECORD, amount=100.0)
        self.assertFalse(verify_records([bad], FACTS)["passed"])

    def test_wrong_invoice_fails(self):
        bad = dict(RECORD, invoice_no="INV-2026-1031")
        self.assertFalse(verify_records([bad], FACTS)["passed"])

    def test_missing_record_fails(self):
        self.assertFalse(verify_records([], FACTS)["passed"])

    def test_missing_facts_fails(self):
        self.assertFalse(verify_records([RECORD], {})["passed"])

    def test_amount_parsing(self):
        self.assertEqual(parse_amount("$4,850.00"), 4850.0)
        self.assertEqual(parse_amount(4850.0), 4850.0)
        self.assertIsNone(parse_amount("n/a"))


class TestApproval(unittest.TestCase):
    def test_write_tools(self):
        self.assertTrue(is_write_action({"tool": "browser_submit"}))
        self.assertTrue(is_write_action({"tool": "http_post"}))
        self.assertFalse(is_write_action({"tool": "http_get"}))

    def test_supervised_deny_blocks(self):
        approver = Approver(auto_approve=False, input_fn=lambda _: "n")
        self.assertFalse(approver.approve({"tool": "browser_submit",
                                          "args": {}}))
        self.assertEqual(approver.log[0]["decision"], "denied")

    def test_supervised_approve_allows(self):
        approver = Approver(auto_approve=False, input_fn=lambda _: "y")
        self.assertTrue(approver.approve({"tool": "browser_submit",
                                         "args": {}}))

    def test_auto_approve_allows_and_logs(self):
        approver = Approver(auto_approve=True)
        self.assertTrue(approver.approve({"tool": "http_post", "args": {}}))
        self.assertEqual(approver.log[0]["decision"], "auto-approved")


if __name__ == "__main__":
    unittest.main()
