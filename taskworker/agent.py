"""Agent: the ReAct loop executor.

Each turn: brain decides one action -> approval gate (writes) -> tool runs
-> observation is recorded and mined for facts -> loop. When the brain
calls finish, the outcome is verified against the internal system; the run
only reports success when verification passes. If the LLM brain fails
(bad JSON, API error, missing key), the executor falls back to the
offline RuleBrain for the rest of the run.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from .approval import Approver, is_write_action
from .brain.base import BrainError
from .brain.llm_brain import LLMBrain
from .brain.rule_brain import RuleBrain, extract_observation_facts
from .memory import RunMemory
from .report import write_report
from .tools.base import ToolContext
from .tools.registry import get_schemas, run_tool
from .verify import verify_via_api


class Agent:
    def __init__(self, goal: str, brain=None, mock_url: str = "http://127.0.0.1:5000",
                 max_steps: int = 30, auto_approve: bool = False,
                 run_dir: str | Path | None = None, input_fn=None,
                 brain_choice: str = "auto"):
        self.goal = goal
        self.mock_url = mock_url.rstrip("/")
        self.max_steps = max_steps
        self.run_id = (Path(run_dir).name if run_dir
                       else uuid.uuid4().hex[:8])
        self.run_dir = Path(run_dir) if run_dir else Path("runs") / self.run_id
        self.memory = RunMemory()
        self.approver = Approver(auto_approve=auto_approve,
                                 input_fn=input_fn)
        self.ctx = ToolContext(run_dir=self.run_dir, memory=self.memory,
                               mock_url=self.mock_url,
                               input_fn=input_fn or input)
        self.brain_choice = brain_choice
        self.brain = brain or self._select_brain(brain_choice)
        self._fell_back = False
        self._consecutive_failures = 0
        self._verify_failures = 0

    # -- brain selection ---------------------------------------------------
    def _select_brain(self, choice: str):
        if choice == "llm":
            return LLMBrain()
        if choice == "rule":
            return RuleBrain(self.mock_url)
        # auto: LLM when a key is present, else the offline planner
        if LLMBrain.available():
            return LLMBrain()
        return RuleBrain(self.mock_url)

    def _fallback_brain(self):
        """Switch to the offline planner after an LLM failure."""
        if isinstance(self.brain, RuleBrain):
            return None
        self.brain = RuleBrain(self.mock_url)
        self._fell_back = True
        return self.brain

    # -- state -------------------------------------------------------------
    def _state(self) -> dict:
        return {
            "goal": self.goal,
            "facts": self.memory.plain_facts(),
            "steps": self.memory.steps,
            "last_observation": (self.memory.steps[-1]["observation"]
                                 if self.memory.steps else None),
            "tools": get_schemas(),
            "attempts": self._consecutive_failures,
        }

    # -- verification ------------------------------------------------------
    def _verify(self) -> dict:
        facts = self.memory.must_verify_facts()
        if not facts:
            facts = self.memory.plain_facts()
        return verify_via_api(
            f"{self.mock_url}/system/api/records", facts,
            lambda url: run_tool("http_get", {"url": url}, self.ctx))

    # -- main loop ---------------------------------------------------------
    def run(self) -> dict:
        result: dict = {"success": False, "summary": "", "steps": 0,
                        "verification": {"passed": False, "detail": "not run"},
                        "run_dir": str(self.run_dir),
                        "brain": self.brain.name,
                        "fell_back_to_rule": False}
        try:
            for _ in range(self.max_steps):
                try:
                    action = self.brain.decide(self._state())
                except BrainError as e:
                    failed_name = self.brain.name
                    fallback = self._fallback_brain()
                    if fallback is None:
                        result["summary"] = f"brain failed: {e}"
                        break
                    result["fell_back_to_rule"] = True
                    print(f"[agent] {failed_name} brain failed ({e}); "
                          "falling back to the offline planner.")
                    action = self.brain.decide(self._state())
                if not isinstance(action, dict) or "tool" not in action:
                    result["summary"] = f"brain returned an invalid action: {action!r}"
                    break
                action.setdefault("args", {})
                action.setdefault("reasoning", "")

                if action["tool"] == "finish":
                    verification = self._verify()
                    result["verification"] = verification
                    if verification["passed"]:
                        result["success"] = True
                        result["summary"] = action["args"].get(
                            "summary", "task completed")
                        self.memory.record_step(
                            action, {"ok": True,
                                     "text": f"Verified: {verification['detail']}",
                                     "screenshot": None, "data": {}})
                        break
                    self._verify_failures += 1
                    obs = {"ok": False,
                           "text": "Verification failed: "
                                   f"{verification['detail']}. The record is "
                                   "not (correctly) in the internal system yet.",
                           "screenshot": None, "data": {}}
                    self.memory.record_step(action, obs)
                    self._consecutive_failures += 1
                    if self._verify_failures >= 2:
                        result["summary"] = ("verification failed twice: "
                                             f"{verification['detail']}")
                        break
                    continue

                if is_write_action(action):
                    if not self.approver.approve(action):
                        obs = {"ok": False, "text": "denied by user",
                               "screenshot": None, "data": {}}
                        self.memory.record_step(action, obs)
                        self._consecutive_failures += 1
                        continue

                obs = run_tool(action["tool"], action["args"], self.ctx)
                self.memory.record_step(action, obs)
                if action["tool"] == "ask_user" and not obs.get("ok"):
                    # the user channel failed (EOF / no terminal): asking
                    # again would loop forever, so end the run here.
                    result["summary"] = ("could not ask the user: "
                                         f"{obs.get('text', '')[:200]}")
                    self.memory.save(self.run_dir / "transcript.json")
                    break
                new_facts = extract_observation_facts(
                    obs, self.goal, last_action=action)
                for key, value in new_facts.items():
                    must = key in ("vendor", "invoice_no", "amount", "due_date")
                    self.memory.set_fact(key, value, source=action["tool"],
                                         must_verify=must)
                if obs.get("ok"):
                    self._consecutive_failures = 0
                else:
                    self._consecutive_failures += 1
                self.memory.save(self.run_dir / "transcript.json")
            else:
                result["summary"] = (f"stopped after {self.max_steps} steps "
                                     "without finishing")
        finally:
            result["steps"] = len(self.memory.steps)
            result["brain"] = self.brain.name
            result["fell_back_to_rule"] = self._fell_back
            write_report(self.run_dir, self.goal, result, self.memory,
                         approval_log=self.approver.log)
            browser = self.ctx.browser
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass
        return result
