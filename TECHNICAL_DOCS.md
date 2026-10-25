# TaskWorker — Technical Documentation

Companion to `README.md` (plain-language guide) and `ARCHITECTURE.md`
(short architecture write-up). This document is the full technical
reference: every component, the exact loop, the failure policy, the
requirement map, and interview preparation.

**Contents**

- [1. System overview](#1-system-overview)
- [2. Requirement traceability](#2-requirement-traceability)
- [3. Component reference](#3-component-reference)
- [4. The ReAct loop, in detail](#4-the-react-loop-in-detail)
- [5. Brains](#5-brains)
- [6. Tools](#6-tools)
- [7. Memory](#7-memory)
- [8. Approval gate](#8-approval-gate)
- [9. Verification](#9-verification)
- [10. Reporting](#10-reporting)
- [11. Mock company application](#11-mock-company-application)
- [12. Error handling and resilience](#12-error-handling-and-resilience)
- [13. Testing](#13-testing)
- [14. Security and safety analysis](#14-security-and-safety-analysis)
- [15. Performance](#15-performance)
- [16. Design decisions and alternatives considered](#16-design-decisions-and-alternatives-considered)
- [17. Limitations and failure modes](#17-limitations-and-failure-modes)
- [18. Future work](#18-future-work)
- [Appendix A. Full demo transcript](#appendix-a-full-demo-transcript)
- [Appendix B. Interview preparation](#appendix-b-interview-preparation)
- [Appendix C. File inventory](#appendix-c-file-inventory)

---

## 1. System overview

TaskWorker is a single-process Python application (3.10+, ~3,100 lines
including tests) with two halves:

- **The agent** (`taskworker/`): a ReAct loop executor, two interchangeable
  brains, a tool registry, memory, an approval gate, a verifier, and a
  reporter, driven from a CLI.
- **The mock company** (`mock_company/`): a Flask application that plays
  the role of the target environment — inbox, invoice PDFs, internal
  system — so the agent can be demonstrated and tested with no real
  credentials and no network access.

```
                         ┌─────────────────────────────┐
                         │  CLI (taskworker/cli.py)    │
                         │  mock | seed | run          │
                         └──────────────┬──────────────┘
                                        │
                         ┌──────────────▼──────────────┐
                         │  Agent (taskworker/agent.py)│
                         │  ReAct loop, max 30 steps   │
                         └──────┬───────────────┬──────┘
                                │               │
              ┌─────────────────▼───┐   ┌───────▼──────────┐
              │  Brain              │   │  Tools            │
              │  llm_brain.py  OR   │   │  registry.py      │
              │  rule_brain.py      │   │  browser / files /│
              │  decide(state)      │   │  http / finish /  │
              │  -> Action          │   │  ask_user         │
              └─────────┬───────────┘   └───────┬───────────┘
                        │                       │
              ┌─────────▼───────────┐   ┌───────▼───────────┐
              │  Memory             │   │  Mock company     │
              │  facts + steps      │   │  Flask on :5000   │
              │  transcript.json    │   │  inbox / invoices │
              └─────────┬───────────┘   │  / internal sys.  │
                        │               └───────┬───────────┘
              ┌─────────▼───────────┐           │
              │  Approval + Verify  │ ◀─────────┘
              │  approval.py        │  verifier re-reads
              │  verify.py          │  /system/api/records
              └─────────┬───────────┘
                        │
              ┌─────────▼───────────┐
              │  Report (report.py) │
              │  summary.md +       │
              │  transcript.json +  │
              │  screenshots/       │
              └─────────────────────┘
```

**Key invariants**

1. The brain never touches tools, the network, or the filesystem. It only
   returns one `Action` dict per turn. All side effects go through the
   executor and the tool registry.
2. Facts are only ever mined from observations, never asserted by the
   brain. The verifier therefore checks data the agent actually observed.
3. Success is a property of the verifier, not of the brain. The brain
   proposes `finish`; the executor verifies; only a passing verification
   reports SUCCESS.
4. Every step is persisted to `transcript.json` immediately after it
   happens, so a killed run still leaves a complete partial record.
5. Tool failures are observations (`ok: False`), never exceptions escaping
   into the loop. Unknown tools fail the same way.

---

## 2. Requirement traceability

The internship problem statement, mapped requirement by requirement.

| # | Requirement (from the statement) | Where it is met | Evidence |
|---|---|---|---|
| R1 | Takes a natural-language task | CLI `run "TASK"`; `Agent(goal)` | `taskworker/cli.py`, `taskworker/agent.py` |
| R2 | Understands the goal, breaks it into actions | Brain subgoal derivation (rule) / LLM planning (LLM brain) | `taskworker/brain/rule_brain.py` stages; `taskworker/brain/llm_brain.py` system prompt |
| R3 | Uses the browser | Real Chromium via Playwright, with HTTP fallback | `taskworker/tools/browser.py`; demo screenshots |
| R4 | Uses files | `read_file` (PDF via pypdf), `list_dir` | `taskworker/tools/files.py`; demo step 3 reads the invoice PDF |
| R5 | Uses APIs | `http_get` / `http_post` (JSON + form) | `taskworker/tools/http_tool.py`; demo step 10 reads `/system/api/records` |
| R6 | Uses a simulated company application | Mock company app (Flask) | `mock_company/app.py` |
| R7 | Observes results and decides next steps | ReAct loop: observation → state → next `decide()` | `taskworker/agent.py` loop; transcript shows observation-driven choices |
| R8 | Remembers discovered information | `RunMemory` facts with sources + step history | `taskworker/memory.py` |
| R9 | Detects failures | Tool observations carry `ok: False`; executor tracks `_consecutive_failures` | `taskworker/tools/base.py`, `taskworker/agent.py` |
| R10 | Retries or tries alternatives | Retry once, then alternative route (browser ↔ API), then ask user | `taskworker/brain/rule_brain.py` `_retry` / `_alternative`; `agent.py` |
| R11 | Verifies the outcome | Independent verifier re-reads the system and compares facts | `taskworker/verify.py` |
| R12 | Asks for clarification / approval when it cannot safely proceed | `ask_user` tool; approval gate for writes | `taskworker/tools/registry.py`, `taskworker/approval.py` |
| R13 | Returns a concise summary with evidence | `summary.md` + `transcript.json` + screenshots + downloads per run | `taskworker/report.py`; `runs/demo/` |
| R14 | Narrow but genuinely working beats broad and mocked | One demo task, fully working end-to-end, no stubs | Demo run: 11 steps, SUCCESS, verification passed |
| R15 | No real company credentials; sandbox/mock environments | Everything runs on `127.0.0.1`; no external service is required for the offline demo | `mock_company/`; `.env.example` contains no real values |
| S1 | GitHub repo (or equivalent link) | This repository (one commit; push instructions in README delivery) | git log |
| S2 | README with setup/run instructions | `README.md` sections 6–7 | — |
| S3 | Short architecture explanation | `ARCHITECTURE.md`; `README.md` section 5 | — |
| S4 | Important technical/design decisions | `README.md` section "Design decisions"; this doc, section 16 | — |
| S5 | Demo video or accessible live demo | `demo/taskworker-demo.mp4` (85 s, narrated, real screenshots) | — |
| S6 | Known limitations | `README.md` section 15; this doc, section 17 | — |
| S7 | What to build next | `README.md` section 16; this doc, section 18 | — |
| S8 | Assumptions | `README.md` section 17 | — |
| S9 | Models/APIs/frameworks/external services | `README.md` "Models, APIs, frameworks"; this doc, section 3 | — |

---

## 3. Component reference

### 3.1 `taskworker/agent.py` — the executor

`class Agent(goal, brain=None, mock_url, max_steps=30, auto_approve=False,
run_dir=None, input_fn=None, brain_choice="auto")`

- `_select_brain(choice)`: `"llm"` → `LLMBrain()`; `"rule"` →
  `RuleBrain(mock_url)`; `"auto"` → `LLMBrain()` if
  `LLMBrain.available()` (i.e. `OPENAI_API_KEY` is set), else
  `RuleBrain`.
- `_state()`: builds the brain's input — `goal`, `facts`
  (`memory.plain_facts()`), `steps` (full history), `last_observation`,
  `tools` (schemas from the registry), `attempts`
  (`_consecutive_failures`).
- Main loop (`run()`): up to `max_steps` turns of
  brain → approval gate → tool dispatch → fact mining → persist.
  `finish` triggers `_verify()`; two failed verifications end the run as
  incomplete. A `BrainError` from the brain triggers `_fallback_brain()`
  (LLM → rule) once, and the fallback is recorded in the result.
- `_verify()`: verifies `must_verify_facts()` (vendor, invoice_no,
  amount, due_date) via `verify_via_api` against
  `{mock_url}/system/api/records`, using the `http_get` tool so the check
  goes through the same path as any other tool call.
- Result dict: `success`, `summary`, `steps`, `brain` (name of the brain
  that finished the run), `fell_back_to_rule`, `verification`.

### 3.2 `taskworker/brain/base.py` — the brain interface

```python
class Brain(ABC):
    def decide(self, state: dict) -> dict: ...   # -> Action dict

class BrainError(Exception): ...  # the fallback signal
```

An `Action` is a plain dict:
`{"tool": "<name>", "args": {...}, "reasoning": "<one line>"}`.
Both brains implement this interface and nothing else; the executor never
calls any other brain method. This is what makes the two brains
interchangeable.

### 3.3 `taskworker/brain/llm_brain.py` — the LLM brain

- Configuration: `OPENAI_API_KEY` (required), `OPENAI_BASE_URL`
  (default `https://api.openai.com/v1`), `OPENAI_MODEL` (default
  `gpt-4o-mini`), `timeout=60` s, `temperature=0` (deterministic).
- `_messages(state)`: system prompt (tool schemas + rules) + a user
  message with `GOAL`, `FACTS SO FAR`, the last 12 steps
  (`MAX_HISTORY_STEPS = 12`, each observation truncated to 1,500 chars),
  and `LAST OBSERVATION`, ending with the tool list and the instruction
  to reply with only the JSON action.
- `_call(messages)`: `POST {base_url}/chat/completions` with
  `Authorization: Bearer <key>`, `{"model", "messages", "temperature": 0}`.
  Non-200 responses and malformed response shapes raise `BrainError`.
- `_parse_action(content, tools)`: strips ```` ``` ```` fences, parses
  JSON, validates that the result is a dict with a known `tool` and a dict
  `args`. Unknown tools and non-dict args raise `BrainError`.
- `decide(state)`: one call + parse; on `BrainError`, one correction
  round (the error is appended as a user message and the model is asked
  again for only a JSON action); a second failure raises `BrainError`,
  which the executor turns into a fallback to the rule brain.
- `available()`: classmethod, true when `OPENAI_API_KEY` is set — used by
  `--brain auto`.

### 3.4 `taskworker/brain/rule_brain.py` — the offline planner

A goal-directed planner, not a fixed script. It derives a subgoal
checklist from the goal text and picks the next action from memory facts
plus the last observation:

| Stage | Condition | Action |
|---|---|---|
| 1. Find the inbox | no `inbox_seen` and no `emails` | `browser_navigate {mock}/inbox` |
| 2. Pick the email | `emails` present, no `email_id` | latest vendor email (see below) → `browser_navigate` to it |
| 3. Read the invoice | `email_id` set, fields incomplete — or a PDF is available and unread | `read_file` on the downloaded PDF (email body is the fallback) |
| 4. Enter the record | all of `invoice_no`, `amount`, `due_date` known, not `submitted` | `browser_navigate /system`, then `browser_type` per field, then `browser_submit` |
| 5. Check + finish | `submitted` | `http_get /system/api/records`, then `finish` when the record is listed |

- `parse_vendor_from_goal(goal)`: extracts the vendor from
  `"... invoice from <Vendor> ..."` (regex, stops at a comma or at
  "extract"/"and enter").
- `pick_latest_vendor_email(emails, vendor)`: matches any significant
  word of the vendor name (stop-words like Ltd/Inc/Corp dropped, because
  the inbox shows sender email addresses, not display names), prefers
  invoice-like emails, then takes the latest date.
- `extract_invoice_fields(text)`: regex extraction — invoice number
  (labelled `Invoice number:` first, then bare `INV-…` tokens, skipping
  matches that are part of a file path, e.g. the downloaded file name in
  an observation header); amount (prefers `$` figures on total/amount-due
  lines, else the largest `$` figure); due date (prefers a date on a
  "due" line, in ISO / "19 November 2026" / "Nov 19, 2026" forms).
- `extract_observation_facts(obs, goal, last_action)`: shared with the
  executor — turns one observation into durable facts. Invoice fields are
  mined only from invoice sources (an email page or a file read), never
  from list pages, so the inbox table cannot produce false positives.
- Failure policy: `_retry` (same action once) then `_alternative`
  (browser ↔ HTTP API per subgoal; `read_file` failure falls back to the
  email-body facts if present, else `ask_user`; double `http_post`
  failure → `ask_user`). A failed `ask_user` ends the run instead of
  looping.

### 3.5 `taskworker/tools/` — the tool layer

`tools/base.py`: the `Observation` shape
`{"ok": bool, "text": str (truncated ~4,000 chars), "screenshot": path|None,
"data": dict}` and `ToolContext` (run dir, memory, browser, mock URL,
input function). `tools/registry.py`: the 11 tools, their JSON schemas,
and `run_tool(name, args, ctx)` — unknown tools and non-dict args fail as
observations; tool exceptions are caught and returned as failed
observations, so the brain can recover.

| Tool | Args | Behaviour |
|---|---|---|
| `browser_navigate` | `url` | Opens the URL; returns page text (headings, links, forms) + screenshot (Playwright only). PDF links on the page are downloaded to `runs/<id>/downloads/` and reported in `data.pdf` / `data.pdfs`. |
| `browser_click` | `text` | Clicks a link/button by visible text. |
| `browser_type` | `label`, `text` | Fills a form field found by its label text. Does not submit. |
| `browser_submit` | — | Submits the current form (clicks the submit button). Write action. |
| `browser_read` | — | Re-reads the current page as text. |
| `read_file` | `path` | PDF via pypdf (text extraction), `.txt`/`.csv`/`.json`/`.md` as text. |
| `list_dir` | `path` | Lists a directory. |
| `http_get` | `url` | GET; returns status + body (JSON pretty-printed). |
| `http_post` | `url`, `json`?, `form`? | POST with a JSON body or form-encoded data. Write action. |
| `finish` | `summary` | Declares the goal done; the executor then verifies. |
| `ask_user` | `question` | Asks the user; the answer becomes the observation. |

### 3.6 `taskworker/tools/browser.py` — the browser tool

Two backends behind one interface, selected by `get_browser(ctx)`:

- **Playwright backend** (used when `playwright` is importable and a
  Chromium binary exists): real Chromium, `page.goto`, clicks and fills
  by text/label selectors, screenshots to `runs/<id>/screenshots/`
  (`shot_01.png`, …). Falls back to the full Chromium executable when
  only that build is installed (the headless-shell build is not assumed).
- **HttpBrowser fallback** (stdlib only: `requests` + an HTML parser):
  fetches pages, parses links and forms, submits forms, and downloads
  linked PDFs. Same methods, same observation shape, no screenshots.
  The agent's behaviour does not depend on which backend is present.

Both backends report downloaded PDFs the same way (`data.pdf` = local
path), which is what lets the rule brain's stage 3 work identically on
either backend.

### 3.7 `taskworker/memory.py` — memory

`RunMemory`: `facts` is a dict `key -> {"value", "source", "must_verify"}`.
`set_fact` never overwrites a fact with an empty value and never
downgrades `must_verify` once set. `plain_facts()` returns
`{key: value}` for the brain; `must_verify_facts()` returns the subset
the verifier must check. `steps` is the ordered list of
`{"action", "observation"}` pairs. `save(path)` writes
`{"facts", "steps"}` as JSON; the executor calls it after every step.

### 3.8 `taskworker/approval.py` — the approval gate

`WRITE_TOOLS = {"browser_submit", "http_post"}`. `Approver(auto_approve,
input_fn)`: in auto mode every write is allowed and logged as
`auto-approved`; in supervised mode it prompts
`Approve <tool> <args>? [y/n]` on the terminal and logs `approved` or
`denied`. A denial is returned to the loop as a failed observation
(`"denied by user"`), not an exception.

### 3.9 `taskworker/verify.py` — the verifier

- `parse_amount(value)`: `"$4,850.00"` / `"4850.00"` / `4850.0` → `4850.0`;
  `None` when unparseable.
- `verify_records(records, facts)`: pure function. Requires `vendor` and
  `invoice_no`; finds records with the same invoice number and a matching
  vendor (case-insensitive, substring either way); compares amount
  numerically and due date as a string when present. Returns
  `{"passed": bool, "detail": str}`.
- `verify_via_api(records_url, facts, http_get)`: fetches the records
  through the `http_get` tool and calls `verify_records`.

### 3.10 `taskworker/report.py` — reporting

`write_report(run_dir, goal, result, memory, approval_log)` writes
`transcript.json` (via `memory.save`) and `summary.md`: goal, outcome,
summary, step count, brain name, fallback flag, verification result,
evidence lists (screenshots, downloads), transcript pointer, approvals.

### 3.11 `taskworker/cli.py` — the CLI

`argparse` with subcommands `mock` (`--port`), `seed`, `run`
(`task`, `--brain {auto,llm,rule}`, `--auto-approve`,
`--mock-url`, `--max-steps`, `--run-dir`). `mock` runs the Flask app
(module-level `app` object from `mock_company/app.py`).

---

## 4. The ReAct loop, in detail

Pseudocode of `Agent.run()`:

```
state = initial (goal, no facts, no steps)
for step in 1..max_steps:
    action = brain.decide(state)                 # one JSON action
    if action.tool == "finish":
        verification = verify(facts)             # independent re-read
        if verification.passed: return SUCCESS
        if verify_failures >= 2: return NOT COMPLETED
        record failed observation; continue      # brain replans
    if action is a write action and not approver.approve(action):
        record observation "denied by user"; continue
    observation = run_tool(action.tool, action.args, ctx)
    memory.record_step(action, observation)
    new_facts = extract_observation_facts(observation, goal, action)
    memory.set_fact(...) for each new fact
    memory.save(transcript.json)
    state = rebuild from memory
    if brain raised BrainError: brain = RuleBrain(); fell_back = True
return NOT COMPLETED (max steps reached)
```

The state handed to the brain each turn is:

```python
{
  "goal": str,
  "facts": {key: value},              # plain values, with sources in memory
  "steps": [{"action": {...}, "observation": {...}}, ...],
  "last_observation": {...} | None,
  "tools": [schemas],                 # from the registry
  "attempts": int,                    # consecutive failures so far
}
```

### The real demo run, step by step

The full annotated trace is in Appendix A. In short: 11 steps, all
`ok=True`, rule brain, no retries, no fallback, verification passed on
the first attempt. The interesting steps, from an engineering point of
view:

- **Step 2** is the selection decision: from the inbox observation the
  brain picks `/inbox/1` (latest Acme invoice email) over `/inbox/2`
  (newer, wrong vendor) and `/inbox/5` (older, same vendor).
- **Step 3** is the source-of-truth decision: the email body already
  contained the figures, but the brain reads the downloaded PDF anyway,
  and the PDF's values overwrite the email-body facts (facts are keyed,
  so a later observation replaces an earlier one for the same key).
- **Step 10** is the pre-verification check: the brain itself looks at the
  records API before calling `finish`; the executor's verifier then
  performs the same check independently. The two checks are redundant by
  design — the brain's check is for deciding, the verifier's check is for
  certifying.

---

## 5. Brains

### 5.1 Design: one interface, two implementations

Both brains satisfy `Brain.decide(state) -> Action`. The executor,
tools, memory and verifier are identical for both, so the choice of brain
is a configuration (`--brain`), not a fork in the code. The report records
which brain finished the run and whether a fallback happened, so the
choice is always auditable.

### 5.2 LLM brain — prompt design

The system prompt (verbatim, from `llm_brain.py`):

```
You are TaskWorker, an autonomous AI worker. You complete the
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
```

Design notes:

- **Temperature 0** for determinism: the same state should produce the
  same action, which makes the LLM brain testable and the demo repeatable.
- **History is bounded**: only the last 12 steps, each observation
  truncated to 1,500 characters. This keeps the prompt small and the cost
  low, at the price of the model forgetting very early steps on long runs
  (mitigated by the facts list, which is always complete).
- **Facts are always included in full**, so the model never has to
  re-derive the invoice figures from history.
- **No function calling / JSON mode is used** (deliberate, for
  provider-independence: the same code works with OpenAI, OpenRouter,
  Ollama, and Gemini's OpenAI-compatible endpoint). The trade-off is that
  free-text JSON parsing can fail; the correction retry + executor
  fallback exist for exactly that case. Structured output is listed as
  future work (section 18).
- **Validation is strict**: unknown tool names, non-dict args, and
  non-JSON replies are all `BrainError`, never silently accepted.

### 5.3 Rule brain — why it is a planner, not a script

A script would be: "open inbox, open email 1, read the PDF, fill these
four values, submit". The rule brain does not do that:

- The vendor is **parsed from the goal sentence**, not hardcoded. The
  same code handles the Globex task in README section 7 with no changes.
- The email is **chosen from the observed inbox** (latest date among
  vendor-matching, invoice-like emails), not assumed to be id 1.
- Every stage's trigger is a **state condition** (which facts exist, what
  the last observation contained), so if the browser fails, the same
  stage can be reached through the HTTP API instead.
- Field values come from **observations** (PDF text), never from literals
  in the code. The only literals are the mock URL and the subgoal shapes.

Its genuine limits: it cannot invent a plan for a task shape it has no
subgoals for, and its extraction is regex-based (it will misread a
differently formatted invoice). That is why the LLM brain exists.

### 5.4 Brain selection and fallback, precisely

- `--brain rule` → `RuleBrain` always.
- `--brain llm` → `LLMBrain` always; if the key is missing, the first
  `decide()` raises `BrainError`, the executor falls back to `RuleBrain`,
  and the run continues (the report records `fell_back_to_rule: True`).
- `--brain auto` → `LLMBrain` if `OPENAI_API_KEY` is set at startup,
  else `RuleBrain`. A mid-run LLM failure (API error, bad JSON after the
  correction retry, timeout) also falls back to `RuleBrain` for the rest
  of the run. There is no fallback *from* the rule brain — if it fails,
  the run asks the user or ends.

---

## 6. Tools

### 6.1 The registry as a single source of truth

`registry.py` is the only place tools are listed. The LLM brain's system
prompt is built from the same schemas the executor dispatches on, so a
tool added to the registry is immediately available to both brains with
no other code change. Tool schemas are JSON-schema-like dicts
(`{"type": "object", "properties": {...}, "required": [...]}`).

### 6.2 Browser tool internals

**Playwright backend.** One `sync_playwright` session per run; a single
page is reused across navigations. `navigate` does `page.goto(url)` and
then extracts the page as text (headings, body text, links with hrefs,
forms with labelled fields) and takes a screenshot
(`screenshots/shot_NN.png`). PDF links found on the page are downloaded
with `requests` into `runs/<id>/downloads/` and reported in the
observation's `data` (`pdf` = first PDF, `pdfs` = list). `click` matches
a link/button by visible text (case-insensitive substring); `type`
matches a form field by label/name/id/placeholder (case-insensitive) and
uses `page.fill`; `submit` clicks the form's submit button.

**HttpBrowser fallback.** `requests.get` + a stdlib `HTMLParser`
subclass that collects links and form fields. `navigate` returns the same
text shape (page text, links, forms) minus screenshots. `click` follows
the matched link; `type` stores values in the current form's field map;
`submit` posts the form (GET or POST per the form's method). PDF links
are downloaded the same way and reported identically.

**Why two backends.** Playwright needs a browser binary (~150 MB
download) and is the honest choice for a "browser" claim. The fallback
exists so the project runs on a machine where that download is
impossible (locked-down CI, no disk space). The trade-off: the fallback
cannot run JavaScript, so it cannot drive JS-heavy pages. Both backends
were exercised against a stub server during development and both passed
the end-to-end check.

### 6.3 Observation contract

Every tool returns `{"ok", "text", "screenshot", "data"}`. `text` is
human-readable and truncated to ~4,000 characters so a single observation
cannot flood the LLM's context or the transcript. `data` carries
machine-readable extras (page URL, links, forms, downloaded PDF paths,
HTTP status, JSON bodies). The executor and the fact-miner read `data`;
the brain mostly reads `text`.

---

## 7. Memory

Facts are the agent's durable knowledge. The model is deliberately
minimal:

```python
facts[key] = {"value": ..., "source": "<tool that produced it>",
              "must_verify": bool}
```

- `source` is the tool name that produced the observation the fact was
  mined from (e.g. `read_file` for the invoice figures). It is the audit
  trail for "where did this number come from?".
- `must_verify` is set for `vendor`, `invoice_no`, `amount`, `due_date`
  — the facts the verifier must check. It is never downgraded once set.
- `set_fact` refuses empty values, so a failed extraction cannot erase a
  good fact.
- Later observations overwrite earlier ones for the same key. This is
  what makes the PDF-over-email-body precedence work: the PDF is read
  after the email, so the document's values win.

The step history is a plain list; the brain sees all of it (the LLM brain
sees the last 12 steps, the rule brain sees all of it via the facts and
its own stage checks). There is no long-term memory across runs — that is
listed as future work.

---

## 8. Approval gate

Policy, in full:

- **Write set:** `browser_submit` and `http_post`. Everything else
  (navigation, reads, GETs) is a read and runs freely. Rationale: reads
  cannot change the world; writes can.
- **Supervised mode (default):** before a write tool runs, the executor
  calls `Approver.approve(action)`, which prompts on the terminal:
  `Approve <tool> <args>? [y/n]`. `y`/`yes` approves; anything else
  denies. A denial becomes the observation `{"ok": False, "text":
  "denied by user"}` and the loop continues — the brain can replan, ask
  the user, or finish without the write.
- **Auto mode (`--auto-approve`):** writes proceed; each is logged as
  `auto-approved`.
- **Logging:** every decision (`tool`, `args`, `decision`) is appended to
  `approver.log` and printed in the run's `summary.md` under "Approvals".

What the gate does **not** do: it does not review the *content* of a
write for correctness (a wrong amount would still be approved if the user
says yes — that is what the verifier is for), and it does not sandbox the
browser. It is a human checkpoint on state changes, nothing more.

---

## 9. Verification

`verify_records(records, facts)`:

1. If `vendor` or `invoice_no` is missing from facts → fail with
   "cannot verify".
2. Candidates = records where `invoice_no` matches exactly and the vendor
   matches (case-insensitive, substring either way — so "Acme Supplies
   Ltd" matches "Acme Supplies Ltd", and a partial vendor still matches).
3. No candidates → fail with "no record found … for invoice X".
4. For the first candidate: compare `amount` numerically
   (`parse_amount` strips `$` and commas) and `due_date` as a string.
   A mismatch fails with the expected vs actual values.
5. All comparisons pass → `{"passed": True, "detail": "record for invoice
   X found in the internal system: amount …, due …"}`.

`verify_via_api` fetches the records through the `http_get` tool, so the
verification read is itself an observed tool call in the transcript.

Executor policy around verification: on `finish`, verify once; on failure,
record a failed observation and let the brain replan (it typically
re-enters the record — the rule brain has an explicit re-entry path that
fires once); on the second failure, end the run as NOT COMPLETED. The run
never reports SUCCESS on a failed verification, and never reports SUCCESS
without attempting verification.

---

## 10. Reporting

Per run, in `runs/<run-id>/`:

- `transcript.json`: `{"facts": {key: {value, source, must_verify}}, "steps":
  [{"action": {"tool", "args", "reasoning"}, "observation": {"ok", "text",
  "screenshot", "data"}}]}`. Written after every step.
- `summary.md`: goal, outcome, summary, step count, brain name, fallback
  flag, verification result + detail, evidence lists (screenshots,
  downloads), transcript pointer, approvals list.
- `screenshots/shot_NN.png`: one per browser navigation (Playwright
  backend only).
- `downloads/`: files the agent downloaded during the run.

The report is the deliverable an evaluator actually reads: the outcome
line, the verification block, and the evidence list answer "did it work,
and how do I know?" without opening the transcript.

---

## 11. Mock company application

Flask app (`mock_company/app.py`), module-level `app`, run with
`python -m taskworker mock [--port PORT]` (default 5000).

| Route | Method | Purpose |
|---|---|---|
| `/` | GET | Dashboard with links to inbox and system |
| `/inbox` | GET | HTML table: date, from, subject; rows link to `/inbox/<id>` |
| `/inbox/<id>` | GET | Email view: from, date, subject, body, attachment link |
| `/invoices/<file>.pdf` | GET | Serves the invoice PDF |
| `/system` | GET | Internal system: table of entered records + entry form (fields `vendor`, `invoice_no`, `amount`, `due_date`) |
| `/system/add` | POST | Validates (all four fields present, amount numeric after stripping `$`/commas) and appends a record; redirects to `/system` |
| `/system/api/records` | GET | JSON list of records (used by the verifier) |
| `/api/inbox` | GET | JSON list of emails (fallback route for the agent) |
| `/system/api/reset` | POST | Clears all records (demo repeatability) |

**Seed data** (`mock_company/seed.py` regenerates `data/seed.json` and the
PDFs with fpdf2; re-running it never wipes existing records):

| Email | Date | From | Subject | Attachment |
|---|---|---|---|---|
| 1 | 2026-10-20 | billing@acmesupplies.com (Acme) | Invoice INV-2026-1042 – October services | inv-2026-1042.pdf |
| 2 | 2026-10-22 | accounts@globexcorp.com (Globex) | Invoice INV-G-881 – Cloud hosting October | inv-g-881.pdf |
| 3 | 2026-10-15 | support@acmesupplies.com (Acme) | Reminder: updated payment terms | — |
| 4 | 2026-10-08 | hello@globexcorp.com (Globex) | Welcome to the Globex vendor portal | — |
| 5 | 2026-09-18 | billing@acmesupplies.com (Acme) | Invoice INV-2026-1031 – September services | inv-2026-1031.pdf |

| Invoice | Vendor | Date | Amount | Due |
|---|---|---|---|---|
| INV-2026-1042 | Acme Supplies Ltd | 2026-10-20 | $4,850.00 | 2026-11-19 |
| INV-2026-1031 | Acme Supplies Ltd | 2026-09-18 | $3,920.50 | 2026-10-18 |
| INV-G-881 | Globex Corp | 2026-10-22 | $1,150.00 | 2026-11-21 |

**Persistence:** records are stored in `mock_company/data/records.json`
(a JSON list; amount stored as a float). The app is single-process with no
database — adequate for a demo, and listed as a limitation.

**Design of the traps.** The seed data is deliberately adversarial in
exactly two ways (newer email from the wrong vendor; older invoice from
the right vendor) so that a naive "pick the newest email" or "pick any
Acme email" strategy fails verification. The reminder and welcome emails
are noise that a keyword-only search would also have to skip.

---

## 12. Error handling and resilience

| Failure | What happens |
|---|---|
| Tool raises an exception | Caught in `run_tool`; becomes a failed observation (`ok: False` with the exception type and message). The brain sees it and can retry or reroute. |
| Tool returns `ok: False` | Executor increments `_consecutive_failures`; the rule brain retries the same action once, then tries the alternative route; the LLM brain is told to retry once then reroute (system prompt rule). |
| Browser navigation fails | Rule brain: retry once, then `http_get` the same URL (inbox API / email JSON). |
| PDF cannot be read | Rule brain: if the email body already yielded the figures, proceed to entry; otherwise `ask_user` for the figures. |
| Form submission fails | Rule brain: retry, then `http_post` the form-encoded record to `/system/add` (the API route). |
| Unknown tool (LLM invents one) | `run_tool` returns a failed observation listing the available tools; the LLM's correction retry is triggered by the parse error path. |
| LLM returns invalid JSON | One correction round with the error quoted back; second failure raises `BrainError` → executor falls back to the rule brain. |
| LLM API error / timeout / no key | `BrainError` → fallback to the rule brain; the report records it. |
| Approval denied | Failed observation ("denied by user"); the brain replans. |
| Verification fails | Failed observation; brain replans (rule brain re-enters once); second failure ends the run as NOT COMPLETED. |
| `ask_user` channel fails (no terminal) | Run ends with "could not ask the user" instead of looping. |
| Max steps reached | Run ends as NOT COMPLETED ("stopped after N steps without finishing"). |
| Mock company not running | Browser/HTTP tools fail with connection errors; the agent retries, reroutes, then asks the user. |
| Duplicate run without reset | A second identical record is entered (no deduplication in the mock app). Reset with `POST /system/api/reset`. |

---

## 13. Testing

Run everything with:

```bash
python -m unittest discover -s tests -v
```

23 tests, stdlib `unittest` only (no pytest dependency). Current state:
all 23 pass.

### 13.1 Test inventory

**`tests/test_brain.py` — planner stages, vendor picking, extraction (12 tests)**

- `TestGoalParsing`: vendor parsed from the goal sentence; empty string
  when the goal names no vendor.
- `TestExtraction`: PDF text yields `invoice_no` / `amount` / `due_date`;
  the downloaded-file-name trap (a lower-case `inv-…` in the observation
  header) must not beat the document's own `Invoice number:`; a bare
  `INV-…` token without a label still extracts.
- `TestVendorPick`: the latest Acme email wins over the newer Globex
  email; no match returns `None`.
- `TestRuleBrainStages`: stage 1 opens the inbox; stage 2 opens the
  latest vendor email; stage 3 reads the PDF before entering even when
  the email body already yielded the figures; stage 4 opens the system
  form; stage 5 checks the records API and then finishes.

**`tests/test_verify_approval.py` — verifier + approval gate (10 tests)**

- `TestVerify`: pass on a matching record; fail on wrong amount, wrong
  invoice number, missing record, missing facts; amount parsing
  (`"$4,850.00"` → `4850.0`, float passthrough, unparseable → `None`).
- `TestApproval`: `browser_submit`/`http_post` are writes, `http_get` is
  not; supervised deny blocks and logs `denied`; supervised approve
  allows; auto-approve allows and logs `auto-approved`.

**`tests/test_e2e.py` — end-to-end (1 test)**

- `test_demo_task_completes_and_verifies`: starts the real mock Flask app
  in-process on port 5051 (werkzeug `make_server` in a thread), resets
  the records, runs the full `Agent` with the rule brain and
  auto-approve, and asserts: `success` is true, verification passed,
  exactly one record exists with invoice `INV-2026-1042`, amount `4850.0`,
  due `2026-11-19`, and the transcript contains both a `read_file` step
  (the PDF was read) and a `finish` step.

### 13.2 What is NOT tested

- The LLM brain against a live API (no key was available during
  development). Its parsing, fence-stripping, unknown-tool rejection and
  missing-key error were checked with inline checks during development
  (see the build notes in the repository history), but those checks live
  outside the repo's test suite. Adding a mocked-HTTP test for
  `LLMBrain.decide` is the first testing gap to close.
- The Playwright backend against a real browser in the test suite (the
  e2e test exercises whichever backend is selected; in CI without
  Chromium it exercises the HTTP fallback).
- Concurrent runs (the mock app is single-process; two agents writing at
  once are untested).

### 13.3 Bugs found by testing, and fixed

Two real bugs were found during the author's own verification runs (not
by the builders) and fixed before delivery:

1. **The agent skipped reading the PDF.** The email body already
   contained the figures, so the planner's "fields complete" check passed
   and stage 3 was skipped. Fix: stage 3 now requires the PDF to be read
   whenever one was downloaded, even if the email body already yielded
   the figures (`rule_brain.py`, stage 3 condition).
2. **A lower-case invoice number from the file name.** The `read_file`
   observation header contains the downloaded file path
   (`.../inv-2026-1042.pdf`), and the invoice-number regex matched that
   lower-case token before the document's own `INV-2026-1042`. Fix:
   labelled patterns are tried first, and matches that are part of a file
   path (preceded by `/` or followed by `.pdf`) are skipped
   (`extract_invoice_fields`).

Both fixes have regression tests (`test_stage3_reads_pdf_before_entering`,
`test_file_path_must_not_win`).

---

## 14. Security and safety analysis

- **No credentials in the repo.** `.env.example` contains placeholders
  only; `.env` is gitignored. The LLM key is read from the process
  environment at runtime and never written to disk, memory files, or
  reports. (The transcript contains tool arguments — if a user ever typed
  a key into a task, it would appear there. The CLI does not do this.)
- **Least privilege by construction.** The agent's only capabilities are
  its 11 tools. It cannot execute shell commands, write arbitrary files
  (only `read_file`/`list_dir` exist; there is deliberately no write-file
  tool), or contact hosts other than the mock URL and the LLM endpoint.
- **Local-only demo.** The mock company binds to `127.0.0.1` and the
  agent's default target is localhost. Nothing in the demo leaves the
  machine except (a) the one-time dependency downloads and (b) LLM API
  calls when the LLM brain is used, which send the goal, facts and recent
  observations to the provider.
- **Approval gate.** See section 8. It is a human checkpoint, not a
  sandbox: it does not inspect write contents for correctness.
- **Input handling.** All browser interactions are by visible text/label,
  not by executing page JavaScript. Form values are filled, not
  interpolated into commands. The mock app's `/system/add` validates
  field presence and numeric amounts server-side.
- **No prompt-injection handling.** The LLM brain's prompt includes
  observation text, which comes from pages and files the agent reads. A
  malicious page could in principle contain text instructing the model to
  do something else ("ignore your instructions and…"). The current
  mitigation is that the model can only call the 11 tools, and writes
  still pass the approval gate in supervised mode. Treating untrusted
  page content as data rather than instructions is future work (section
  18) and a known limitation (section 17).

---

## 15. Performance

Observed on the development machine (2-core VM, Python 3.12):

| Run | Brain | Steps | Wall time |
|---|---|---|---|
| Demo run (`runs/demo`) | rule | 11 | ~4 s |
| Verification re-runs | rule | 11 | ~4–7 s |
| Supervised run (one approval) | rule | 11 | ~8 s (includes the human pause) |
| Test suite (23 tests, incl. e2e) | rule | — | ~4–7 s |
| LLM brain | llm | — | Not measured against a live API; expect tens of seconds (one API call per step, ~1–3 s each, plus the correction retry when needed). |

The rule brain is effectively free (regex + HTTP). The LLM brain's cost
is one chat-completions call per step with a bounded prompt (last 12
steps, 1,500 chars each, plus facts and tool schemas) — a few thousand
tokens per step at most. With `gpt-4o-mini` that is a fraction of a cent
per run.

---

## 16. Design decisions and alternatives considered

1. **A mock company instead of the real web.**
   *Chosen:* a local Flask app. *Why:* the task forbids real credentials;
   a local mock gives a genuinely working demo with zero setup and zero
   risk. *Rejected:* scraping a real public site (fragile, and the task
   is about a company workflow, not the public web); a pure simulation
   with no browser (would make the "uses the browser" claim hollow).

2. **Two brains behind one interface.**
   *Chosen:* `Brain.decide(state) -> Action`, implemented twice.
   *Why:* an LLM generalises to unscripted tasks; a planner guarantees
   the demo runs offline. One interface means the executor, tools and
   verifier are written once. *Rejected:* LLM-only (the demo would depend
   on a key and the internet, and could not be shown reliably); planner-
   only (the submission would have no genuine generalisation story).

3. **ReAct loop instead of a fixed workflow.**
   *Chosen:* think → act → observe, one action per turn.
   *Why:* the agent can react to failures and surprises instead of
   assuming the happy path. *Rejected:* a hardcoded 11-step script (would
   be brittle and would not satisfy "detect failures, retry or try
   alternatives"); a full planner with search (overkill for this scope).

4. **Two browser backends.**
   *Chosen:* Playwright when available, HTTP fallback otherwise, same
   observation shape. *Why:* the demo works on any machine, with or
   without a browser binary. *Rejected:* Playwright-only (fails on
   machines where the download is blocked); HTTP-only (weaker claim —
   "uses the browser" would mean "fetches pages").

5. **Verification as a separate component.**
   *Chosen:* `verify.py` re-reads the system independently of the brain.
   *Why:* "done" must be a checkable fact, not the agent's opinion.
   *Rejected:* trusting the brain's `finish` (the standard failure mode
   of agent demos — the agent says done and nobody checks).

6. **Facts mined from observations, not asserted by the brain.**
   *Chosen:* `extract_observation_facts` runs on every observation; facts
   carry their source tool. *Why:* the verifier then checks data the
   agent actually saw, and the transcript shows where each number came
   from. *Rejected:* letting the brain declare facts in its reasoning
   (unverifiable, and the LLM could hallucinate a figure).

7. **The PDF as the source of truth.**
   *Chosen:* the planner reads the attached PDF even when the email body
   already states the figures. *Why:* in real work the email is a summary
   and the document is authoritative; the demo should model the careful
   behaviour. *Cost:* one extra step. This was a deliberate fix during
   verification (section 13.3), not the original behaviour.

8. **Approval gate on writes only.**
   *Chosen:* `browser_submit` and `http_post` need approval; reads run
   freely. *Why:* reads cannot change the world, so asking about them
   would be noise; writes are the only irreversible actions in scope.
   *Rejected:* approving every step (unusable), approving nothing (unsafe
   for a real deployment story).

9. **Free-text JSON parsing instead of function calling.**
   *Chosen:* the LLM replies with a JSON action object; the parser
   tolerates fences and validates strictly. *Why:* provider-independence
   (the same code works with OpenAI, OpenRouter, Ollama, Gemini's
   compatible endpoint). *Cost:* parsing can fail; mitigated by the
   correction retry and the executor fallback. Structured output is
   future work.

10. **stdlib `unittest`, no pytest.**
    *Chosen:* the test suite uses only the standard library.
    *Why:* one fewer dependency for an evaluator to install; the suite
    runs with the same venv as the project. *Cost:* less expressive
    fixtures (the e2e test manages its own server thread).

---

## 17. Limitations and failure modes

- **Planner scope.** The rule brain handles the find → extract → enter →
  verify shape. A task with a different shape (e.g. "compare two
  invoices and email the cheaper vendor") has no subgoals and will end in
  `ask_user`. The LLM brain is the intended route for such tasks.
- **Regex extraction.** Amounts and dates are pulled out with regular
  expressions. An invoice in an unexpected format (amount written as
  words, a date in an unusual format, a different invoice-number scheme)
  will extract wrongly or not at all. The verifier catches a wrong
  amount/date (it compares against the record the agent entered — which
  would contain the same wrong value, so in fact it would *not* catch a
  consistent mis-extraction; the transcript is the only audit trail).
  This is the most important honest limitation in the project: the
  verifier checks consistency between the extracted facts and the system,
  not correctness against the document. A second, independent extraction
  (e.g. reading the PDF twice with a different method) would close it.
- **Browser tool scope.** Pages are driven by visible text and labels.
  JavaScript-heavy apps, logins, file uploads, and CAPTCHAs are out of
  scope. The HTTP fallback cannot run JavaScript at all.
- **Prompt injection.** Observation text (pages, files) is included in the
  LLM prompt without sanitisation. A hostile document could try to steer
  the model. Mitigations in place: the 11-tool boundary and the approval
  gate. No instruction-hierarchy handling.
- **LLM brain unverified against a live API.** Code-complete and tested
  for error/fallback paths, but never run end-to-end against OpenAI (no
  key during development). The verified path is the offline planner.
- **Single-process mock.** No auth, no concurrency control, no database.
  Two agents writing at once, or a restart mid-run, are untested.
- **No long-term memory.** Each run starts with no knowledge of previous
  runs. Vendor names and contacts are re-discovered every time.
- **Transcript may contain sensitive values.** If a task or a page
  contains secrets, they appear in `transcript.json`. Runs are local and
  gitignored, but the file should be treated as sensitive.

---

## 18. Future work

Ordered by value:

1. **Mocked-LLM tests for `LLMBrain.decide`** — a local fake
   OpenAI-compatible server in the test suite, so the LLM path is covered
   end-to-end without a key.
2. **Structured output** — JSON mode / function calling where the provider
   supports it, keeping the free-text parser as a fallback.
3. **A second demo task** — "chase the overdue invoice" (find overdue
   records, draft a reminder, ask for approval before sending), which
   exercises a different task shape and the email-sending tool.
4. **More tools** — email send, calendar, spreadsheets, element-selector
   browser actions.
5. **Long-term memory** — a small local store (SQLite) for facts across
   runs.
6. **Prompt-injection defences** — mark observation text as untrusted
   data in the prompt; add an instruction-hierarchy note; log when a
   page contains instruction-like text.
7. **Web dashboard** — live transcripts and approval buttons in the
   browser.
8. **Independent re-extraction in the verifier** — re-read the PDF and
   compare against the entered record, closing the consistent-
   mis-extraction gap in section 17.
9. **Real-company adapter** — Gmail + a real internal system behind
   OAuth, reusing the same agent core.

---

## Appendix A. Full demo transcript

The verified demo run (`runs/demo`, rule brain, auto-approve, 11 steps).
Reasoning and observation text are quoted from the real transcript.

| # | Action | Reasoning | Observation (abridged) |
|---|---|---|---|
| 1 | `browser_navigate` `http://127.0.0.1:5000/inbox` | opening the inbox to find the invoice email | Inbox table: 2026-10-22 Globex INV-G-881; 2026-10-20 Acme INV-2026-1042; 2026-10-15 Acme reminder; 2026-10-08 Globex welcome; 2026-09-18 Acme INV-2026-1031 |
| 2 | `browser_navigate` `http://127.0.0.1:5000/inbox/1` | opening the latest Acme Supplies Ltd email (2026-10-20) | Email: Invoice INV-2026-1042 – October services; attachment `inv-2026-1042.pdf` (downloaded to `runs/demo/downloads/`) |
| 3 | `read_file` `runs/demo/downloads/inv-2026-1042.pdf` | reading the invoice PDF | `TAX INVOICE / Vendor: Acme Supplies Ltd / Invoice number: INV-2026-1042 / Amount due: $4,850.00 / Due date: 19 November 2026 (2026-11-19)` |
| 4 | `browser_navigate` `http://127.0.0.1:5000/system` | opening the internal system to enter the invoice | Internal System: "No records entered yet." Form: vendor, invoice_no, amount, due_date |
| 5 | `browser_type` vendor = `Acme Supplies Ltd` | filling the vendor field | `Filled 'vendor' with 'Acme Supplies Ltd' (not submitted yet).` |
| 6 | `browser_type` invoice_no = `INV-2026-1042` | filling the invoice_no field | `Filled 'invoice_no' with 'INV-2026-1042' (not submitted yet).` |
| 7 | `browser_type` amount = `$4,850.00` | filling the amount field | `Filled 'amount' with '$4,850.00' (not submitted yet).` |
| 8 | `browser_type` due_date = `2026-11-19` | filling the due_date field | `Filled 'due_date' with '2026-11-19' (not submitted yet).` |
| 9 | `browser_submit` | submitting the invoice record | `Form submitted. … Acme Supplies Ltd / INV-2026-1042 / 4850.0 / 2026-11-19` |
| 10 | `http_get` `http://127.0.0.1:5000/system/api/records` | checking the internal system for the record | `[{"amount": 4850.0, "due_date": "2026-11-19", "invoice_no": "INV-2026-1042", "vendor": "Acme Supplies Ltd"}]` |
| 11 | `finish` "Entered invoice INV-2026-1042 … and confirmed it is listed there." | record confirmed in the internal system | `Verified: record for invoice INV-2026-1042 found in the internal system: amount 4850.0, due 2026-11-19` |

Final facts (with sources): `vendor = Acme Supplies Ltd`,
`invoice_no = INV-2026-1042`, `amount = $4,850.00`,
`due_date = 2026-11-19` — invoice figures sourced from `read_file`.

---

## Appendix B. Interview preparation

Likely questions from an evaluator, with the strong answer for each.
Use these to prepare; do not memorise them word for word — understand
the reasoning behind each answer.

**Q1. Walk me through the architecture.**
A: "One sentence in, one loop: a brain decides the next action, the
executor runs it through an approval gate, the tool returns an
observation, facts are mined into memory, and the loop repeats. The brain
is interchangeable — an LLM or an offline planner — behind one interface.
When the brain says finish, a separate verifier re-reads the target
system and compares the facts. Only then is it a success. Everything is
recorded in a transcript, a summary and screenshots."

**Q2. Why two brains?**
A: "The LLM generalises to tasks nobody scripted, but it needs a key,
costs money, and can answer in the wrong format. The offline planner
guarantees the demo runs anywhere with zero cost. One interface means the
rest of the system is written once, and the executor falls back from the
LLM to the planner automatically — so the system degrades instead of
failing."

**Q3. How does the agent know it actually succeeded?**
A: "It doesn't trust itself. The verifier is a separate component that
fetches the system's records through the API and compares vendor, invoice
number, amount and due date. The brain proposes finish; the verifier
certifies it. Two failed verifications end the run as incomplete."

**Q4. What happens when something fails?**
A: "Failures are observations, not crashes. A failed tool is retried
once, then the agent tries the other route — browser versus API — and
only then asks the user. A denied approval is an observation too. Asking
is bounded so the agent can't loop forever asking."

**Q5. How is this not just a script?**
A: "Nothing about the demo answer is in the code. The vendor is parsed
from the task sentence, the email is chosen from the observed inbox, the
figures come from the PDF it reads, and the same code handles a different
vendor — try the Globex task — with no changes. A script would have the
answers baked in; this one derives them from observations."

**Q6. What is the hardest part you had to get right?**
A: "Two things. First, making the PDF the source of truth — the first
version took the figures from the email body and skipped the document,
which is the lazy behaviour the demo is supposed to avoid. Second, the
invoice-number extraction: the downloaded file name contains the same
token in lower case, and the regex matched the file name before the
document. Both were caught by running the real demo and reading the
transcript, not by code review."

**Q7. What would you do differently with more time?**
A: "Structured output for the LLM instead of parsing free-text JSON —
that is the main failure mode. A second demo task with a different shape
to prove generalisation. And a verifier that re-reads the PDF itself, so
a consistent mis-extraction can't pass verification — right now the
verifier checks the facts against the system, not against the document,
and that's the honest gap in the design."

**Q8. Why a mock company instead of a real integration?**
A: "The task forbids real credentials and unauthorised access. A local
mock gives a genuinely working demo — real browser, real PDFs, real form
submission — with zero setup and zero risk, and the agent code doesn't
care: the same tools would drive a real system behind OAuth."

**Q9. How did you test it?**
A: "23 tests in stdlib unittest: unit tests for the planner stages,
extraction and the verifier, approval-gate tests, and a full end-to-end
test that starts the real mock app and runs the agent against it. Plus
manual verification runs where I read the whole transcript — that's how
the two bugs in section 13.3 were found."

**Q10. What are the limitations?**
A: "The planner only covers the find–read–enter–verify shape; new shapes
need the LLM. Extraction is regex-based, so unusual invoice formats can
misread. The verifier checks consistency, not correctness against the
document. And the LLM brain hasn't been run against a live paid API yet —
the verified path is the offline one. I'd rather state those plainly than
have an evaluator discover them."

---

## Appendix C. File inventory

Exact counts from the committed tree (`wc -l`, Python files only;
2,834 lines of application code + 245 lines of tests = 3,079 total):

| File | Lines | Role |
|---|---|---|
| `taskworker/agent.py` | 186 | ReAct executor |
| `taskworker/approval.py` | 38 | Approval gate |
| `taskworker/cli.py` | 118 | CLI |
| `taskworker/memory.py` | 70 | Run memory |
| `taskworker/report.py` | 69 | Run reports |
| `taskworker/verify.py` | 103 | Verifier |
| `taskworker/brain/base.py` | 43 | Brain interface |
| `taskworker/brain/llm_brain.py` | 179 | LLM brain |
| `taskworker/brain/rule_brain.py` | 540 | Offline planner + extraction |
| `taskworker/tools/base.py` | 69 | Observation + context |
| `taskworker/tools/browser.py` | 498 | Browser tool (2 backends) |
| `taskworker/tools/files.py` | 67 | File tools |
| `taskworker/tools/http_tool.py` | 82 | HTTP tools |
| `taskworker/tools/registry.py` | 141 | Tool registry + dispatch |
| `mock_company/app.py` | 226 | Mock company (Flask) |
| `mock_company/seed.py` | 202 | Seed data + invoice PDFs |
| `tests/test_brain.py` | 120 | Planner/extraction tests |
| `tests/test_verify_approval.py` | 62 | Verifier/approval tests |
| `tests/test_e2e.py` | 63 | End-to-end test |
| `demo/build_video.py` | 203 | Demo video builder |

Documentation: `README.md` (plain-language guide),
`ARCHITECTURE.md` (short architecture write-up), this file
(`TECHNICAL_DOCS.md`), `examples/invoice_task.md` (demo script).
