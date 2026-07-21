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


def _cmd_run_tailor(args: argparse.Namespace) -> None:
    from jobapply.agents.tailor import run_tailor

    stats = run_tailor(job_id=args.job_id)
    print(f"Tailor run complete: {stats}")


def _cmd_run_applier(args: argparse.Namespace) -> None:
    from jobapply.agents.applier import run_applier

    stats = run_applier(job_id=args.job_id)
    print(f"Applier run complete: {stats}")


def _cmd_run_gap_analysis(_args: argparse.Namespace) -> None:
    from jobapply.agents.gap_advisor import run_gap_analysis

    stats = run_gap_analysis(trigger="manual")
    print(f"Gap analysis complete: {stats}")


def _cmd_list_users(_args: argparse.Namespace) -> None:
    from jobapply.web.auth import list_users

    users = list_users()
    if not users:
        print("No users yet - complete /setup in the browser first.")
        return
    for u in users:
        print(f"id={u['id']}  email={u['email']}  name={u['display_name']}  created={u['created_at']}")


def _cmd_reset_password(args: argparse.Namespace) -> None:
    import getpass

    from jobapply.web.auth import get_user_id_by_email, update_password

    user_id = get_user_id_by_email(args.email)
    if user_id is None:
        print(f"No user found with email {args.email!r}. Run `jobapply list-users` to see existing accounts.")
        raise SystemExit(1)

    password = getpass.getpass("New password: ")
    confirm = getpass.getpass("Confirm new password: ")
    if password != confirm:
        print("Passwords didn't match - nothing changed.")
        raise SystemExit(1)
    if len(password) < 8:
        print("Password must be at least 8 characters - nothing changed.")
        raise SystemExit(1)

    update_password(user_id, password)
    print(f"Password updated for {args.email}. You can log in now.")


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

    tailor_parser = subparsers.add_parser("run-tailor", help="Run Agent 2 + 2b once (tailor + audit resumes)")
    tailor_parser.add_argument("--job-id", type=int, default=None, help="Tailor only this job (default: all pending_tailor jobs)")
    tailor_parser.set_defaults(func=_cmd_run_tailor)

    applier_parser = subparsers.add_parser("run-applier", help="Run Agent 3 once (submit approved applications)")
    applier_parser.add_argument("--job-id", type=int, default=None, help="Apply only to this job (default: all approved jobs)")
    applier_parser.set_defaults(func=_cmd_run_applier)

    subparsers.add_parser("run-gap-analysis", help="Run the Gap Advisor once").set_defaults(
        func=_cmd_run_gap_analysis
    )

    subparsers.add_parser("list-users", help="List existing dashboard accounts (email, name)").set_defaults(
        func=_cmd_list_users
    )

    reset_parser = subparsers.add_parser(
        "reset-password", help="Reset a dashboard account's password (run this if you're locked out)"
    )
    reset_parser.add_argument("--email", required=True, help="Email of the account to reset (see `list-users`)")
    reset_parser.set_defaults(func=_cmd_reset_password)

    serve_parser = subparsers.add_parser("serve", help="Run the web dashboard + scheduler")
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--reload", action="store_true")
    serve_parser.set_defaults(func=_cmd_serve)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
