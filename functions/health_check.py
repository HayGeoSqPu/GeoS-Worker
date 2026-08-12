import json
import sys
from pathlib import Path

# Make the `app` package importable from Netlify's function runtime.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402


def handler(event, context):
    """Public endpoint to verify the deployment is online. No auth required."""
    db_configured = bool(settings.MONGODB_URI)
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(
            {
                "status": "ok",
                "service": "GEOS-PAGASA-Worker",
                "db_configured": db_configured,
            }
        ),
    }