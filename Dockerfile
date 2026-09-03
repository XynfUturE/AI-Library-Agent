# ============================================================
# AI Library Agent - Production Image
# ============================================================

FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies (layer cached unless requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

EXPOSE 8000

# Zeabur / other PaaS inject the PORT env var; fall back to 8000 locally.
CMD ["sh", "-c", "uvicorn web.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
