FROM python:3.12-slim

WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH"

RUN pip install --no-cache-dir "uv==0.12.5"
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-editable
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN uv sync --locked --no-dev --no-editable
RUN rm -f pyproject.toml uv.lock

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
