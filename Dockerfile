# ── Stage 1: Build React Frontend ─────────────────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm install

COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python Backend Runtime ──────────────────────
FROM python:3.11-slim
WORKDIR /app

# Install curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/app/ ./app/

# Copy compiled frontend from Stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Persistent directory for SQLite and OAuth credentials
ENV DATA_DIR=/app/data
ENV DATABASE_URL=sqlite:////app/data/job_tracker.db
ENV GMAIL_TOKEN_PATH=/app/data/token.json
ENV GMAIL_CREDENTIALS_PATH=/app/data/credentials.json
RUN mkdir -p /app/data

# Default port
ENV PORT=8000
EXPOSE 8000

# Run FastAPI with Uvicorn
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
