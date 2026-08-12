from pathlib import Path
import argparse
import sys

# Add project root (Geos-Worker) to Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.scraper.base import get_html_element
from app.scraper.weather_advisory import parse_pagasa_comment_advisory
from app.scraper.regional_forecast import parse_regional_forecast

# ---------------------------------------------------------------------------
# Type mapping (see plan.md §2): which hazard type each scrape activates.
# Only "Flood prone" and "Landslide prone" exist in the geofences collection.
# ---------------------------------------------------------------------------
FLOOD_GEOFENCE_TYPE = "Flood prone"
LANDSLIDE_GEOFENCE_TYPE = "Landslide prone"

ADVISORY_URL = "https://www.pagasa.dost.gov.ph/weather/weather-advisory"
FORECAST_URL = "https://pagasa.dost.gov.ph/regional-forecast/slprsd"
GEOFENCES_COLLECTION = "geofences"
# ! actual geofences collection name ? (assumed from user schema)


def scrape_advisory() -> dict:
    """Returns rainfall tiers: {">200 mm": {"rainfall_range", "municipalities", "impact"}, ...}"""
    raw = get_html_element(ADVISORY_URL, "div.weekly-advisory-content")
    return parse_pagasa_comment_advisory(raw)


def scrape_forecast() -> dict:
    """Returns {headline, issued, valid, provinces: [{<name>: {latitude, longitude, outlook}}]}"""
    raw = get_html_element(FORECAST_URL, "body")
    return parse_regional_forecast(raw)


def advisory_locations(tiers: dict) -> list:
    """All municipality/province names mentioned across every rainfall tier."""
    seen = []
    for tier in tiers.values():
        for name in tier.get("municipalities", []):
            if name and name not in seen:
                seen.append(name)
    return seen


def forecast_locations(forecast: dict) -> list:
    """All province names in the regional forecast outlook."""
    names = []
    for entry in forecast.get("provinces", []):
        for name in entry.keys():
            if name and name not in names:
                names.append(name)
    return names


def location_matches(doc_location: str, target_locations: list) -> bool:
    """Case-insensitive substring match, either direction."""
    if not doc_location:
        return False
    loc = doc_location.lower()
    for target in target_locations:
        t = target.lower()
        if t in loc or loc in t:
            return True
    return False


def doc_type(doc: dict) -> str:
    """Geofence hazard type, from nested geojson.properties (fallback top-level)."""
    props = (doc.get("geojson") or {}).get("properties") or {}
    return str(props.get("type") or doc.get("type") or "")


def doc_location(doc: dict) -> str:
    """Combined 'municipality, province' string for matching."""
    props = (doc.get("geojson") or {}).get("properties") or {}
    municipality = props.get("municipality") or doc.get("municipality") or ""
    province = props.get("province") or doc.get("province") or ""
    return ", ".join(p for p in (municipality, province) if p)


def activate_geofences(collection, geofence_type: str, locations: list, dry_run: bool) -> int:
    """Sets status=true on every doc of `geofence_type` matching `locations`.
    Returns the number of geofences that would be / were activated."""
    activated = 0
    n_scanned = 0

    for doc in collection.find({"geojson.properties.type": geofence_type}):
        n_scanned += 1
        if not location_matches(doc_location(doc), locations):
            continue
        activated += 1
        if dry_run:
            status = "WOULD activate"
        else:
            status = "activated"
            # Real docs store status in geojson.properties; set top-level too defensively
            update = {"status": True}
            if doc.get("geojson"):
                update["geojson.properties.status"] = True
            collection.update_one({"_id": doc["_id"]}, {"$set": update})
        print(f"[{status}] {doc.get('_id')} type={geofence_type!r} location={doc_location(doc)!r}")

    print(f"scanned {n_scanned} geofence(s) of type={geofence_type!r} -> {activated} matched")
    return activated


def main() -> None:
    parser = argparse.ArgumentParser(description="Hourly PAGASA scrape -> activate GEOs geofences")
    parser.add_argument("--dry-run", action="store_true", help="Print matches without writing to MongoDB")
    args = parser.parse_args()

    if not settings.MONGODB_URI:
        print("MONGODB_URI not set in .env", file=sys.stderr)
        sys.exit(1)

    print("Scraping PAGASA weather advisory ...")
    tiers = scrape_advisory()
    print(f"  weather advisory: {len(tiers)} rainfall tier(s)")
    for tier in tiers.values():
        print(f"    {tier['rainfall_range']}: {len(tier.get('municipalities', []))} location(s)")

    print("Scraping PAGASA regional forecast ...")
    forecast = scrape_forecast()
    provinces = forecast_locations(forecast)
    print(f"  regional forecast: {len(provinces)} province(s)")

    from pymongo import MongoClient

    client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=15000)
    db = client[settings.DATABASE_NAME]
    collection = db[GEOFENCES_COLLECTION]

    try:
        total = 0
        # Weather advisory (rainfall tiers, flood/landslide impacts) -> both hazard types
        total += activate_geofences(collection, FLOOD_GEOFENCE_TYPE, advisory_locations(tiers), args.dry_run)
        total += activate_geofences(collection, LANDSLIDE_GEOFENCE_TYPE, advisory_locations(tiers), args.dry_run)
        # Regional forecast (daily outlook per province) -> flood-prone zones
        total += activate_geofences(collection, FLOOD_GEOFENCE_TYPE, provinces, args.dry_run)
        print(f"TOTAL {'WOULD activate' if args.dry_run else 'activated'}: {total} geofence(s)")
    finally:
        client.close()


if __name__ == "__main__":
    main()