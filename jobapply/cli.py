from __future__ import annotations

import argparse
import logging


def _cmd_migrate(_args: argparse.Namespace) -> None:
    from jobapply.db.migrate import run_migrations

    applied = run_migrations()
    print(f"Applied migrations: {applied or '(none pending)'}")


def _cmd_run_finder(_args: argparse.Namespace) -> None:
    from jobapply.agents.finder import run_finder

    stats = run_finder()
    print(f"Finder run complete: {stats}")


def _cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run("jobapply.web.main:app", host=args.host, port=args.port, reload=args.reload)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(prog="jobapply")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("migrate", help="Apply pending DB migrations").set_defaults(func=_cmd_migrate)
    subparsers.add_parser("run-finder", help="Run Agent 1 once (find + score jobs)").set_defaults(
        func=_cmd_run_finder
    )

    serve_parser = subparsers.add_parser("serve", help="Run the web dashboard + scheduler")
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--reload", action="store_true")
    serve_parser.set_defaults(func=_cmd_serve)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
