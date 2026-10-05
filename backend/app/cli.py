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


async def run_index_gc(args) -> int:
    from sqlalchemy import select

    import app.models  # noqa: F401
    from app.core.config import get_settings
    from app.core.database import SessionFactory, engine
    from app.infrastructure.elasticsearch.gc_inventory import (
        acquire_redis_lock,
        load_candidates,
        make_context,
        record_audit,
        release_redis_lock,
    )
    from app.infrastructure.elasticsearch.gc_runner import GcRunner
    from app.infrastructure.telemetry.correlation import use_correlation_id

    settings = get_settings()
    apply = bool(args.apply)
    if apply and not settings.rag_index_gc_enabled:
        print("Refusing apply: RAG_INDEX_GC_ENABLED is off (dry-run only).", file=sys.stderr)
        return 2
    correlation_id = use_correlation_id()
    _, es, redis = make_context()
    try:
        async with SessionFactory() as session:
            from app.modules.ai_providers.models import EmbeddingIndexVersion

            async def recheck(index_name):
                version = (
                    await session.scalars(
                        select(EmbeddingIndexVersion).where(
                            EmbeddingIndexVersion.index_name == index_name
                        )
                    )
                ).one_or_none()
                if version is None:
                    return None
                from app.infrastructure.elasticsearch.gc import IndexCandidate
                from app.modules.workspaces.models import Workspace

                workspace = await session.get(Workspace, version.workspace_id)
                return IndexCandidate(
                    index_name=index_name,
                    version_id=str(version.id),
                    workspace_id=str(version.workspace_id),
                    state=version.status,
                    age_hours=None,
                    active=workspace is not None
                    and workspace.active_embedding_index_version_id == version.id,
                    pending_or_running=workspace is not None
                    and workspace.pending_embedding_index_version_id == version.id,
                )

            async def delete_index(index_name: str) -> None:
                es.indices.delete(index=index_name)

            async def record(report, correlation, pairs) -> None:
                await record_audit(
                    session, mode=report.mode, correlation_id=correlation,
                    report=report, pairs=pairs,
                )

            runner = GcRunner(
                load_candidates=lambda: load_candidates(session, es),
                delete_index=delete_index,
                recheck=recheck,
                record_run=record,
                acquire_lock=lambda: acquire_redis_lock(redis),
                release_lock=lambda: release_redis_lock(redis),
            )
            report = await runner.run(apply=apply, correlation_id=correlation_id)
        print(json.dumps({
            "mode": report.mode,
            "candidates": report.candidates,
            "kept": report.kept,
            "deleted": report.deleted,
            "reported": report.reported,
            "errors": report.errors,
            "decisions": [{"index": d.index_name, "decision": d.decision, "reason": d.reason}
                          for d in report.decisions],
        }, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"Index GC failed: {exc}", file=sys.stderr)
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
    gc_parser = commands.add_parser("index-gc", help="Versioned index garbage collection")
    gc_parser.add_argument("--apply", action="store_true", help="Delete; default is dry-run")
    args = parser.parse_args()
    if args.command == "index-gc":
        return asyncio.run(run_index_gc(args))
    return asyncio.run(run_bootstrap(args))


if __name__ == "__main__":
    raise SystemExit(main())
