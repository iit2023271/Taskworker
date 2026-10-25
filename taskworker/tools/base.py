"""Tool plumbing: the Observation shape, the context tools receive, and
small helpers shared by every tool.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

MAX_TEXT = 4000


def truncate(text: str, limit: int = MAX_TEXT) -> str:
    if len(text) > limit:
        return text[:limit] + f"\n... [truncated, {len(text) - limit} more chars]"
    return text


def make_obs(ok: bool, text: str, screenshot: str | None = None,
             data: dict | None = None) -> dict:
    """Build an Observation dict in the SPEC shape."""
    return {
        "ok": bool(ok),
        "text": truncate(str(text)),
        "screenshot": screenshot,
        "data": data or {},
    }


@dataclass
class ToolContext:
    """Everything a tool needs. Created once per run by the executor."""
    run_dir: Path
    memory: object = None          # RunMemory
    mock_url: str = "http://127.0.0.1:5000"
    input_fn: object = None        # callable(prompt) -> str, for ask_user
    browser: object = None         # lazily created browser backend
    backend: str = "unknown"       # "playwright" or "http"

    def __post_init__(self) -> None:
        self.run_dir = Path(self.run_dir)
        (self.run_dir / "downloads").mkdir(parents=True, exist_ok=True)
        (self.run_dir / "screenshots").mkdir(parents=True, exist_ok=True)
        if self.input_fn is None:
            self.input_fn = input

    @property
    def downloads_dir(self) -> Path:
        return self.run_dir / "downloads"

    @property
    def screenshots_dir(self) -> Path:
        return self.run_dir / "screenshots"


class Tool:
    """A single tool: name, description, JSON args schema, run()."""

    name: str = ""
    description: str = ""
    # JSON-schema-ish: {"type": "object", "properties": {...}, "required": [...]}
    args_schema: dict = {"type": "object", "properties": {}}

    def run(self, args: dict, ctx: ToolContext) -> dict:
        raise NotImplementedError

    def schema(self) -> dict:
        return {"name": self.name, "description": self.description,
                "args": self.args_schema}
