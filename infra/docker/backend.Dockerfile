FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends git libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==0.13.8
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never PATH="/opt/venv/bin:$PATH"
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --group vision --no-dev --no-install-project
COPY backend/src ./src
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./
RUN uv sync --locked --group vision --no-dev --no-editable
# Windows checkouts may contain CRLF. Git still compares their normalized content
# with the pinned commit; genuine source edits continue to fail preflight.
RUN git config --system core.autocrlf true
COPY infra/docker/entrypoint.py /app/entrypoint.py
ENTRYPOINT ["python", "/app/entrypoint.py"]
