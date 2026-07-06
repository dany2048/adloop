# Container image for AdLoop — for container hosts (Fly.io / Railway / Alibaba Function Compute custom container).
# Base already ships Chromium + all its system libs, which is the usual deploy headache. Version-pinned to requirements.txt's playwright floor.
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install chromium

COPY . .

# Container hosts inject $PORT; default 8080 for local `docker run`.
ENV PORT=8080
EXPOSE 8080

# Shell form so $PORT expands at runtime.
CMD uvicorn app.server:app --host 0.0.0.0 --port ${PORT} --workers 1
