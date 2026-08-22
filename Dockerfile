# Playwright needs a real Chromium install (~300MB with system libs), which
# is why this can't run on the smallest serverless/free-tier platforms --
# it needs a platform that runs a full Docker container (Render does).
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Installs Chromium plus every system library it needs -- must run after
# pip install so the playwright CLI (from the pinned version in
# requirements.txt) is available.
RUN playwright install --with-deps chromium

COPY . .

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# $PORT is set by Render at runtime; 8000 is the local-Docker-run fallback.
CMD gunicorn --workers 2 --threads 4 --timeout 120 --bind 0.0.0.0:${PORT:-8000} webapp.app:app
