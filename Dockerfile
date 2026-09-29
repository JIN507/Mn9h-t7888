# Tahaqqaq — one image for the web app and the background worker.

# ---- stage 1: build the React frontend
FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- stage 2: Python runtime
FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright HF_HOME=/app/.cache/huggingface

RUN apt-get update && apt-get install -y --no-install-recommends \
        libmagic1 ffmpeg libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-ml.txt ./
RUN pip install -r requirements.txt

# Chromium for the TinEye engine (system libraries included)
RUN python -m playwright install --with-deps chromium

# Embedding model runtime (CPU wheels). Build with --build-arg INSTALL_ML=false
# to skip it; the app then verifies with hashes and keypoint geometry only.
ARG INSTALL_ML=true
RUN if [ "$INSTALL_ML" = "true" ]; then \
        pip install torch --index-url https://download.pytorch.org/whl/cpu && \
        pip install "timm>=1.0"; \
    fi

COPY . .
COPY --from=frontend /build/dist ./frontend/dist

RUN mkdir -p uploads user-data static/uploads/audio \
    && useradd --create-home --uid 10001 app \
    && chown -R app:app /app /ms-playwright
USER app

EXPOSE 8000
# SSE progress streams need threads, not sync workers
CMD ["sh", "-c", "flask db upgrade && gunicorn -k gthread -w 2 --threads 8 -t 180 -b 0.0.0.0:8000 app:app"]
