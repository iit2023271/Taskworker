"""Tool registry: schemas for the brains + dispatch to implementations.

Every tool is described by a JSON-ish schema (name, description, args) so
the LLM brain can be prompted with the same tool list the rule brain uses.
"""

from __future__ import annotations

from .base import Tool, make_obs
from .browser import get_browser
from .files import ListDirTool, ReadFileTool
from .http_tool import HttpGetTool, HttpPostTool


class _BrowserNavigateTool(Tool):
    name = "browser_navigate"
    description = ("Open a URL in the browser. Returns the page text "
                   "(headings, links, forms) and a screenshot path. "
                   "PDF links on the page are downloaded and reported.")
    args_schema = {"type": "object",
                   "properties": {"url": {"type": "string"}},
                   "required": ["url"]}

    def run(self, args, ctx):
        return get_browser(ctx).navigate(str(args.get("url", "")))


class _BrowserClickTool(Tool):
    name = "browser_click"
    description = "Click a link or button by its visible text."
    args_schema = {"type": "object",
                   "properties": {"text": {"type": "string"}},
                   "required": ["text"]}

    def run(self, args, ctx):
        return get_browser(ctx).click(str(args.get("text", "")))


class _BrowserTypeTool(Tool):
    name = "browser_type"
    description = ("Fill a form field found by its label text. "
                   "Does not submit the form.")
    args_schema = {"type": "object",
                   "properties": {"label": {"type": "string"},
                                  "text": {"type": "string"}},
                   "required": ["label", "text"]}

    def run(self, args, ctx):
        return get_browser(ctx).type(str(args.get("label", "")),
                                     str(args.get("text", "")))


class _BrowserSubmitTool(Tool):
    name = "browser_submit"
    description = "Submit the current form (click the submit button)."
    args_schema = {"type": "object", "properties": {}, "required": []}

    def run(self, args, ctx):
        return get_browser(ctx).submit()


class _BrowserReadTool(Tool):
    name = "browser_read"
    description = "Re-read the current page as text."
    args_schema = {"type": "object", "properties": {}, "required": []}

    def run(self, args, ctx):
        return get_browser(ctx).read()


class _FinishTool(Tool):
    name = "finish"
    description = ("Declare the goal done. The executor then verifies the "
                   "outcome against the internal system before reporting "
                   "success. Only call this after you believe every part "
                   "of the goal is complete.")
    args_schema = {"type": "object",
                   "properties": {"summary": {"type": "string"}},
                   "required": ["summary"]}

    def run(self, args, ctx):
        summary = str(args.get("summary", ""))
        return make_obs(True, f"Finished: {summary}",
                        data={"finished": True, "summary": summary})


class _AskUserTool(Tool):
    name = "ask_user"
    description = ("Ask the user a question when you cannot safely proceed "
                   "(missing information, ambiguous choice, or a blocked "
                   "step). The user's answer comes back as the observation.")
    args_schema = {"type": "object",
                   "properties": {"question": {"type": "string"}},
                   "required": ["question"]}

    def run(self, args, ctx):
        question = str(args.get("question", ""))
        answer = ctx.input_fn(f"Agent asks: {question}\nYour answer: ")
        return make_obs(True, f"User answered: {answer}",
                        data={"answer": answer})


TOOLS: list[Tool] = [
    _BrowserNavigateTool(),
    _BrowserClickTool(),
    _BrowserTypeTool(),
    _BrowserSubmitTool(),
    _BrowserReadTool(),
    ReadFileTool(),
    ListDirTool(),
    HttpGetTool(),
    HttpPostTool(),
    _FinishTool(),
    _AskUserTool(),
]

_BY_NAME = {t.name: t for t in TOOLS}


def get_schemas() -> list[dict]:
    """Tool schemas, as the brains see them."""
    return [t.schema() for t in TOOLS]


def tool_names() -> list[str]:
    return [t.name for t in TOOLS]


def run_tool(name: str, args: dict, ctx) -> dict:
    """Dispatch one tool call. Unknown tools fail as an observation, never
    as an exception, so the brain can recover."""
    tool = _BY_NAME.get(name)
    if tool is None:
        return make_obs(False, f"unknown tool: {name!r}. "
                               f"Available tools: {', '.join(tool_names())}")
    if not isinstance(args, dict):
        return make_obs(False, f"args for {name} must be an object, got {args!r}")
    try:
        return tool.run(args, ctx)
    except Exception as e:  # noqa: BLE001 - tool errors are observations
        return make_obs(False, f"tool {name} raised {type(e).__name__}: {e}")
