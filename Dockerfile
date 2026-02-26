FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git curl && rm -rf /var/lib/apt/lists/* && pip install uv

WORKDIR /app

COPY pyproject.toml ./
COPY taskrunner/ ./taskrunner/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY main.py ./

RUN uv pip install --system -e .

EXPOSE 8002

CMD ["uvicorn", "taskrunner.api:app", "--host", "0.0.0.0", "--port", "8002"]
