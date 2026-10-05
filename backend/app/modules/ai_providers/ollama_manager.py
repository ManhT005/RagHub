"""Ollama management stays in the host control plane, never the engine."""

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select

from app.core.exceptions import AppError
from app.modules.ai_providers.control_schemas import ModelInput
from app.modules.ai_providers.control_service import ProviderControlService
from app.modules.ai_providers.models import OllamaModelPull, ProviderConfig, ProviderConnection
from app.modules.ai_providers.schemas import _validate_base_url

ACTIVE_PULLS = {"QUEUED", "PULLING", "VERIFYING"}


def canonical_model(model):
    return model if ":" in model else model + ":latest"


def ollama_connection(connection):
    if connection.provider_type != "OLLAMA":
        raise AppError("OLLAMA_REQUIRED", "This action requires Ollama.", status_code=422)
    if not connection.enabled:
        raise AppError("PROVIDER_DISABLED", "Connection is disabled.", status_code=409)
    return _validate_base_url(connection.base_url).rstrip("/")


class OllamaModelManager:
    def __init__(self, session):
        self.session = session

    async def start(self, organization_id, connection_id, payload):
        connection = await self.session.scalar(
            select(ProviderConnection)
            .where(
                ProviderConnection.id == connection_id,
                ProviderConnection.organization_id == organization_id,
            )
            .with_for_update()
        )
        if connection is None:
            raise AppError("PROVIDER_NOT_FOUND", "Connection not found.", status_code=404)
        ollama_connection(connection)
        active = await self.session.scalar(
            select(OllamaModelPull).where(
                OllamaModelPull.connection_id == connection_id,
                OllamaModelPull.status.in_(ACTIVE_PULLS),
            )
        )
        model = canonical_model(payload.model)
        if active and active.updated_at < datetime.now(UTC) - timedelta(hours=2):
            active.status, active.error_code = "FAILED", "MODEL_PULL_TIMEOUT"
            await self.session.flush()
            active = None
        if active:
            if active.model == model and active.register_after_pull == payload.register_after_pull:
                return active
            raise AppError(
                "MODEL_PULL_IN_PROGRESS", "A model is already downloading.", status_code=409
            )
        job = OllamaModelPull(
            organization_id=organization_id,
            connection_id=connection_id,
            model=model,
            register_after_pull=payload.register_after_pull,
            status="QUEUED",
            total_bytes=0,
            completed_bytes=0,
        )
        self.session.add(job)
        await self.session.commit()
        try:
            from app.infrastructure.task_queue.celery_app import celery_app

            await asyncio.to_thread(
                celery_app.send_task, "providers.ollama_pull", args=[str(job.id)], retry=False
            )
        except Exception:
            job.status, job.error_code = "FAILED", "MODEL_PULL_QUEUE_UNAVAILABLE"
            await self.session.commit()
        await self.session.refresh(job)
        return job

    async def get(self, organization_id, connection_id, job_id):
        job = await self.session.scalar(
            select(OllamaModelPull).where(
                OllamaModelPull.id == job_id,
                OllamaModelPull.organization_id == organization_id,
                OllamaModelPull.connection_id == connection_id,
            )
        )
        if job is None:
            raise AppError("MODEL_PULL_NOT_FOUND", "Pull job not found.", status_code=404)
        if job.status in ACTIVE_PULLS and job.updated_at < datetime.now(UTC) - timedelta(hours=2):
            job.status, job.error_code = "FAILED", "MODEL_PULL_TIMEOUT"
            await self.session.commit()
        return job

    async def run(self, job_id, *, transport=None):
        job = await self.session.get(OllamaModelPull, job_id)
        if job is None or job.status not in ACTIVE_PULLS:
            return
        control = ProviderControlService(self.session)
        try:
            connection = await control.get(job.organization_id, job.connection_id)
            base = ollama_connection(connection)
            job.status, job.error_code = "PULLING", None
            await self.session.commit()
            layers = {}
            last_saved = 0
            success = False
            async with asyncio.timeout(7000):
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(120, connect=10),
                    follow_redirects=False,
                    transport=transport,
                ) as client:
                    async with client.stream(
                        "POST", f"{base}/api/pull", json={"model": job.model, "stream": True}
                    ) as response:
                        if response.status_code != 200:
                            raise AppError("MODEL_PULL_FAILED", "Download failed.", status_code=422)
                        async for line in response.aiter_lines():
                            if not line:
                                continue
                            if len(line) > 65_536:
                                raise ValueError("Oversized progress event")
                            event = json.loads(line)
                            if event.get("error"):
                                raise AppError(
                                    "MODEL_PULL_FAILED", "Download failed.", status_code=422
                                )
                            status = event.get("status", "")
                            digest = event.get("digest")
                            if digest and "total" in event:
                                total = max(0, min(int(event["total"]), 2**63 - 1))
                                completed = max(0, min(int(event.get("completed", 0)), total))
                                layers[digest] = (completed, total)
                                job.completed_bytes = sum(item[0] for item in layers.values())
                                job.total_bytes = sum(item[1] for item in layers.values())
                            if status.startswith("verifying") or status == "success":
                                job.status = "VERIFYING"
                            if time.monotonic() - last_saved >= 1 or status == "success":
                                await self.session.commit()
                                last_saved = time.monotonic()
                            if status == "success":
                                success = True
            if not success:
                raise AppError("MODEL_PULL_FAILED", "Download ended early.", status_code=422)
            installed = await control.discover(job.organization_id, job.connection_id)
            if not any(canonical_model(item.model) == job.model for item in installed):
                raise AppError(
                    "MODEL_PULL_FAILED", "Model is missing after download.", status_code=422
                )
            if job.register_after_pull:
                config = await self.session.scalar(
                    select(ProviderConfig).where(
                        ProviderConfig.connection_id == job.connection_id,
                        ProviderConfig.model == job.model,
                        ProviderConfig.capability == "CHAT",
                    )
                )
                if config:
                    from app.modules.ai_providers.service import ProviderConfigService

                    await ProviderConfigService(self.session).test(job.organization_id, config.id)
                else:
                    config = await control.register(
                        job.organization_id,
                        job.connection_id,
                        ModelInput(model=job.model, capability="CHAT"),
                    )
                job.registered_model_id = config.id
            job.status = "READY"
            job.completed_bytes = job.total_bytes
            await self.session.commit()
        except Exception as exc:
            await self.session.rollback()
            job = await self.session.get(OllamaModelPull, job_id)
            if job is not None:
                job.status = "FAILED"
                job.error_code = (
                    "MODEL_PULL_TIMEOUT" if isinstance(exc, TimeoutError) else "MODEL_PULL_FAILED"
                )
                await self.session.commit()
