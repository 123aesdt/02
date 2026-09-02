FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN pip install --no-cache-dir .
RUN rm -f pyproject.toml

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
