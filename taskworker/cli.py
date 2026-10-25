"""CLI for TaskWorker.

    python -m taskworker mock [--port 5000]   start the mock company app
    python -m taskworker seed                 regenerate seed data
    python -m taskworker run "TASK" [--brain auto|llm|rule]
        [--auto-approve] [--mock-url URL] [--max-steps N] [--run-dir DIR]
"""

from __future__ import annotations

import argparse
import os
import sys

from .agent import Agent


def _mock_port(args) -> int:
    return int(os.environ.get("MOCK_PORT", args.port))


def cmd_mock(args) -> int:
    # The mock app exposes either a create_app() factory (SPEC) or a
    # module-level Flask `app` (current implementation) — accept either.
    try:
        from mock_company.app import create_app
        app = create_app()
    except (ImportError, AttributeError):
        try:
            from mock_company import app as mock_app_module
            app = mock_app_module.app
        except (ImportError, AttributeError) as e:
            print(f"mock company app is not available: {e}", file=sys.stderr)
            return 1
    port = _mock_port(args)
    print(f"Mock company app at http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)
    return 0


def cmd_seed(_args) -> int:
    try:
        from mock_company.seed import main as seed_main
    except ImportError as e:
        print(f"seed module is not available: {e}", file=sys.stderr)
        return 1
    seed_main()
    print("Seed data regenerated.")
    return 0


def cmd_run(args) -> int:
    mock_url = args.mock_url or os.environ.get(
        "MOCK_URL", "http://127.0.0.1:5000")
    agent = Agent(
        goal=args.task,
        mock_url=mock_url,
        max_steps=args.max_steps,
        auto_approve=args.auto_approve,
        run_dir=args.run_dir,
        brain_choice=args.brain,
    )
    print(f"Goal: {args.task}")
    print(f"Brain: {agent.brain.name}  |  Mock: {mock_url}  |  "
          f"Run dir: {agent.run_dir}")
    result = agent.run()
    print()
    print(f"Outcome: {'SUCCESS' if result['success'] else 'NOT COMPLETED'}")
    print(f"Summary: {result['summary']}")
    print(f"Verification: passed={result['verification'].get('passed')} — "
          f"{result['verification'].get('detail')}")
    print(f"Steps: {result['steps']}  |  Report: {result['run_dir']}")
    return 0 if result["success"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="taskworker",
        description="Autonomous AI task worker (prototype).")
    sub = parser.add_subparsers(dest="command")

    mock_p = sub.add_parser("mock", help="start the mock company app")
    mock_p.add_argument("--port", type=int, default=5000)
    mock_p.set_defaults(func=cmd_mock)

    seed_p = sub.add_parser("seed", help="regenerate seed data")
    seed_p.set_defaults(func=cmd_seed)

    run_p = sub.add_parser("run", help="run the agent on a task")
    run_p.add_argument("task", help="natural-language task")
    run_p.add_argument("--brain", choices=["auto", "llm", "rule"],
                       default="auto",
                       help="brain to use (default: auto = LLM if a key "
                            "is set, else the offline planner)")
    run_p.add_argument("--auto-approve", action="store_true",
                       help="approve write actions without asking")
    run_p.add_argument("--mock-url", default=None,
                       help="mock company app URL "
                            "(default http://127.0.0.1:5000)")
    run_p.add_argument("--max-steps", type=int, default=30)
    run_p.add_argument("--run-dir", default=None,
                       help="directory for transcript/screenshots "
                            "(default runs/<id>)")
    run_p.set_defaults(func=cmd_run)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
