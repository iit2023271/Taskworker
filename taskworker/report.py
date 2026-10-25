"""Run report: transcript.json + summary.md in runs/<run_id>/.
"""

from __future__ import annotations

from pathlib import Path


def write_report(run_dir: str | Path, goal: str, result: dict,
                 memory, approval_log: list | None = None) -> dict:
    """Persist the run's evidence. Returns paths written."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    transcript = run_dir / "transcript.json"
    memory.save(transcript)

    summary_path = run_dir / "summary.md"
    verification = result.get("verification") or {}
    lines = [
        f"# TaskWorker run — {run_dir.name}",
        "",
        f"**Goal:** {goal}",
        "",
        f"**Outcome:** {'SUCCESS' if result.get('success') else 'NOT COMPLETED'}",
        "",
        f"**Summary:** {result.get('summary', '')}",
        "",
        f"**Steps taken:** {result.get('steps', 0)}",
        "",
        f"**Brain:** {result.get('brain', '?')}",
        "",
        f"**Fell back to rule brain:** {result.get('fell_back_to_rule', False)}",
        "",
        "## Verification",
        "",
        f"Passed: {verification.get('passed')}",
        "",
        f"{verification.get('detail', '')}",
        "",
        "## Evidence",
        "",
    ]
    screenshots = sorted((run_dir / "screenshots").glob("*.png")) \
        if (run_dir / "screenshots").exists() else []
    downloads = sorted((run_dir / "downloads").glob("*")) \
        if (run_dir / "downloads").exists() else []
    if screenshots:
        lines.append("Screenshots:")
        for shot in screenshots:
            lines.append(f"- {shot.name}")
    if downloads:
        lines.append("Downloaded files:")
        for item in downloads:
            lines.append(f"- {item.name}")
    if not screenshots and not downloads:
        lines.append("(no screenshots or downloads captured)")
    lines.append("")
    lines.append("## Transcript")
    lines.append("")
    lines.append("Full step-by-step log: transcript.json")
    if approval_log:
        lines.append("")
        lines.append("## Approvals")
        lines.append("")
        for entry in approval_log:
            lines.append(f"- {entry.get('tool')} {entry.get('args')} "
                         f"-> {entry.get('decision')}")
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    return {"transcript": str(transcript), "summary": str(summary_path)}
