import json
import sys
from pathlib import Path

# Make the `app` package importable from Netlify's function runtime.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.services.pagasa_pipeline import run_pagasa_pipeline  # noqa: E402


def _json_response(status_code: int, payload: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"}
        # "body": json.dumps(payload, default=str),
    }


def handler(event, context):
    """Netlify function entrypoint. POST-only gateway for cron-job.org.

    Triggers the PAGASA scrape + geofence activation pipeline (shared with
    scripts/update_geofences.py and the local FastAPI endpoint).
    """
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    secret = headers.get("x-cron-secret", "")

    if not settings.CRON_SECRET or secret != settings.CRON_SECRET:
        return _json_response(401, {"detail": "Invalid cron secret"})

    query = event.get("queryStringParameters") or {}
    dry_run = str(query.get("dry_run", "")).lower() in ("1", "true", "yes")

    try:
        summary = run_pagasa_pipeline(dry_run=dry_run)
        return _json_response(200, {"status": "ok"})
    except Exception as e:
        return _json_response(500, {"detail": str(e)})