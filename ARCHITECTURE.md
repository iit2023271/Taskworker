# Architecture

## Overview

TaskWorker is a small ReAct agent: a loop in which a *brain* decides the
next action, an *executor* runs it through tools, and the result is
observed, remembered, and fed back into the next decision. The loop ends
when the brain declares the goal finished **and** an independent verifier
confirms the outcome in the target system.

```
goal ──▶ Brain.decide(state) ──▶ Action {tool, args, reasoning}
                                          │
                              ┌───────────┴───────────┐
                              │ approval gate (writes)│
                              └───────────┬───────────┘
                                          ▼
                                   Tool.run(args, ctx)
                                          │
                                          ▼
                                   Observation {ok, text,
                                     screenshot, data}
                                          │
                              ┌───────────┴───────────┐
                              │ fact mining → memory  │
                              │ transcript.json       │
                              └───────────┬───────────┘
                                          ▼
                              state' ──▶ Brain.decide(state') ...
                                          │
                              finish ──▶ Verifier ──▶ SUCCESS / NOT COMPLETED
```

## Components

### Brain (`taskworker/brain/`)

One interface, two implementations:

```python
class Brain(ABC):
    def decide(self, state: dict) -> dict:  # -> Action dict
```

`state` carries the goal, the facts collected so far (with sources), the
step history, the last observation, the tool schemas, and the attempt
count. The brain returns exactly one action per turn. It never touches
tools, the network, or the filesystem directly — that separation is what
makes the two brains interchangeable and the executor testable.

- **LLMBrain** (`llm_brain.py`) — builds a system prompt from the tool
  schemas and the rules (one JSON action per turn; use `finish` only when
  the goal is done; verify before finishing), calls an OpenAI-compatible
  chat-completions endpoint with `requests`, and parses the reply as JSON
  (markdown fences tolerated). A malformed reply gets one correction
  retry, then raises `BrainError`. No key raises a clear error telling the
  user to set `OPENAI_API_KEY` or use `--brain rule`.
- **RuleBrain** (`rule_brain.py`) — a goal-directed planner. It parses the
  vendor out of the goal sentence, keeps a subgoal checklist
  (inbox → latest vendor email → invoice PDF → system form → records
  check → finish), and at each turn picks the next action from the facts
  in memory and the last observation. A failed tool is retried once, then
  the alternative route is tried (browser ↔ HTTP API), then it asks the
  user. It is deliberately *not* a fixed script: the same code handles a
  different vendor, a different invoice number, or the inbox API instead
  of the browser, because every decision reads the current state.

### Executor (`taskworker/agent.py`)

The `Agent` owns the loop:

1. Ask the brain for the next action (max 30 steps by default).
2. If it is a write action, pass it through the `Approver`.
3. Dispatch it to the tool registry; on an unknown tool, record a failed
   observation instead of raising.
4. Mine durable facts from the observation
   (`extract_observation_facts` — shared by both brains so the verifier
   sees the same facts whichever brain drove) and store them in memory
   with their source.
5. On `finish`, run the verifier. If it passes, report success; if it
   fails twice, stop as incomplete and say why.
6. On a brain error (`BrainError` from the LLM brain), fall back to the
   rule brain mid-run and record the fallback in the report.

The executor also saves the transcript after every step, so a killed run
still leaves evidence.

### Tools (`taskworker/tools/`)

Every tool has a name, a JSON argument schema, and `run(args, ctx) ->
Observation`. The registry (`registry.py`) is the single place tools are
listed, which is also what the LLM brain's system prompt is built from —
adding a tool means adding one entry, and the LLM immediately knows about
it.

| Tool | Purpose |
|---|---|
| `browser_navigate` / `browser_click` / `browser_type` / `browser_submit` / `browser_read` | Drive a real browser by URL, visible text and form labels; screenshots on navigation. Linked PDFs are downloaded to the run directory and their local path is reported. |
| `read_file` | Read a PDF (pypdf), text, CSV or JSON file. |
| `list_dir` | List a directory. |
| `http_get` / `http_post` | Raw API access (JSON or form-encoded). |
| `finish` | Declare the goal done (triggers verification). |
| `ask_user` | Ask the user a question; the answer becomes the next observation. |

**Browser backends.** `browser.py` picks Playwright/Chromium when it is
importable and a browser binary exists, otherwise an `HttpBrowser`
(`requests` + stdlib HTML parsing for links and forms). Both expose the
same methods and return the same observation shape, so the agent's
behaviour does not depend on which backend is present — it degrades
instead of dying. This is a deliberate portability decision: an evaluator
without a browser binary can still run the whole demo.

### Memory (`taskworker/memory.py`)

`RunMemory` holds facts as `{key: {value, source, must_verify}}` and the
ordered step list. Facts are only ever added by mining observations, never
asserted by the brain — that is what makes the verifier's comparison
meaningful. `must_verify` marks the facts the verifier must check
(vendor, invoice number, amount, due date). The transcript is saved as
JSON after every step.

### Approval (`taskworker/approval.py`)

`WRITE_TOOLS = {browser_submit, http_post}`. In supervised mode the
executor prompts on the terminal before each write; a denial is recorded
as a failed observation ("denied by user") so the brain can replan or ask.
In auto mode (`--auto-approve`) writes proceed and are logged. Every
decision lands in the run report.

### Verification (`taskworker/verify.py`)

`verify_records(records, facts)` is a pure function: find the record with
the same invoice number and a matching vendor, then compare amount
numerically and due date as a string. `verify_via_api` fetches the
records first. Verification is deliberately separate from the brain: the
brain's job is to *try* to finish; the verifier's job is to *check*.

### Reporting (`taskworker/report.py`)

Each run writes `runs/<run_id>/transcript.json` (every step) and
`summary.md` (goal, outcome, verification, brain used, fallback flag,
approvals, evidence list), plus `screenshots/` and `downloads/`.

### Mock company (`mock_company/`)

A Flask app that plays the role of the company: an inbox with five
emails, three invoice PDFs (one target, one older invoice from the same
vendor, one newer invoice from a different vendor), and an internal
system with a form and a JSON records API. Records persist to
`mock_company/data/records.json`; `POST /system/api/reset` clears them
for repeatable demos. The route contract is the endpoint list in
`mock_company/app.py`.

## Data flow for the demo task

1. `browser_navigate /inbox` → observation lists the emails; facts:
   `inbox_seen`, `emails`.
2. Rule brain picks the latest email from "Acme Supplies Ltd" (token
   match on the vendor name; invoice-like emails preferred; latest date
   wins) → `browser_navigate /inbox/1`. The browser downloads the
   attached PDF; facts: `email_id`, `pdf_path`, plus figures from the
   email body.
3. The PDF is the source of truth, so the brain reads it:
   `read_file runs/<id>/downloads/inv-2026-1042.pdf` → facts
   `invoice_no`, `amount`, `due_date` (overwriting the email-body
   values with the document's values).
4. `browser_navigate /system`, then `browser_type` for each of the four
   fields (the approval gate asks first in supervised mode), then
   `browser_submit`.
5. `http_get /system/api/records` → the brain sees the record listed and
   calls `finish`.
6. The verifier re-fetches the records and compares all four fields.
   Only then is the run reported as SUCCESS.

## Why this shape

- **One loop, many tasks.** Nothing in the executor, the tool registry,
  the memory or the verifier knows about invoices. A new task needs a new
  brain prompt (LLM) or a new subgoal set (rule planner) — the machinery
  stays the same. That is the generalisation the problem statement asks
  for.
- **The brain is the only part that "thinks".** Keeping decisions in one
  place makes the agent explainable: the transcript shows a reasoning
  line per step, and the report shows which brain decided.
- **Failure is a first-class outcome.** Retries, alternative routes,
  bounded asking, verification failures and denials are all ordinary
  observations in the transcript — not exceptions, not silent skips.
- **Evidence over claims.** A run that cannot verify itself reports
  NOT COMPLETED with the reason. The summary, transcript and screenshots
  are the deliverable, not a chat message saying "done".
