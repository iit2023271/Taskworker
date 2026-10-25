# Demo task — invoice processing

## The task (as given to the agent, word for word)

```
Find the latest invoice from Acme Supplies Ltd, extract the amount and due
date, enter it into our internal system, and tell me once it is done.
```

## Setup

```bash
python -m taskworker mock          # terminal 1: mock company on :5000
```

## Run (offline planner — no API key)

```bash
python -m taskworker run "Find the latest invoice from Acme Supplies Ltd, \
  extract the amount and due date, enter it into our internal system, \
  and tell me once it is done." --brain rule --auto-approve
```

With the LLM brain:

```bash
export OPENAI_API_KEY=sk-...
python -m taskworker run "<same task>" --brain llm
```

Supervised (asks before submitting the record):

```bash
python -m taskworker run "<same task>" --brain rule
```

## Expected outcome

- `Outcome: SUCCESS`, 11 steps, verification passed.
- The internal system gains exactly one record:
  `Acme Supplies Ltd / INV-2026-1042 / 4850.0 / 2026-11-19`.
- Evidence in `runs/<run_id>/`: `transcript.json`, `summary.md`,
  4 screenshots, the downloaded invoice PDF.

## Why this task is a real test

- **Selection, not just retrieval.** The inbox has a *newer* invoice from
  Globex Corp (2026-10-22) and an *older* Acme invoice (INV-2026-1031).
  Picking the wrong one fails verification.
- **The document is the source of truth.** The email body mentions the
  figures, but the agent reads the attached PDF and uses its values.
- **A real write with a real check.** The record is submitted through the
  browser form, then verified by re-reading the system — not by trusting
  the submit button.
- **A decision point.** In supervised mode the run pauses for approval
  before the write; answering "n" makes the agent replan instead of
  crashing.

## Reset between runs

```bash
curl -X POST http://127.0.0.1:5000/system/api/reset
```
