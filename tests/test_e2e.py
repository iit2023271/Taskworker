"""End-to-end test: rule brain + real mock app completes the demo task.

The mock Flask app is started in-process on port 5051 for the test run.
Run:  python -m unittest discover -s tests -v
"""
import json
import threading
import unittest
from pathlib import Path

import requests

from taskworker.agent import Agent

ROOT = Path(__file__).resolve().parent.parent
GOAL = ("Find the latest invoice from Acme Supplies Ltd, extract the amount "
        "and due date, enter it into our internal system, and tell me once "
        "it is done.")
PORT = 5051
BASE = f"http://127.0.0.1:{PORT}"


def _start_mock_server():
    from mock_company.app import app
    from werkzeug.serving import make_server
    server = make_server("127.0.0.1", PORT, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


class TestEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = _start_mock_server()
        requests.post(f"{BASE}/system/api/reset", timeout=5)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_demo_task_completes_and_verifies(self):
        agent = Agent(GOAL, brain_choice="rule", auto_approve=True,
                      mock_url=BASE, max_steps=25,
                      run_dir=ROOT / "runs" / "test-e2e")
        result = agent.run()
        self.assertTrue(result["success"], result.get("summary"))
        self.assertTrue(result["verification"]["passed"])
        records = requests.get(f"{BASE}/system/api/records",
                               timeout=5).json()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["invoice_no"], "INV-2026-1042")
        self.assertEqual(records[0]["amount"], 4850.0)
        self.assertEqual(records[0]["due_date"], "2026-11-19")
        transcript = json.loads(
            (ROOT / "runs" / "test-e2e" / "transcript.json").read_text())
        tools = [s["action"]["tool"] for s in transcript["steps"]]
        self.assertIn("read_file", tools)  # the invoice PDF was read
        self.assertIn("finish", tools)


if __name__ == "__main__":
    unittest.main()
