FROM python:3.14.4-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir torch==2.12.1 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app
COPY scripts ./scripts
COPY tests ./tests

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]

# The coreference library needs a separate Python/dependency set. No model service.
FROM python:3.14.4-slim AS coreference-runtime
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /usr/local/bin/uv
ENV UV_PYTHON_INSTALL_DIR=/opt/python
COPY scripts/coreference_requirements.txt /tmp/coreference_requirements.txt
RUN uv venv --python 3.11.15 /opt/coreference \
    && uv pip install --python /opt/coreference/bin/python torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu \
    && uv pip install --python /opt/coreference/bin/python -r /tmp/coreference_requirements.txt

FROM app AS coreference-worker
COPY --from=coreference-runtime /opt/python /opt/python
COPY --from=coreference-runtime /opt/coreference /opt/coreference
