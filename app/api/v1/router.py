from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.core.config import settings
from app.services.pagasa_pipeline import run_pagasa_pipeline

router = APIRouter()


async def verify_cron_secret(x_cron_secret: str = Header(default="")) -> None:
    if not settings.CRON_SECRET or x_cron_secret != settings.CRON_SECRET:
        raise HTTPException(status_code=401, detail="Invalid cron secret")


@router.get(
    "/cron/activate",
    summary="Public health check — no auth, dry-run only",
)
async def cron_activate_public(dry_run: bool = Query(default=True)):
    """Public endpoint for quick health test. Always runs dry-run."""
    summary = run_pagasa_pipeline(dry_run=dry_run)
    return {"status": "ok", **summary}


@router.post(
    "/cron/activate",
    dependencies=[Depends(verify_cron_secret)],
    summary="Run the hourly PAGASA scrape + geofence activation",
)
async def cron_activate(dry_run: bool = Query(default=False, description="Validate matches without writing to MongoDB")):
    """Gateway endpoint for cron-job.org. Scrapes PAGASA (weather advisory +
    regional forecast) and activates matching geofences in MongoDB."""
    summary = run_pagasa_pipeline(dry_run=dry_run)
    return {
        "status": "success",
        "message": "PAGASA pipeline executed successfully",
        "items_processed": len(summary),
    }