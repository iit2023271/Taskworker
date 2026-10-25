"""Approval gate for write actions.

Write actions are browser_submit and http_post: anything that changes state
in the outside world. In supervised mode (the default) the CLI asks the user
before each write; a denial becomes an observation ("denied by user") rather
than a crash, so the agent can replan or ask the user. In auto mode
(--auto-approve) writes proceed and are logged.
"""

from __future__ import annotations

WRITE_TOOLS = frozenset({"browser_submit", "http_post"})


def is_write_action(action: dict) -> bool:
    return action.get("tool") in WRITE_TOOLS


class Approver:
    def __init__(self, auto_approve: bool = False, input_fn=None):
        self.auto_approve = auto_approve
        self.input_fn = input_fn if input_fn is not None else input
        self.log: list[dict] = []  # every approval decision, for the report

    def approve(self, action: dict) -> bool:
        """Return True if the write action may proceed."""
        tool = action.get("tool", "")
        args = action.get("args", {})
        if self.auto_approve:
            self.log.append({"tool": tool, "args": args,
                             "decision": "auto-approved"})
            return True
        answer = self.input_fn(
            f"Approve {tool} {args}? [y/n] ").strip().lower()
        ok = answer in ("y", "yes")
        self.log.append({"tool": tool, "args": args,
                         "decision": "approved" if ok else "denied"})
        return ok
