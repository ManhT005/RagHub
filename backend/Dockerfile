FROM python:3.12.11-slim-bookworm AS dependencies

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface

WORKDIR /app

RUN addgroup --system raghub && adduser --system --ingroup raghub raghub \
    && mkdir -p /app/.cache/huggingface \
    && chown -R raghub:raghub /app/.cache

COPY requirements.lock pyproject.toml ./
RUN python -m pip install --upgrade pip==25.2 \
    && python -m pip install -r requirements.lock

FROM dependencies AS local-ai-dependencies

COPY requirements-local-ai.lock ./
RUN python -m pip install \
        --index-url https://download.pytorch.org/whl/cpu \
        torch==2.8.0 \
    && python -m pip install -r requirements-local-ai.lock

FROM dependencies AS runtime

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY raghub_core ./raghub_core

USER raghub

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM local-ai-dependencies AS local-ai

COPY --from=runtime /app /app
USER raghub
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
