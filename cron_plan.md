# Plan: HTTP Gateway Endpoint for the Hourly PAGASA Scrape (Netlify + cron-job.org)

> **Status: IMPLEMENTED FOR NETLIFY & LOCALLY TESTED** — pending Netlify deploy + cron-job.org setup (see §7, §8).

## 1. Goal

Expose an HTTP endpoint that runs the same PAGASA scrape → MongoDB geofence-activation pipeline as `scripts/update_geofences.py`. [cron-job.org](https://console.cron-job.org/jobs/create) hits the endpoint every hour; the app is hosted on **Netlify** (Python serverless functions).

```
cron-job.org (every hour)
        │  POST https://<app>.netlify.app/.netlify/functions/cron_activate
        │  (+ X-Cron-Secret header)
        ▼
Netlify -> Python function (functions/cron_activate.py)
        │  runs shared pipeline service
        ▼
  Scrape PAGASA (advisory + regional forecast)  ->  MongoDB GEOs > geofences (activate)
```

## 2. Why a plain function (not the FastAPI app)

Netlify Python functions are single-entrypoint `handler(event, context)` modules — they do **not** serve an ASGI app directly (the `vercel.json`/`api/index.py` FastAPI approach does not transfer). Instead of adding an adapter (e.g. Mangum) and its event-format risk, the Netlify function:

- reuses the **same shared service** (`app/services/pagasa_pipeline.run_pagasa_pipeline`) the FastAPI endpoint and CLI script call,
- re-implements only the tiny auth/wrapper (header check + JSON response), ~30 lines.

The FastAPI endpoint (`POST /api/v1/cron/activate` in `app/api/v1/router.py`) stays for local development/testing.

## 3. Critical constraint: Selenium does not exist on Netlify

`app/scraper/base.py` first tries headless Chrome (Selenium) and falls back to plain HTTP. On Netlify there is **no Chrome binary**. Already handled:

- `base.py` imports Selenium inside `try/except` and honors the `SCRAPE_JS=0` env flag → serverless runs go **straight to the HTTP path** (no wasted Chrome launch attempt). **[DONE]**
- Both parsers work off raw HTTP HTML (verified): the advisory lives in an HTML comment; the regional forecast lives in the server-side `regional` JS object.

## 4. Endpoint design

Netlify function `functions/cron_activate.py`:

| Item | Value |
|---|---|
| URL | `https://<app>.netlify.app/.netlify/functions/cron_activate` |
| Method | `POST` (cron-job.org supports POST) |
| Auth | `X-Cron-Secret` header must equal `CRON_SECRET` env var (401 otherwise). Header lookup is case-insensitive (Netlify lowercases header keys) |
| Query | optional `?dry_run=1` → validates without DB writes |
| Response | `200 {"status": "ok", "advisory_tiers": n, "forecast_provinces": n, "by_type": {...}, "total_activated": n}`; `401` bad secret; `500` on pipeline failure |
| Timeout | Netlify synchronous function max = **26s** (set `timeout = 26` in `netlify.toml`). Pipeline ≈ 2 × 5–10s HTTP scrapes + Mongo write, comfortably inside; risk noted in §10 |

Handler sketch (already implemented):

```python
def handler(event, context):
    secret = {k.lower(): v for k, v in (event.get("headers") or {}).items()}.get("x-cron-secret", "")
    if not settings.CRON_SECRET or secret != settings.CRON_SECRET:
        return {"statusCode": 401, "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"detail": "Invalid cron secret"})}
    dry_run = str((event.get("queryStringParameters") or {}).get("dry_run", "")).lower() in ("1", "true", "yes")
    try:
        summary = run_pagasa_pipeline(dry_run=dry_run)
        return {"statusCode": 200, "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"status": "ok", **summary}, default=str)}
    except Exception as e:
        return {"statusCode": 500, "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"detail": str(e)})}
```

## 5. Shared pipeline service (kept from Vercel plan)

- `app/services/pagasa_pipeline.py` — `run_pagasa_pipeline(dry_run=False) -> dict`; scrapes advisory + regional forecast, matches geofences (types `Flood prone`, `Landslide prone`), activates via nested `geojson.properties.status`. **[DONE]**
- `scripts/update_geofences.py` — thin CLI wrapper over the service (local runs / old Windows Task Scheduler). **[DONE]**
- `app/api/v1/router.py` — local-only FastAPI endpoint, same service. **[DONE]**

## 6. Netlify deployment files

```
netlify.toml            # functions dir, python version, timeout
functions/cron_activate.py  # Netlify handler (see §4)
requirements.txt        # root-level — Netlify auto-installs it for Python functions
app/...                 # existing
```

- `netlify.toml` (implemented):
  ```toml
  [build]
  command = "echo 'no build step needed'"

  [functions]
  directory = "functions"
  python_binary_version = "3.12"
  timeout = 26
  ```
  - Function URL becomes `/.netlify/functions/cron_activate` (directory = "functions").
  - `python_binary_version`: Netlify-supported values include 3.11/3.12/3.13 — 3.12 matches local `.venv`.
  - `timeout = 26` is the synchronous-function maximum on Netlify.
- Dependency install: Netlify reads `requirements.txt` **at the repository root** for Python functions (already fully pinned: fastapi, requests, beautifulsoup4, pymongo, pdfplumber, selenium...). If Netlify fails to pick it up, fallback = copy to `functions/requirements.txt`.

## 7. Environment variables (Netlify UI → Site settings → Environment variables)

Same values as local `.env` (Netlify has no `.env` at runtime; `pydantic-settings` reads real env vars):

- `MONGODB_URI` (Atlas URI from `.env`)
- `DATABASE_NAME` = `GEOs`
- `CRON_SECRET` (already generated in local `.env`; use the same value here and in cron-job.org)
- `SCRAPE_JS` = `0` (skip Selenium, straight to HTTP fallback)
- local-only: `SUPABASE_*`, `GOOGLE_API_KEY`, `PROXIMITY_MAX_RADIUS_M` etc. are ignored by Settings → not needed on Netlify

## 8. Deploy (user does, guided)

1. Optional: remove `vercel.json` + `api/index.py` (Vercel leftovers — safe to delete; already replaced by Netlify files).
2. CLI deploy (recommended; repo is not git-initialized):
   ```powershell
   netlify login
   netlify init        # create/link Netlify site
   netlify deploy --prod
   ```
   CLI picks up `netlify.toml` automatically; functions are bundled in the deploy.
3. Or git-based: push the repo to GitHub → import in Netlify → set build command/root (functions auto-detected via `netlify.toml`).
4. Set the env vars from §7 in the Netlify UI **before** first live test.

## 9. cron-job.org setup (user does, guided)

Console at https://console.cron-job.org/jobs/create:

1. **Job name**: `GEOs PAGASA hourly`
2. **URL**: `https://<your-site>.netlify.app/.netlify/functions/cron_activate`
3. **Method**: `POST`
4. **Headers**: `X-Cron-Secret: <CRON_SECRET value>`
5. **Schedule**: hourly → cron expression `0 * * * *` (or the console's hourly preset)
6. **Enabled**: on; notification settings optional
7. cron-job.org default job timeout (120s) > Netlify 26s → fine
8. Save, then click **Run now** to verify

## 10. Testing

1. Local function smoke test: import `functions/cron_activate.handler` with a fake event + `?dry_run=1` → summary JSON; wrong/missing secret → 401; `SCRAPE_JS=0` path verified. **[DONE]**
2. Local FastAPI: `uvicorn app.main:app` → `POST /api/v1/cron/activate` with header → same summary (sanity check of shared service). **[DONE — 401/200 verified]**
3. `netlify dev` (local emulator) → POST against `http://localhost:8888/.netlify/functions/cron_activate` with `?dry_run=1`.
4. Deploy → POST against the live URL once (dry-run first, then real).
5. cron-job.org → Run now → job log shows 200 + response body.
6. Confirm Mongo: `geojson.properties.status` reflects activation.

## 11. Risks / notes

- **26s sync timeout**: if a scrape is slow, the function may time out (Netlify returns 502 to cron-job.org). Mitigations if it ever bites: split scrapes, cache raw HTML briefly, or move to a Netlify **background function** (15-min limit) — but background functions return immediately, so cron-job.org would need a follow-up poll. Not needed today (pipeline measured well under 26s).
- The Windows Task Scheduler job (`GEOs-PAGASA-Hourly`) still runs locally — duplicate activations are harmless (`update_one` re-sets `status=true`); decide later whether to disable it.
- The old `scripts/get-*-.py` JSON-print scripts remain for debugging.
