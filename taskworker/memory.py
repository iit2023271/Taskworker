"""Run memory: facts discovered during a run + the step transcript.

Facts are stored as key -> {"value", "source", "must_verify"}. The verifier
needs vendor / invoice_no / amount / due_date, so those are marked
must_verify=True when recorded.
"""

from __future__ import annotations

import json
from pathlib import Path


class RunMemory:
    def __init__(self) -> None:
        self.facts: dict[str, dict] = {}
        self.steps: list[dict] = []

    # -- facts -----------------------------------------------------------
    def set_fact(self, key: str, value, source: str = "",
                 must_verify: bool = False) -> None:
        """Record a fact. Does not overwrite an existing fact with an empty
        value, and never downgrades must_verify once set."""
        if value is None or value == "":
            return
        existing = self.facts.get(key)
        if existing is not None:
            must_verify = must_verify or existing.get("must_verify", False)
        self.facts[key] = {
            "value": value,
            "source": source,
            "must_verify": bool(must_verify),
        }

    def get_fact(self, key: str, default=None):
        entry = self.facts.get(key)
        return entry["value"] if entry is not None else default

    def has_fact(self, key: str) -> bool:
        return key in self.facts and self.facts[key]["value"] not in (None, "")

    def plain_facts(self) -> dict:
        """Facts as a plain key -> value dict (what brains see)."""
        return {k: v["value"] for k, v in self.facts.items()}

    def must_verify_facts(self) -> dict:
        return {k: v["value"] for k, v in self.facts.items()
                if v.get("must_verify")}

    # -- steps -----------------------------------------------------------
    def record_step(self, action: dict, observation: dict) -> None:
        self.steps.append({"action": action, "observation": observation})

    # -- persistence -----------------------------------------------------
    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"facts": self.facts, "steps": self.steps}, f,
                      indent=2, default=str)
        return path

    @classmethod
    def load(cls, path: str | Path) -> "RunMemory":
        mem = cls()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        mem.facts = data.get("facts", {})
        mem.steps = data.get("steps", [])
        return mem
