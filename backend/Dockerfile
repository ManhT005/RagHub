FROM python:3.12.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system raghub && adduser --system --ingroup raghub raghub

COPY requirements.lock pyproject.toml ./
RUN python -m pip install --upgrade pip==25.2 \
    && python -m pip install -r requirements.lock

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

USER raghub

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
