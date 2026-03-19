FROM node:20-alpine AS frontend-build
WORKDIR /frontend
COPY apex/frontend/package.json apex/frontend/package-lock.json* ./
RUN npm ci --no-audit
COPY apex/frontend/ ./
RUN npm run build

FROM python:3.11-slim AS runtime
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY apex/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY apex ./apex
COPY --from=frontend-build /frontend/dist ./apex/frontend_dist

RUN mkdir -p /app/uploads /app/data

ENV DATABASE_URL=sqlite:///./data/apex.db
ENV UPLOAD_DIR=/app/uploads
ENV FRONTEND_DIST_DIR=/app/apex/frontend_dist

EXPOSE 8000

CMD ["sh", "-c", "uvicorn apex.backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
