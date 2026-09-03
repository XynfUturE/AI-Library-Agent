# ============================================================
# AI Library Agent - Production Image
# ============================================================

FROM python:3.12-slim

# Do not write .pyc files or buffer stdout inside the container.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python dependencies (layer cached unless requirements change)
# PIP_INDEX_URL can point to a PyPI mirror (e.g. a domestic mirror in China).
ARG PIP_INDEX_URL=https://pypi.org/simple
COPY requirements.txt .
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -r requirements.txt

# Copy application source
COPY . .

# Run as a non-root user. SQLite needs write access to the
# database directory at runtime.
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Zeabur / other PaaS inject the PORT env var; fall back to 8000 locally.
CMD ["sh", "-c", "uvicorn web.app:app --host 0.0.0.0 --port ${PORT:-8000}"]

# Lightweight liveness probe using Python's stdlib (no curl in slim).
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${PORT:-8000}/', timeout=3)" || exit 1
