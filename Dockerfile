# Root Dockerfile — used by Hugging Face Spaces (Docker SDK).
# Base image ships Chromium + all its system libs, so there's no `playwright install` step to fail.
# (For a generic VM deploy, use deploy/setup.sh instead; for other container hosts see deploy/Dockerfile.)
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# SQLite memory store + generated assets live under the app dir (writable).
ENV ADLOOP_DB_PATH=/app/data/adloop.db
RUN mkdir -p /app/data /app/output

# HF routes HTTPS to the port declared as `app_port` in README.md (7860).
EXPOSE 7860
CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
