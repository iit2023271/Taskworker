# TaskWorker — Autonomous AI Task Worker (prototype)

> **Plain-English summary:** You type a task in normal words — for
> example, *"Find the latest invoice from Acme Supplies Ltd, extract the
> amount and due date, enter it into our internal system, and tell me once
> it is done."* TaskWorker does the whole job on the computer by itself:
> it opens the inbox, finds the right email, reads the invoice PDF, fills
> in the internal system, checks its own work, and tells you it is done —
> with proof. No API key is needed for the built-in offline mode.

---

## Contents

- [1. What is this?](#1-what-is-this)
- [2. The problem it solves](#2-the-problem-it-solves)
- [3. What it actually does — the demo, step by step](#3-what-it-actually-does--the-demo-step-by-step)
- [4. Watch it work](#4-watch-it-work)
- [5. How it works — the simple version](#5-how-it-works--the-simple-version)
- [6. Quick start — run it yourself](#6-quick-start--run-it-yourself)
- [7. Using it — every command, explained](#7-using-it--every-command-explained)
- [8. The two brains — which one should you use?](#8-the-two-brains--which-one-should-you-use)
- [9. Safety — what stops it from doing something wrong?](#9-safety--what-stops-it-from-doing-something-wrong)
- [10. What you get after a run — the evidence](#10-what-you-get-after-a-run--the-evidence)
- [11. Project tour — what every folder and file is](#11-project-tour--what-every-folder-and-file-is)
- [12. Frequently asked questions](#12-frequently-asked-questions)
- [13. Troubleshooting — when something goes wrong](#13-troubleshooting--when-something-goes-wrong)
- [14. Glossary — every technical word, explained simply](#14-glossary--every-technical-word-explained-simply)
- [15. Known limitations — an honest list](#15-known-limitations--an-honest-list)
- [16. What I would build next](#16-what-i-would-build-next)
- [17. For evaluators — how to check every claim in this file](#17-for-evaluators--how-to-check-every-claim-in-this-file)

---

## 1. What is this?

TaskWorker is a small **autonomous AI worker**. "Autonomous" means it
works on its own, without you clicking through the steps. You describe the
goal in one sentence of normal English, and it figures out the steps,
performs them on the computer, watches what happens after each step, fixes
problems when they appear, and only says "done" after it has checked its
own work.

Think of it like hiring a careful office assistant for one job: you tell
them the outcome you want, they go and do it, and they come back with a
report and the receipts. The difference is that this assistant is a
program — it runs the same way every time, it writes down everything it
did, and it never claims success it cannot prove.

It is a **prototype**, built to demonstrate the idea for an internship
application. It is deliberately narrow — it does one kind of job really
well (find a document, read it, enter the details somewhere, verify) —
instead of pretending to do everything.

### In 30 seconds

| Question | Answer |
|---|---|
| What do I type? | One sentence, e.g. the invoice task below. |
| What does it do? | Opens a browser, reads an inbox and a PDF, fills a form, checks the result. |
| Do I need an API key? | No. The built-in offline planner needs no key and no internet. |
| Does it use AI? | Yes — optionally. It has two "brains": a large language model (LLM) brain and an offline rule-based planner. You choose. |
| How do I know it worked? | It re-reads the system and compares the numbers. Every run leaves a transcript, a summary and screenshots. |
| How long does a run take? | A few seconds with the offline brain; tens of seconds with an LLM, depending on the provider. |
| What do I need to run it? | Python 3.10+ and the libraries in `requirements.txt`. Setup takes about 5 minutes. |

---

## 2. The problem it solves

This project was built for an internship task. The task, in full, is:

> Build a prototype AI worker that takes a natural-language task and
> autonomously completes it using a computer — understanding the goal,
> breaking it into actions, using the browser, files, APIs or a simulated
> company application, observing results, deciding next steps, remembering
> discovered information, detecting failures, retrying or trying
> alternatives, verifying the outcome, and asking for clarification or
> approval when it cannot safely proceed — then returning a concise summary
> with evidence.

The example task in the statement is:

> *"Find the latest invoice from Company X, extract the amount and due
> date, enter it into our internal system, and tell me once it is done."*

The statement also asks for: a GitHub repository (or equivalent link), a
README with setup and run instructions, a short architecture explanation,
the important technical and design decisions, a demo video or live demo,
known limitations, what to build next, assumptions, and details of the
models, APIs, frameworks and pre-built components used.

This repository is the answer to that task, point by point. Section 17 of
this file maps every requirement in the statement to the exact place in
the code that satisfies it, so an evaluator can check each one.

### Why a mock company?

The task says: no real company credentials, use sandbox or mock
environments. So instead of connecting to a real company's email and
systems (which would need passwords and could touch real data), this
project ships its own tiny pretend company that runs on your own computer:
an inbox with emails, invoice PDFs, and an internal system with a form.
The agent works against that pretend company using a real browser and real
files — so the demo is genuinely working, not a slideshow, and it is
completely safe: nothing leaves your computer and no real data is involved.

"Company X" in the statement is a placeholder name. In the demo, the
company is called **Acme Supplies Ltd**.

---

## 3. What it actually does — the demo, step by step

Here is the demo task again:

```
Find the latest invoice from Acme Supplies Ltd, extract the amount and due
date, enter it into our internal system, and tell me once it is done.
```

Given only that sentence, the agent does this:

**Step 1 — Opens the inbox.** It opens the company inbox in a real
Chromium browser window (the same browser engine Chrome uses). The inbox
has five emails.

**Step 2 — Picks the right email.** This is the first real test. The inbox
is deliberately set up with traps:

- A **newer** email (22 October) from a different company, Globex Corp,
  with invoice INV-G-881. If the agent just picked the newest email, it
  would get the wrong vendor.
- An **older** Acme invoice (18 September), INV-2026-1031. If the agent
  just picked any Acme email, it might get the old one.
- A payment-terms reminder and a welcome email with no invoice at all.

The agent picks the latest email **from Acme Supplies Ltd that contains an
invoice**: 20 October, invoice INV-2026-1042.

**Step 3 — Reads the invoice PDF.** The email has an attachment,
`inv-2026-1042.pdf`. The agent downloads it and reads the document
itself. The PDF says: vendor Acme Supplies Ltd, invoice number
INV-2026-1042, amount **$4,850.00**, due date **19 November 2026
(2026-11-19)**. The PDF is treated as the source of truth — the email
body also mentions the figures, but the agent uses the document's values,
not the email's summary of them.

**Steps 4–8 — Enters the record.** The agent opens the internal system,
fills in the four fields one by one — vendor, invoice number, amount, due
date — and submits the form.

**Step 9 — Checks its own work.** Instead of trusting the submit button,
the agent re-reads the internal system's records and looks for the record
it just entered.

**Step 10 — Reports.** It declares the job done, and the run only counts
as a success because the verification passed. The final output is:

```
Outcome: SUCCESS
Summary: Entered invoice INV-2026-1042 from Acme Supplies Ltd ($4,850.00,
due 2026-11-19) into the internal system and confirmed it is listed there.
Verification: passed=True — record for invoice INV-2026-1042 found in the
internal system: amount 4850.0, due 2026-11-19
Steps: 11
```

The whole run takes a few seconds with the offline brain. The complete
step-by-step log of the demo run is in `runs/demo/transcript.json` (the
`runs/` folder is created when you run it yourself), and the full
annotated trace is in Appendix A of
[`TECHNICAL_DOCS.md`](TECHNICAL_DOCS.md).

---

## 4. Watch it work

**Demo video:** [`demo/taskworker-demo.mp4`](demo/taskworker-demo.mp4)
— 85 seconds, 1280×720, narrated. It shows the real run: the task being
typed, the inbox, the email, the invoice, the form being filled, the
record appearing in the system, and the final SUCCESS report. Every
screenshot in the video is a genuine screenshot taken by the agent during
the run (from `runs/demo/screenshots/`), not a mock-up.

The script the video follows is in
[`examples/invoice_task.md`](examples/invoice_task.md), and the video can
be rebuilt at any time with `python demo/build_video.py` (it re-renders
the scenes from the demo run and re-records the narration).

---

## 5. How it works — the simple version

### The loop

Everything the agent does follows one repeating loop:

```
  THINK → ACT → LOOK → REMEMBER → THINK → ACT → LOOK → REMEMBER → ...
```

In plain words:

1. **Think.** The "brain" looks at the goal, what it has learned so far,
   and what just happened, and decides the single next action.
2. **Act.** It performs that one action — open a page, click something,
   type into a field, read a file, call an API.
3. **Look.** It reads what came back: the page content, the file text, the
   API response, or an error message.
4. **Remember.** It writes down any durable facts it learned (for
   example, "the amount is $4,850.00, and I read that in the PDF") and
   saves the step to the transcript.
5. Repeat, until the brain says the goal is finished — and then the
   **verifier** independently checks the result before anyone is told
   "done".

This think–act–look pattern is called a **ReAct loop** (Reason + Act).
It is the standard way to build agents that do real work, because the
agent never has to plan the whole job perfectly in advance: it can react
to what actually happens, including surprises.

### The two brains

The "brain" is the part that decides the next action. TaskWorker has two,
and they are interchangeable — the rest of the program (the tools, the
memory, the verifier) is identical whichever brain is in charge:

| | LLM brain | Offline planner ("rule brain") |
|---|---|---|
| **What it is** | A large language model (like GPT-4o-mini, Gemini, or a local model) that reads the goal and the history and replies with the next action. | A built-in planner written in plain code. It works out the subgoals from the task sentence and picks the next step from what it has observed. |
| **Needs** | An API key (or a local model server). Costs money per run with a paid provider; free with Ollama or a free-tier key. | Nothing. No key, no internet, no cost. |
| **Good at** | Tasks nobody wrote a plan for — genuinely new, open-ended jobs. | The invoice-style job, and anything with the same shape (find → read → enter → verify). Always available, always the same behaviour. |
| **Weakness** | Can answer in the wrong format or misunderstand; costs and latency depend on the provider. | Cannot improvise far outside its subgoal shapes; new task types need the LLM brain (or new subgoals added in code). |
| **Use it with** | `--brain llm` | `--brain rule` |

**`--brain auto` (the default)** uses the LLM when an API key is set, and
the offline planner otherwise. If the LLM fails in the middle of a run
(bad answer, API error, no key), the agent automatically switches to the
offline planner for the rest of the run and records the switch in the
report, so you always know which brain did the work.

An analogy: the LLM brain is like hiring an experienced generalist who
can handle anything but sometimes mishears you; the offline planner is
like a written checklist that never mishears anything but only covers the
jobs on the list. TaskWorker lets you pick, and falls back from the
generalist to the checklist rather than failing.

### The tools

The brain never touches the computer directly. It can only ask for one of
**11 tools** (see section 7 for the full list with arguments):

- **Browser tools (5):** open a page, click a link or button, type into a
  form field, submit a form, re-read the current page. The browser is a
  real Chromium browser when one is installed; if not, a lightweight
  built-in web reader takes over automatically and behaves the same way.
- **File tools (2):** read a file (PDF, text, CSV, JSON) and list a
  directory.
- **API tools (2):** fetch a URL and post data to a URL.
- **Control tools (2):** `finish` (declare the goal done — this triggers
  verification) and `ask_user` (ask the human a question when the agent
  cannot safely proceed).

Because the brain can only use these tools, it cannot do anything outside
them — it cannot delete files, run shell commands, or reach the wider
internet beyond the addresses it is given. That is a deliberate safety
boundary.

### Memory

The agent remembers in two ways:

- **Facts:** durable things it learned, each stored with its source —
  for example, "amount = $4,850.00, source: the invoice PDF". The four
  facts the verifier must check (vendor, invoice number, amount, due
  date) are marked as "must verify".
- **Steps:** the full ordered history of every action and observation,
  saved to `transcript.json` after every step — so even a run that is
  interrupted leaves a complete record.

### Verification — the part that makes "done" mean something

Most demos of AI agents end when the agent *says* it is done. TaskWorker
does not trust that. When the brain calls `finish`, a separate component
— the **verifier** — fetches the internal system's records itself and
checks that a record exists with the same vendor, invoice number, amount
and due date. Only if that check passes does the run report SUCCESS. If
verification fails twice, the run ends as NOT COMPLETED, with the reason
written in the report. The verifier is not the brain's opinion; it is an
independent re-read of the system.

---

## 6. Quick start — run it yourself

You need **Python 3.10 or newer**. The whole setup takes about 5 minutes
plus download time.

### Step 1 — Get the code

Download the repository (or the `TaskWorker.zip` file) and unzip it. Open
the `taskworker` folder — you should see `README.md`,
`requirements.txt`, and the `taskworker/` and `mock_company/` folders.

### Step 2 — Check Python

Open a terminal inside the `taskworker` folder:

- **Windows:** click the address bar in File Explorer, type `cmd`, press
  Enter.
- **Mac:** open Terminal, type `cd ` (with a trailing space), drag the
  `taskworker` folder into the window, press Enter.

Then run:

```
python --version
```

You should see `Python 3.10` or newer. If it says "not recognized", install
Python from [python.org](https://www.python.org/downloads/) and try again.
(On Mac, use `python3 --version` and `python3` in every command below.)

### Step 3 — Create an isolated environment and install

```
python -m venv .venv
```

Activate it — Windows:

```
.venv\Scripts\activate
```

Mac / Linux:

```
source .venv/bin/activate
```

You should see `(.venv)` at the start of the terminal line. Then:

```
pip install -r requirements.txt
playwright install chromium
```

The first command installs the Python libraries (Flask, Playwright,
pypdf, fpdf2, requests). The second downloads the Chromium browser the
agent drives (a one-time download, a few minutes).

### Step 4 — Start the mock company

Open a **second** terminal in the same folder, activate the venv there
too, and run:

```
python -m taskworker mock
```

Leave this window open. Open http://127.0.0.1:5000 in your browser — you
should see the Company Portal. This is the pretend company the agent will
work in.

### Step 5 — Run the agent

In the **first** terminal, run:

```
python -m taskworker run "Find the latest invoice from Acme Supplies Ltd, extract the amount and due date, enter it into our internal system, and tell me once it is done." --brain rule --auto-approve
```

You should see:

```
Outcome: SUCCESS
Summary: Entered invoice INV-2026-1042 from Acme Supplies Ltd ($4,850.00, due 2026-11-19) into the internal system and confirmed it is listed there.
Verification: passed=True
Steps: 11
```

Open http://127.0.0.1:5000/system in your browser: the record is listed
there. The full evidence is in the `runs/` folder the run created.

### Step 6 — Try it supervised

Reset the system first:

```
curl -X POST http://127.0.0.1:5000/system/api/reset
```

Then run the same command as Step 5 **without** `--auto-approve`. The run
will pause and ask `Approve browser_submit {}? [y/n]` — type `y` and
press Enter. That is the approval gate in action: nothing is written to
the system without your say-so.

### Step 7 — Run the tests

```
python -m unittest discover -s tests -v
```

All 23 tests should pass, including a full end-to-end test that runs the
agent against the mock company and checks the record.

---

## 7. Using it — every command, explained

The program has three commands: `mock`, `seed`, and `run`.

### `python -m taskworker mock`

Starts the mock company (the pretend company: inbox, invoices, internal
system) so the agent has somewhere to work.

```
python -m taskworker mock [--port PORT]
```

- `--port` — which port to listen on. Default `5000`. If port 5000 is
  already used on your machine, use `--port 5001` and pass the same URL to
  the agent with `--mock-url`.

### `python -m taskworker seed`

Regenerates the mock company's data: the five inbox emails and the three
invoice PDFs. Run this if you ever want to restore the demo data to its
original state. It never deletes records already entered in the internal
system.

```
python -m taskworker seed
```

### `python -m taskworker run "TASK"`

Runs the agent on a task you write in plain English.

```
python -m taskworker run "TASK" [--brain {auto,llm,rule}] [--auto-approve]
                                 [--mock-url URL] [--max-steps N]
                                 [--run-dir DIR]
```

| Option | What it does | Default |
|---|---|---|
| `TASK` | The task, in plain English, in quotes. | (required) |
| `--brain auto` | LLM if an API key is set, otherwise the offline planner. | `auto` |
| `--brain llm` | Always the LLM brain. Fails clearly if no key is set, then falls back to the offline planner mid-run. | — |
| `--brain rule` | Always the offline planner. No key, no internet needed. | — |
| `--auto-approve` | Writes go through without asking. Without it, the agent asks before every write. | off (supervised) |
| `--mock-url URL` | Where the mock company is running. | `http://127.0.0.1:5000` |
| `--max-steps N` | Maximum steps before the agent must stop. Prevents endless runs. | `30` |
| `--run-dir DIR` | Where to write the transcript, summary and screenshots. | `runs/<random-id>` |

**Examples:**

```bash
# Offline demo (no key needed)
python -m taskworker run "Find the latest invoice from Acme Supplies Ltd, extract the amount and due date, enter it into our internal system, and tell me once it is done." --brain rule --auto-approve

# Supervised (asks before writing)
python -m taskworker run "<same task>" --brain rule

# LLM brain (needs OPENAI_API_KEY set; see section 8)
python -m taskworker run "<same task>" --brain llm

# A different vendor, to see the planner generalise
python -m taskworker run "Find the latest invoice from Globex Corp, extract the amount and due date, enter it into our internal system, and tell me once it is done." --brain rule --auto-approve
```

### Environment variables (LLM brain only)

| Variable | Meaning | Default |
|---|---|---|
| `OPENAI_API_KEY` | Your API key. Without it the LLM brain cannot run. | (none) |
| `OPENAI_BASE_URL` | The API endpoint. Change this to use another provider (OpenRouter, a local Ollama server, Google's Gemini OpenAI-compatible endpoint). | `https://api.openai.com/v1` |
| `OPENAI_MODEL` | Which model to use. | `gpt-4o-mini` |
| `MOCK_PORT` | Port for the mock company (used by `seed`/`mock` tooling). | `5000` |

Set them in the terminal before running, for example on Windows `cmd`:

```
set OPENAI_API_KEY=sk-...
set OPENAI_MODEL=gpt-4o-mini
```

On Mac / Linux:

```
export OPENAI_API_KEY=sk-...
export OPENAI_MODEL=gpt-4o-mini
```

Or copy `.env.example` to `.env` and fill it in as a reminder of what to
set — note the program reads the real environment, not the `.env` file,
so you still need to export the values in your terminal. Never commit a
real key: `.env` is in `.gitignore`.

---

## 8. The two brains — which one should you use?

**Use the offline planner (`--brain rule`) when:**

- You have no API key, no internet, or no budget for API calls.
- You want the demo to work identically every time (for example, in front
  of an evaluator).
- The task has the shape find → read → enter → verify.

**Use the LLM brain (`--brain llm`) when:**

- The task is new and open-ended — something nobody wrote a plan for.
- You have a key and you want to show the agent generalising.
- You want the agent to explain its reasoning in its own words (the LLM
  writes a fresh reasoning line each step; the planner's lines are
  templated).

**Free ways to try the LLM brain:**

1. **Ollama (free, local, no key):** install Ollama from
   [ollama.com](https://ollama.com), run `ollama pull llama3.1:8b`, then
   set `OPENAI_BASE_URL=http://localhost:11434/v1`,
   `OPENAI_API_KEY=ollama`, `OPENAI_MODEL=llama3.1:8b` and run with
   `--brain llm`. Note: small local models sometimes answer in the wrong
   format; the agent retries once and then falls back to the offline
   planner, and the report says so honestly.
2. **Gemini free key:** get a free key at
   [Google AI Studio](https://aistudio.google.com), set
   `OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/`,
   `OPENAI_MODEL=gemini-2.0-flash`, and run with `--brain llm`.
3. **OpenAI (paid):** a key from [platform.openai.com](https://platform.openai.com)
   with billing enabled; only `OPENAI_API_KEY` is needed.

**What the report tells you:** every run's `summary.md` records which
brain ran and whether it fell back (`Fell back to rule brain: True/False`),
so an evaluator can always tell which brain actually did the work. The
LLM brain has never been run against a live paid API during development
(no key was available); it is code-complete and tested for its error and
fallback paths, and the offline demo — the one in the video — needs no key
at all.

---

## 9. Safety — what stops it from doing something wrong?

Four layers, each independent:

1. **The approval gate.** Anything that changes state in the outside
   world — submitting a form, posting data — is a "write action". In
   supervised mode (the default) the agent must ask you before each one:
   `Approve browser_submit {}? [y/n]`. If you answer `n`, the write does
   not happen; the agent sees "denied by user" as an observation and can
   replan or ask you what to do instead. Every approval decision is logged
   in the run report. `--auto-approve` turns this off and is meant for
   demos and trusted runs.
2. **Independent verification.** As described in section 5, success
   requires re-reading the target system and matching the facts. The agent
   cannot talk its way to a SUCCESS.
3. **Bounded runs.** A maximum of 30 steps by default (`--max-steps`).
   Asking the user is bounded too: if the `ask_user` channel itself fails
   (for example, there is no terminal to read from), the run ends instead
   of asking forever.
4. **A small, fixed tool set.** The brain can only call the 11 tools in
   section 7. It cannot run shell commands, delete files, or browse the
   wider internet beyond the addresses it is given. The mock company runs
   locally, so even a mistake touches nothing real.

There is also a **retry and reroute policy**: a failed tool is retried
once; if it fails again, the agent tries the other route (real browser ↔
API); only then does it ask the user. Failures are ordinary observations
in the transcript, not crashes.

---

## 10. What you get after a run — the evidence

Every run writes a folder, `runs/<run-id>/`:

```
runs/<run-id>/
  transcript.json   every step: the action, the reasoning, the observation,
                    and the facts learned (saved after every step)
  summary.md        a human-readable report: goal, outcome, verification
                    result, brain used, whether it fell back, approvals,
                    and the list of evidence
  screenshots/      browser screenshots taken during the run
  downloads/        files the agent downloaded (for the demo: the invoice PDF)
```

`summary.md` for the demo run looks like this:

```markdown
# TaskWorker run — demo

**Goal:** Find the latest invoice from Acme Supplies Ltd, extract the amount
and due date, enter it into our internal system, and tell me once it is done.

**Outcome:** SUCCESS

**Summary:** Entered invoice INV-2026-1042 from Acme Supplies Ltd
($4,850.00, due 2026-11-19) into the internal system and confirmed it is
listed there.

**Steps taken:** 11

**Brain:** rule

**Fell back to rule brain:** False

## Verification

Passed: True

record for invoice INV-2026-1042 found in the internal system: amount
4850.0, due 2026-11-19

## Evidence

Screenshots:
- shot_01.png
- shot_02.png
- shot_03.png
- shot_04.png
Downloaded files:
- inv-2026-1042.pdf

## Transcript

Full step-by-step log: transcript.json

## Approvals

- browser_submit {} -> auto-approved
```

---

## 11. Project tour — what every folder and file is

```
taskworker/                 the agent itself
  __init__.py               public exports (Agent, brains, memory, tools)
  __main__.py               lets you run it as: python -m taskworker ...
  agent.py                  the ReAct loop: brain -> approval -> tool ->
                            observation -> memory -> loop; verification
                            on finish; LLM -> rule fallback
  approval.py               the approval gate (write tools, supervised
                            vs auto, decision log)
  cli.py                    the command line: mock / seed / run and flags
  memory.py                 RunMemory: facts (with source + must_verify)
                            and the step history; saves transcript.json
  report.py                 writes summary.md + transcript.json per run
  verify.py                 the verifier: compares collected facts with
                            the system's records
  brain/
    base.py                 the Brain interface every brain implements
    llm_brain.py            the LLM brain (OpenAI-compatible API)
    rule_brain.py           the offline planner + the field-extraction
                            helpers shared with the executor
  tools/
    base.py                 the Observation shape + ToolContext
    browser.py              the browser tool: Playwright/Chromium backend
                            with an HTTP fallback; downloads PDFs
    files.py                read_file (PDF/text/CSV/JSON) + list_dir
    http_tool.py            http_get + http_post (JSON or form data)
    registry.py             the list of all 11 tools, their schemas,
                            and the dispatcher
mock_company/               the pretend company the agent works in
  app.py                    Flask app: dashboard, inbox, invoice PDFs,
                            internal system, JSON APIs, reset
  seed.py                   regenerates the emails and invoice PDFs
  data/
    seed.json               the five inbox emails
    invoices/               the three invoice PDFs
    records.json            records entered in the internal system
                            (starts empty: [])
tests/                      the test suite (unittest, no extra dependencies)
  test_brain.py             planner stages, vendor picking, extraction
  test_verify_approval.py   verifier pass/fail cases + approval gate
  test_e2e.py               full run against the real mock app
examples/
  invoice_task.md           the demo task, the commands, and why it is a
                            real test
demo/
  taskworker-demo.mp4       the 85-second narrated demo video
  build_video.py            rebuilds the video from the demo run
README.md                   this file
ARCHITECTURE.md             the short architecture write-up
TECHNICAL_DOCS.md           the full technical documentation, requirement
                            map, and interview preparation
requirements.txt            Python dependencies
.env.example                the environment variables, with no real values
.gitignore                  keeps virtualenvs, run folders and secrets
                            out of git
```

Total size: about 3,100 lines of code and tests (agent core, mock app,
tests), plus documentation.

---

## 12. Frequently asked questions

**Do I need an API key?**
No. The offline planner (`--brain rule`) needs no key, no internet, and
no money. A key is only needed if you choose the LLM brain.

**Does it need the internet?**
After the one-time setup (installing libraries and the Chromium browser),
the offline demo runs entirely on your own computer. The LLM brain needs
the internet to reach its API.

**Is it safe to run?**
Yes. It only talks to the mock company running on your own computer
(`127.0.0.1`), it can only use its 11 tools, and in supervised mode it
asks before writing anything. Nothing is uploaded anywhere.

**Can it do other tasks?**
With the LLM brain, yes — any task that can be done with a browser, files
and APIs. With the offline planner, tasks with the shape find → read →
enter → verify work; for example, try the Globex invoice task in section
7 — the planner generalises to a different vendor without any code change.
Genuinely new task shapes need the LLM brain or a new subgoal set in
`rule_brain.py`.

**Why does the agent read the PDF instead of just using the email?**
Because the email is a summary and the PDF is the document. In real work
the two can disagree (a typo in the email, an outdated figure). The agent
is designed to treat the document as the source of truth — that is a
deliberate design decision, documented in `ARCHITECTURE.md`.

**What happens if something fails mid-run?**
The agent retries the failed step once, then tries the alternative route
(browser ↔ API), then asks you. If verification fails twice, the run ends
as NOT COMPLETED with the reason in the report. Nothing is silently
pretended to have worked.

**What if I run it twice without resetting?**
The record is entered a second time, so the system will hold two identical
records. Reset between runs with
`curl -X POST http://127.0.0.1:5000/system/api/reset`.

**Can I see what the agent was thinking?**
Yes — every step in `transcript.json` has a `reasoning` line, and the
screenshots show what the browser saw at each stage.

**Does it work on Windows / Mac / Linux?**
Yes — Python, Playwright and Flask are cross-platform. The commands differ
slightly (see section 6): `python` vs `python3`, and the venv activation
command.

**How much does the LLM brain cost?**
With the default model (`gpt-4o-mini`) a run of ~11 steps costs a fraction
of a cent. With Ollama or a free Gemini key it costs nothing.

**Where do I report a bug or ask for a feature?**
Open an issue on the GitHub repository with the step number, the command
you ran, and the contents of the run's `transcript.json` — that file is
usually enough to diagnose any problem.

---

## 13. Troubleshooting — when something goes wrong

**`python: command not found` / `'python' is not recognized`**
Python is not installed, or not on your PATH. Install it from python.org
(tick "Add Python to PATH" on Windows during install). On Mac, try
`python3` instead.

**`pip install -r requirements.txt` fails**
Check your internet connection (this step downloads libraries). If you
are behind a proxy, you may need to set it first. Make sure the venv is
activated — you should see `(.venv)` in the terminal.

**`playwright install chromium` fails or hangs**
Same cause: it downloads a browser (~150 MB). Wait longer, or try again.
Without Chromium the agent still works — the browser tool falls back to
its built-in HTTP reader — but you will not get screenshots.

**`python -m taskworker mock` says the port is already in use**
Something else is using port 5000 (on some Macs, AirPlay uses it). Stop
the other program, or start the mock on another port:
`python -m taskworker mock --port 5001`, and add
`--mock-url http://127.0.0.1:5001` to the `run` command.

**The agent run says `NOT COMPLETED` or verification failed**
First reset the system (`curl -X POST
http://127.0.0.1:5000/system/api/reset`) and run again. If it still
fails, open the run's `transcript.json` and `summary.md` in `runs/` — the
last steps show exactly which step failed and what the system replied.
Common cause: the mock company was not running when the agent started
(step 1 of section 6 was skipped).

**The browser opens but the agent sees an empty page**
The mock company may have started on a different port than the agent is
using. Check the URL the agent was told (`--mock-url`) matches the port
the mock is actually on.

**`Approve browser_submit?` appears and nothing happens**
The agent is waiting for your answer in the terminal. Type `y` and press
Enter to approve, or `n` to deny. If you run without a terminal (for
example, from a script), use `--auto-approve` instead.

**Tests fail**
Run them with `-v` to see which test failed:
`python -m unittest discover -s tests -v`. The end-to-end test starts its
own mock server on port 5051 — if that port is busy, stop whatever is
using it and retry. Make sure you run the tests from the project root
(the folder containing `taskworker/` and `tests/`).

**The video will not play**
It is a standard H.264 MP4 (1280×720). Any modern browser or media player
opens it. Rebuild it with `python demo/build_video.py` if needed (this
needs the `runs/demo` run folder and the TTS tool used during development;
on a fresh machine, watch the shipped `demo/taskworker-demo.mp4` instead).

---

## 14. Glossary — every technical word, explained simply

- **Agent** — a program that works toward a goal on its own, by deciding
  actions and observing their results, instead of following a fixed list
  of instructions.
- **API** — a way for programs to talk to each other over the web. Here,
  the internal system has an API the agent uses to read the records
  (`GET /system/api/records`).
- **API key** — a secret password that lets a program use a paid service
  (here, an LLM provider). Keep it private; never put a real one in git.
- **Autonomous** — working without human guidance during the task.
- **Brain** — the part of the agent that decides the next action. See
  section 5.
- **Chromium** — the open-source browser engine behind Google Chrome. The
  agent drives a real Chromium window to do its work.
- **CLI** — command-line interface: controlling the program by typing
  commands in a terminal.
- **Fallback** — a backup plan that runs automatically when the first plan
  fails. Here, the LLM brain falls back to the offline planner.
- **Flask** — a small Python library for building websites and web APIs.
  The mock company is built with it.
- **LLM (large language model)** — an AI model trained on vast amounts of
  text that can read, write and reason in natural language (for example,
  GPT-4o-mini, Gemini, Llama).
- **Mock / simulated company** — a small pretend version of a company's
  systems, running locally, so the agent can be tested without real
  credentials or real data.
- **Observation** — what comes back after the agent does something: the
  page it sees, the file it read, the API's answer, or an error.
- **PDF** — Portable Document Format: the file type invoices are usually
  sent as.
- **Playwright** — a library that lets a program control a real browser
  (open pages, click, type, take screenshots).
- **Prompt** — the text sent to an LLM telling it what to do and what the
  rules are.
- **ReAct loop** — Reason + Act: the repeating think → act → observe
  cycle the agent uses.
- **Regex (regular expression)** — a pattern for finding text, for example
  "a dollar amount" or "a date". The offline planner uses regexes to pull
  the amount and due date out of the invoice text.
- **Transcript** — the complete step-by-step record of a run, saved as
  JSON.
- **Verification** — independently checking the result in the target
  system, instead of believing the agent's word for it.
- **Virtual environment (venv)** — a private folder that holds a
  project's Python libraries separately from the rest of the computer, so
  they cannot conflict with other projects.

---

## 15. Known limitations — an honest list

- The offline planner handles invoice-style tasks (find → extract → enter
  → verify) and generalises within that shape; genuinely open-ended tasks
  need the LLM brain.
- The browser tool drives pages by visible text and labels. Heavily
  JavaScript-driven apps, logins and CAPTCHAs are out of scope for this
  prototype.
- The LLM brain needs an API key and network access; cost and latency
  depend on the provider. Small local models sometimes answer in the wrong
  format (the agent retries once, then falls back — the report says so).
- The mock system is single-process with one JSON file for storage; there
  is no multi-user support, authentication, or database.
- Verification compares the facts the agent collected. If the agent
  extracted the wrong invoice entirely (for example, it misread which
  vendor an email was from), the verifier would check that wrong record
  consistently — the transcript is the audit trail for that case.
- The LLM brain has not been run against a live paid API during
  development (no key was available). It is code-complete and tested for
  its error and fallback paths; the offline demo is the verified path.
- There is no graphical user interface — the agent is driven from the
  terminal, and approvals happen there too.

---

## 16. What I would build next

1. **More tools** — send email, calendar, spreadsheets, and a generic
   form-filling browser tool with element selectors.
2. **A second demo task** — for example, "chase the overdue invoice":
   find overdue records, draft a reminder email, and ask for approval
   before sending. This would show the agent handling a multi-step job
   with a genuinely different shape.
3. **Long-term memory** — persist facts across runs (vendors, contacts)
   in a small local store, so the agent gets faster and smarter over time.
4. **Structured LLM output** — use the provider's JSON mode or function
   calling instead of parsing free-text JSON, which removes the main
   failure mode of the LLM brain.
5. **A web dashboard** — live run transcripts and approval buttons in a
   browser page, instead of the terminal.
6. **A real-company adapter** — the same agent against a real Gmail
   account and a real system, with OAuth and proper permissions, once
   credentials are available.

---

## 17. For evaluators — how to check every claim in this file

| Claim | How to check it |
|---|---|
| The demo completes and verifies | Run section 6, steps 4–5. Expected: `Outcome: SUCCESS`, `Verification: passed=True`, 11 steps. |
| The agent picks the right invoice over the traps | The inbox (`/inbox`) shows the newer Globex invoice and the older Acme invoice; the transcript's step 2 opens `/inbox/1` (the latest Acme invoice). |
| The PDF is the source of truth | Step 3 of the transcript is `read_file` on the downloaded PDF, and the facts in the transcript carry `source: read_file`. |
| Verification is independent | `taskworker/verify.py` re-fetches `/system/api/records` and compares; `taskworker/agent.py` only reports success when it passes. |
| Approval gate works | Run without `--auto-approve`; the run pauses at `browser_submit`. Or run `test_supervised_deny_blocks` in the test suite. |
| LLM brain exists and falls back | `taskworker/brain/llm_brain.py` + the fallback in `agent.py` (`_fallback_brain`). Run with `--brain llm` and no key: the run still succeeds via fallback and the report says so. |
| Two browser backends | `taskworker/tools/browser.py`: Playwright when available, HTTP fallback otherwise; the stub-server end-to-end check exercised both. |
| Tests | `python -m unittest discover -s tests -v` — 23 tests, including end-to-end. |
| Requirement-by-requirement map | `TECHNICAL_DOCS.md`, section 2. |
| Architecture | `ARCHITECTURE.md` (short version) and `TECHNICAL_DOCS.md` (full version). |
| Demo video | `demo/taskworker-demo.mp4` (85 s, narrated, real screenshots). |

**Assumptions made while building:** the evaluator runs the mock company
locally; "Company X" in the statement is a placeholder (the demo uses
"Acme Supplies Ltd"); the internal system is a web form plus a JSON API,
and entering data means submitting that form (or the equivalent API call
as the fallback route); no real company credentials are used anywhere.
