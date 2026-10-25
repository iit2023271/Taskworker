"""Brain interface for TaskWorker.

A Brain looks at the current run state and returns one Action dict:

    {"tool": "<name>", "args": {...}, "reasoning": "<one line>"}

The executor (agent.py) runs the action, observes the result, and calls
decide() again. Brains are stateless across runs apart from whatever they
keep on the instance; all durable run state lives in RunMemory and is passed
in via the ``state`` dict:

    state = {
        "goal": str,            # the user's natural-language task
        "facts": dict,          # memory facts so far (plain key -> value)
        "steps": [              # [{"action": ..., "observation": ...}, ...]
        "last_observation": dict | None,
        "tools": [tool schemas],
        "attempts": int,        # consecutive failed actions for current subgoal
    }
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Brain(ABC):
    """Decide the next action for the agent to take."""

    name = "base"

    @abstractmethod
    def decide(self, state: dict) -> dict:
        """Return an Action dict: {"tool", "args", "reasoning"}."""
        raise NotImplementedError


class BrainError(Exception):
    """Raised when a brain cannot produce an action.

    The executor catches this and falls back to another brain (LLM -> rule)
    instead of crashing the run.
    """
