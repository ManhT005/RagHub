FROM python:3.14.8-slim-bookworm AS runtime

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

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

USER raghub

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS local-ai

USER root
ARG PYTORCH_VERSION=2.8.0
RUN python -m pip install \
        --index-url https://download.pytorch.org/whl/cpu \
        "torch==${PYTORCH_VERSION}" \
    && python -m pip install sentence-transformers==5.1.1
USER raghub
