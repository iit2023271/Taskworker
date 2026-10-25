"""HTTP tools: http_get and http_post (JSON, with an optional form body).

http_post accepts either {"json": {...}} for a JSON body or
{"form": {...}} for an application/x-www-form-urlencoded body — the form
variant is the fallback route for posting the internal system's HTML form
when the browser path fails.
"""

from __future__ import annotations

import json

import requests

from .base import Tool, make_obs

TIMEOUT = 20


class HttpGetTool(Tool):
    name = "http_get"
    description = ("GET a URL. Returns the HTTP status and body text "
                   "(JSON bodies are pretty-printed).")
    args_schema = {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    }

    def run(self, args: dict, ctx) -> dict:
        url = str(args.get("url", ""))
        try:
            resp = requests.get(url, timeout=TIMEOUT)
        except Exception as e:  # noqa: BLE001
            return make_obs(False, f"GET {url} failed: {e}")
        return _response_obs(resp, f"GET {url}")


class HttpPostTool(Tool):
    name = "http_post"
    description = ("POST to a URL with a JSON body (\"json\") or a form body "
                   "(\"form\", application/x-www-form-urlencoded). "
                   "Returns the HTTP status and body text.")
    args_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "json": {"type": "object",
                     "description": "JSON body to send."},
            "form": {"type": "object",
                     "description": "Form fields to send (url-encoded)."},
        },
        "required": ["url"],
    }

    def run(self, args: dict, ctx) -> dict:
        url = str(args.get("url", ""))
        try:
            if args.get("form") is not None:
                resp = requests.post(url, data=args["form"], timeout=TIMEOUT)
            else:
                resp = requests.post(url, json=args.get("json", {}),
                                     timeout=TIMEOUT)
        except Exception as e:  # noqa: BLE001
            return make_obs(False, f"POST {url} failed: {e}")
        return _response_obs(resp, f"POST {url}")


def _response_obs(resp: requests.Response, label: str) -> dict:
    data: dict = {"status": resp.status_code, "url": resp.url}
    text = resp.text or ""
    content_type = resp.headers.get("Content-Type", "")
    if "json" in content_type or text.strip().startswith(("{", "[")):
        try:
            parsed = resp.json()
            data["json"] = parsed
            text = json.dumps(parsed, indent=2)
        except ValueError:
            pass
    ok = 200 <= resp.status_code < 400
    return make_obs(ok, f"{label} -> HTTP {resp.status_code}\n{text}",
                    data=data)
