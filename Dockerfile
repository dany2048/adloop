# Root Dockerfile — used by Hugging Face Spaces (Docker SDK).
# Base image ships Chromium + all its system libs. requirements pins playwright==1.44.0 to
# match this image; we still run `playwright install chromium` so the browser binary is
# guaranteed present regardless of the resolved patch version.
# (For a generic VM deploy, use deploy/setup.sh instead; for other container hosts see deploy/Dockerfile.)
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ensure the Chromium build matching the installed Playwright is present (the base image's
# pre-bundled browser can drift from the pip-resolved Playwright).
RUN python -m playwright install chromium

# Pre-fetch the rembg background-removal model at build time so the first product
# composite on a live Space doesn't stall on a ~176MB download (best-effort; runtime
# falls back to on-demand download if this is skipped).
RUN python -c "from rembg import new_session; new_session('u2net')" || echo "u2net predownload skipped"

COPY . .

# SQLite memory store + generated assets live under the app dir (writable).
ENV ADLOOP_DB_PATH=/app/data/adloop.db
RUN mkdir -p /app/data /app/output

# HF routes HTTPS to the port declared as `app_port` in README.md (7860).
EXPOSE 7860
CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
