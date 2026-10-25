# Second demo task — Globex invoice (generalisation check)

## The task (as given to the agent, word for word)

```
Find the latest invoice from Globex Corp, extract the amount and due date, enter it into our internal system, and tell me once it is done.
```

## Why this task

The Acme demo proves the agent can do one task. This one proves it can
generalise: same agent, same tools, no code change, a different vendor —
and Globex has only one invoice in the inbox, so the agent must find it
rather than reusing the Acme answer.

## Setup

```bash
python -m taskworker mock          # terminal 1: mock company on :5000
curl -X POST http://127.0.0.1:5000/system/api/reset   # start with an empty system
```

## Run (offline planner — no API key)

```bash
python -m taskworker run "Find the latest invoice from Globex Corp, extract the amount and due date, enter it into our internal system, and tell me once it is done." --brain rule --auto-approve
```

## Expected outcome

- `Outcome: SUCCESS`, 11 steps, verification passed.
- The internal system gains exactly one record:
  `Globex Corp / INV-G-881 / 1150.0 / 2026-11-21`.
- Evidence in `runs/<run_id>/`: `transcript.json`, `summary.md`,
  4 screenshots, the downloaded invoice PDF (`inv-g-881.pdf`).

## Verified

Run `dea0b98e` on 2026-10-25: SUCCESS, 11 steps, verification passed —
`Entered invoice INV-G-881 from Globex Corp ($1,150.00, due 2026-11-21)
into the internal system and confirmed it is listed there.`
