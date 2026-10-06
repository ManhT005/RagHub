"""Read-only queue/work-item snapshot plus optional JSON telemetry summary. No AI calls."""

import argparse
import asyncio
import json
import math
import re
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kombu import Connection  # noqa: E402
from kombu.exceptions import ChannelError  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.config import get_settings  # noqa: E402
from app.modules.ai_providers.models import EmbeddingWorkItem  # noqa: E402
from app.modules.documents.models import IngestionJob  # noqa: E402
from scripts.run_production_eval import percentile  # noqa: E402

QUEUES = ("celery", "rag-ingestion", "rag-reindex", "rag-embedding", "rag-ocr")
_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")


def summarize_telemetry(lines):
    timings, counters, skipped = defaultdict(list), defaultdict(int), 0
    for line in lines:
        try:
            record = json.loads(line[line.index("{") :])
            if record.get("event") == "stage_timing" and _NAME.fullmatch(record["stage"]):
                elapsed = float(record["duration_ms"])
                if not math.isfinite(elapsed) or elapsed < 0:
                    raise ValueError("Invalid duration")
                timings[record["stage"]].append(elapsed)
            elif record.get("event") == "stage_counter" and _NAME.fullmatch(record["metric"]):
                value = int(record["value"])
                if value < 0:
                    raise ValueError("Invalid counter")
                counters[record["metric"]] += value
            else:
                skipped += 1
        except (ValueError, KeyError, TypeError):
            skipped += 1
    hits, misses = (
        counters.get("embedding_cache_hits", 0),
        counters.get("embedding_cache_misses", 0),
    )
    return {
        "stage_timings": {
            stage: {
                "count": len(values),
                "p50_ms": percentile(values, 0.5),
                "p95_ms": percentile(values, 0.95),
            }
            for stage, values in timings.items()
        },
        "counters": dict(counters),
        "cache_hit_rate": hits / (hits + misses) if hits + misses else None,
        "skipped_records": skipped,
    }


def queue_depths(settings):
    with Connection(
        settings.celery_broker_url,
        transport_options={
            "socket_timeout": 2,
            "socket_connect_timeout": 2,
            "priority_steps": [0, 1, 2, 3, 4, 6, 9],
        },
    ) as connection:
        result = {}
        for queue in QUEUES:
            with connection.channel() as channel:
                try:
                    result[queue] = channel.queue_declare(queue=queue, passive=True).message_count
                except ChannelError as error:
                    if str(error.reply_code) != "404":
                        raise
                    result[queue] = 0  # No queue has been declared yet: there is no backlog.
        return result


async def capture(settings):
    report = {
        "version": 1,
        "mode": "operations-diagnostic",
        "created_at": datetime.now(UTC).isoformat(),
        "hardware_profile": settings.rag_hardware_profile,
        "worker_concurrency": settings.rag_worker_concurrency,
        "issues": [],
    }
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with AsyncSession(engine) as session:
            for label, column in (
                ("work_item_states", EmbeddingWorkItem.state),
                ("ingestion_stages", IngestionJob.stage),
            ):
                rows = await session.execute(select(column, func.count()).group_by(column))
                report[label] = {str(state): count for state, count in rows}
    except Exception as exc:
        report["issues"].append("database:" + type(exc).__name__)
    finally:
        await engine.dispose()
    try:
        report["queue_depths"] = await asyncio.to_thread(queue_depths, settings)
    except Exception as exc:
        report["issues"].append("broker:" + type(exc).__name__)
        report["queue_depths"] = None
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--telemetry", type=Path, help="Saved JSON telemetry log, if enabled")
    parser.add_argument(
        "--strict-infrastructure",
        action="store_true",
        help="Opt in to failure on missing DB/broker",
    )
    args = parser.parse_args()
    report = asyncio.run(capture(get_settings()))
    if args.telemetry:
        with args.telemetry.open(encoding="utf-8") as lines:
            report["telemetry"] = summarize_telemetry(lines)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "mode": report["mode"],
                "queue_depths": report["queue_depths"],
                "issues": report["issues"],
            }
        )
    )
    if args.strict_infrastructure and report["issues"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
