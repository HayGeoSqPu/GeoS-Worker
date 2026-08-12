# Plan: PAGASA Scrape → MongoDB Geofence Activation (Render + cron-job.org)

## 1. Architecture

```
cron-job.org (every hour, 0 * * * *)
        │  POST https://geos-worker.onrender.com/api/v1/cron/activate
        │  Header: X-Cron-Secret: <CRON_SECRET>
        ▼
Render Web Service (FastAPI)
        │  runs pagasa_pipeline.run_pagasa_pipeline(dry_run=False)
        ▼
  MongoDB Atlas (GEOs > geofences) → activate matching geofences
```

| Component | Render Service | Notes |
|---|---|---|
| **Web API** | Web Service (Python) | `uvicorn app.main:app` — serves `/health`, `GET /api/v1/cron/activate` (public dry-run), `POST /api/v1/cron/activate` (auth) |
| **MongoDB** | External (Atlas) | `MONGODB_URI`, `DATABASE_NAME=GEOs` in env vars |
| **Schedule** | cron-job.org | Hits `POST /api/v1/cron/activate` hourly with `X-Cron-Secret` header |

> **No Render Cron Job needed** — cron-job.org drives the schedule externally.

---

## 2. Endpoints (FastAPI, `app/api/v1/router.py`)

| Route | Method | Auth | Purpose |
|---|---|---|---|
| `/health` | GET | none | Liveness probe |
| `/api/v1/cron/activate` | GET | none | Public dry-run (always `dry_run=true`) for quick browser/curl test |
| `/api/v1/cron/activate` | POST | `X-Cron-Secret` header | Full run (writes to MongoDB) — called by cron-job.org |

Response shape (both):
```json
{
  "status": "ok",
  "advisory_tiers": 3,
  "forecast_provinces": 10,
  "by_type": {
    "advisory:Flood prone": {"scanned": 21, "matched": 0},
    "advisory:Landslide prone": {"scanned": 1, "matched": 0},
    "forecast:Flood prone": {"scanned": 21, "matched": 21}
  },
  "total_activated": 21
}
```

---

## 3. Environment Variables (Render dashboard → each service → Environment)

| Key | Value | Source |
|---|---|---|
| `MONGODB_URI` | `mongodb+srv://...` | `.env` (secret, `sync: false`) |
| `DATABASE_NAME` | `GEOs` | — |
| `CRON_SECRET` | `jQgI4YUXZ1Sp6rCbLAWYXZAqIe-76iYPcEMGt3OZrVI` | `.env` (secret) |
| `SCRAPE_JS` | `0` | disables Selenium (Render has no Chrome) |

---

## 4. Deploy on Render (Blueprint)

Create `render.yaml` at repo root:

```yaml
services:
  - type: web
    name: geos-pagasa-api
    runtime: python
    buildCommand: "pip install -r requirements.txt"
    startCommand: "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
    envVars:
      - key: MONGODB_URI
        sync: false
      - key: DATABASE_NAME
        value: "GEOs"
      - key: CRON_SECRET
        sync: false
      - key: SCRAPE_JS
        value: "0"
    autoDeploy: true
    healthCheckPath: /health
```

Deploy steps:
1. Push this `render.yaml` to GitHub.
2. Render Dashboard → **New → Blueprint** → select repo → Apply.
3. In each created service → **Environment** → add `MONGODB_URI` and `CRON_SECRET` (copy from local `.env`).
4. First deploy → watch build logs (heavy deps: geopandas, pymupdf, selenium; ~3–5 min).
5. Verify:
   - `GET https://geos-worker.onrender.com/health` → `{"status":"ok"}`
   - `GET https://geos-worker.onrender.com/api/v1/cron/activate` → dry-run summary
   - `POST .../api/v1/cron/activate` with `X-Cron-Secret` → live run

---

## 5. cron-job.org Setup

Console: https://console.cron-job.org/jobs/create

| Field | Value |
|---|---|
| **Job name** | `GEOs PAGASA hourly` |
| **URL** | `https://geos-worker.onrender.com/api/v1/cron/activate` |
| **Method** | `POST` |
| **Headers** | `X-Cron-Secret: <CRON_SECRET from .env>` |
| **Schedule** | `0 * * * *` (hourly at minute 0) |
| **Enabled** | ✅ |
| **Timeout** | 120s (cron-job.org default) |

After save → **Run now** → check job log for `200` + JSON response.

---

## 6. Local Testing

```bash
# Start API
uvicorn app.main:app --reload

# Public dry-run (no auth)
curl http://127.0.0.1:8000/api/v1/cron/activate

# Full run (requires secret)
curl -X POST -H "X-Cron-Secret: <CRON_SECRET>" http://127.0.0.1:8000/api/v1/cron/activate
```

---

## 6. Cleanup (done)

Removed Netlify artifacts:
- `netlify.toml`
- `functions/` (cron_activate.py, health_check.py)
- `public/`

All logic now lives in:
- `app/services/pagasa_pipeline.py` (shared pipeline)
- `app/api/v1/router.py` (HTTP routes)
- `scripts/update_geofences.py` (CLI wrapper, unchanged)

---

## 8. Open Items

- `requirements.txt` is heavy (geopandas, pymupdf, selenium, pdfplumber) — first Render build takes ~4 min; subsequent builds cached.
- Render free tier spins down after inactivity → first request after idle may take 30–60s cold start. Acceptable for hourly cron.
- If cold start becomes an issue, upgrade to paid plan or add a keep-alive ping.
- `SCRAPE_JS=0` forces HTTP fallback (no Chrome on Render). Verified locally — pipeline works.