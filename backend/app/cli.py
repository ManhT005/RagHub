"""Installation commands. Passwords are accepted through a prompt or stdin, never argv."""

import argparse
import asyncio
import getpass
import json
import sys


async def run_bootstrap(args) -> int:
    import app.models  # noqa: F401
    from app.core.database import SessionFactory, engine
    from app.infrastructure.persistence.bootstrap import BootstrapOwnerInput, bootstrap_owner

    try:
        if args.stdin_json:
            payload = BootstrapOwnerInput.model_validate_json(sys.stdin.read())
        else:
            if not args.email:
                raise ValueError("Provide --email or --stdin-json.")
            password = getpass.getpass("Owner password (12+ characters): ")
            if password != getpass.getpass("Confirm password: "):
                raise ValueError("Passwords do not match.")
            payload = BootstrapOwnerInput(email=args.email, password=password)
        async with SessionFactory() as session:
            result = await bootstrap_owner(session, payload)
        print(json.dumps(result))
        return 0
    except ValueError:
        print(
            "Bootstrap rejected. Check input and existing owner; no changes committed.",
            file=sys.stderr,
        )
        return 1
    except Exception:
        print("Bootstrap failed. Check database connectivity and migrations.", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    bootstrap = commands.add_parser("bootstrap-owner", help="Create the installation owner")
    bootstrap.add_argument("--email")
    bootstrap.add_argument(
        "--stdin-json", action="store_true", help="Read credentials JSON on stdin"
    )
    args = parser.parse_args()
    return asyncio.run(run_bootstrap(args))


if __name__ == "__main__":
    raise SystemExit(main())
