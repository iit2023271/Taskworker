"""LLMBrain: decide the next action with an OpenAI-compatible chat model.

Configuration from the environment:
    OPENAI_API_KEY   (required; without it the brain cannot run)
    OPENAI_BASE_URL  (default https://api.openai.com/v1)
    OPENAI_MODEL     (default gpt-4o-mini)

The model is prompted with the tool schemas and must reply with exactly one
JSON action: {"tool": ..., "args": {...}, "reasoning": "..."}. A reply that
is not valid JSON is corrected once; a second failure raises BrainError,
which the executor catches and falls back to the RuleBrain.
"""

from __future__ import annotations

import json
import os

import requests

from .base import Brain, BrainError

SYSTEM_PROMPT = """You are TaskWorker, an autonomous AI worker. You complete the
user's task by choosing ONE tool call per turn. Reply with ONLY a JSON object:

{"tool": "<tool name>", "args": {...}, "reasoning": "<one line>"}

Rules:
- Use the tools listed below; never invent a tool or an argument.
- Work step by step: look, then act, then check the observation before the
  next step. Do not guess facts you have not observed.
- Prefer the browser for reading pages and filling forms; use http_get /
  http_post only when the browser cannot do the job.
- Filling a form takes several steps: navigate to the form, type each field,
  then submit. Do not submit before every field is filled.
- When every part of the goal is done, call finish with a short summary of
  what was accomplished. Only call finish when you have actually observed
  the outcome (for example, the record appearing in the internal system).
- If you cannot proceed safely, or information is missing, call ask_user
  with a clear question instead of guessing.
- If an action fails, retry it once; if it fails again, try a different
  route (browser <-> HTTP API) before asking the user.
"""

MAX_HISTORY_STEPS = 12
MAX_OBS_CHARS = 1500


class LLMBrain(Brain):
    name = "llm"

    def __init__(self, api_key: str | None = None,
                 base_url: str | None = None,
                 model: str | None = None, timeout: int = 60):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.environ.get(
            "OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self.timeout = timeout

    @classmethod
    def available(cls) -> bool:
        """True when an API key is configured (used by --brain auto)."""
        return bool(os.environ.get("OPENAI_API_KEY"))

    # -- prompting ---------------------------------------------------------
    def _messages(self, state: dict) -> list:
        tools = state.get("tools", [])
        tool_text = "\n".join(
            f"- {t['name']}{t.get('args', {})}: {t.get('description', '')}"
            for t in tools)
        lines = [f"GOAL: {state.get('goal', '')}"]
        facts = state.get("facts", {}) or {}
        if facts:
            lines.append("FACTS SO FAR:")
            for key, value in facts.items():
                lines.append(f"- {key}: {value}")
        steps = state.get("steps", []) or []
        if steps:
            lines.append("STEPS TAKEN:")
            for i, step in enumerate(steps[-MAX_HISTORY_STEPS:], 1):
                action = step.get("action", {})
                obs = step.get("observation", {}) or {}
                obs_text = (obs.get("text", "") or "")[:MAX_OBS_CHARS]
                lines.append(
                    f"{i}. {action.get('tool')} {action.get('args')} "
                    f"-> ok={obs.get('ok')}: {obs_text}")
        last = state.get("last_observation")
        if last:
            lines.append("LAST OBSERVATION:")
            lines.append((last.get("text", "") or "")[:MAX_OBS_CHARS])
        user = "\n".join(lines) + (
            "\n\nTOOLS:\n" + tool_text +
            "\n\nReply with ONLY the JSON action for the next step.")
        return [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user}]

    def _call(self, messages: list) -> str:
        if not self.api_key:
            raise BrainError(
                "LLMBrain needs an API key: set OPENAI_API_KEY "
                "(or run with --brain rule for the offline planner).")
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
                json={"model": self.model, "messages": messages,
                      "temperature": 0},
                timeout=self.timeout)
        except Exception as e:  # noqa: BLE001
            raise BrainError(f"LLM request failed: {e}") from e
        if resp.status_code != 200:
            raise BrainError(
                f"LLM API returned HTTP {resp.status_code}: "
                f"{resp.text[:300]}")
        try:
            content = resp.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, ValueError) as e:
            raise BrainError(f"unexpected LLM response shape: {e}") from e
        return content

    @staticmethod
    def _parse_action(content: str, tools: list) -> dict:
        """Parse one JSON action out of a model reply (tolerates fences)."""
        text = content.strip()
        if text.startswith("```"):
            text = re_sub_fences(text)
        try:
            action = json.loads(text)
        except ValueError as e:
            raise BrainError(f"LLM reply was not valid JSON: {e}") from e
        if not isinstance(action, dict) or "tool" not in action:
            raise BrainError(
                "LLM reply is not an action object "
                f"(needs 'tool' and 'args'): {content[:300]}")
        known = {t["name"] for t in tools}
        if action["tool"] not in known:
            raise BrainError(
                f"LLM chose unknown tool {action['tool']!r}; "
                f"known tools: {sorted(known)}")
        action.setdefault("args", {})
        if not isinstance(action["args"], dict):
            raise BrainError("LLM action 'args' must be an object")
        action.setdefault("reasoning", "")
        return action

    # -- Brain interface ---------------------------------------------------
    def decide(self, state: dict) -> dict:
        tools = state.get("tools", [])
        messages = self._messages(state)
        content = ""
        try:
            content = self._call(messages)
            return self._parse_action(content, tools)
        except BrainError as first_error:
            # One correction round: tell the model what went wrong.
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content":
                             f"Your last reply was not usable: {first_error}. "
                             "Reply now with ONLY a JSON action object, "
                             "no other text."})
            try:
                content = self._call(messages)
                return self._parse_action(content, tools)
            except BrainError as second_error:
                raise BrainError(
                    f"LLM could not produce a valid action after a retry: "
                    f"{second_error}") from second_error


def re_sub_fences(text: str) -> str:
    """Strip a surrounding ``` or ```json fence from model output."""
    lines = text.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()
