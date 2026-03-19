# APEX Estimating Engine

APEX is a FastAPI + React app for construction estimating workflows, including project tracking, document ingestion, gap analysis, takeoff, labor, estimate review, and variance analysis.

## What's included

- **FastAPI backend** in `apex/backend`
- **Vite + React frontend** in `apex/frontend`
- **Single-container Railway deployment** via the root `Dockerfile`

## Local development

### Backend

```bash
pip install -r apex/backend/requirements.txt
uvicorn apex.backend.main:app --reload
```

### Frontend

```bash
cd apex/frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` to `http://localhost:8000`.

## Deploy to Railway

This repo now includes a root `Dockerfile` and `railway.json` so Railway can deploy the whole app as **one service**:

- the frontend is built during image build
- the FastAPI backend serves the built React app
- Railway health checks hit `/api/health`
- the container listens on Railway's injected `PORT` variable at runtime

### Railway steps

1. Push this repo to GitHub.
2. In Railway, create a **New Project** and choose **Deploy from GitHub Repo**.
3. Select this repository.
4. In the deployed service, add these environment variables:

   - `JWT_SECRET_KEY` = a long random secret
   - `DATABASE_URL` = optional if you want to override the default SQLite path
   - `UPLOAD_DIR` = optional if you want uploads somewhere other than `/app/uploads`
   - `CORS_ORIGINS` = only needed if you plan to call the API from a different origin than the Railway-hosted app

5. Open the service **Settings** tab and click **Generate Domain**.
6. Redeploy once the domain exists if you changed any variables.

### Notes

- The app defaults to SQLite at `./data/apex.db`, which works for demos and light usage.
- For production, Railway volumes are recommended so `/app/data` and `/app/uploads` persist across deployments.
- Because the frontend is served by FastAPI in the same service, you do **not** need a separate frontend Railway service for normal use.
- If you later move to Postgres, update `DATABASE_URL` and add the appropriate driver dependency.

## Health check

`GET /api/health`
