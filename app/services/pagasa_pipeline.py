from typing import Any, Dict, List

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


def scrape_advisory() -> dict:
    """Returns rainfall tiers: {">200 mm": {"rainfall_range", "municipalities", "impact"}, ...}"""
    raw = get_html_element(ADVISORY_URL, "div.weekly-advisory-content")
    return parse_pagasa_comment_advisory(raw)


def scrape_forecast() -> dict:
    """Returns {headline, issued, valid, provinces: [{<name>: {latitude, longitude, outlook}}]}"""
    raw = get_html_element(FORECAST_URL, "body")
    return parse_regional_forecast(raw)


def advisory_locations(tiers: dict) -> List[str]:
    """All municipality/province names mentioned across every rainfall tier."""
    seen: List[str] = []
    for tier in tiers.values():
        for name in tier.get("municipalities", []):
            if name and name not in seen:
                seen.append(name)
    return seen


def forecast_locations(forecast: dict) -> List[str]:
    """All province names in the regional forecast outlook."""
    names: List[str] = []
    for entry in forecast.get("provinces", []):
        for name in entry.keys():
            if name and name not in names:
                names.append(name)
    return names


def location_matches(doc_location: str, target_locations: List[str]) -> bool:
    """Case-insensitive substring match, either direction."""
    if not doc_location:
        return False
    loc = doc_location.lower()
    for target in target_locations:
        t = target.lower()
        if t in loc or loc in t:
            return True
    return False


def doc_location(doc: dict) -> str:
    """Combined 'municipality, province' string for matching."""
    props = (doc.get("geojson") or {}).get("properties") or {}
    municipality = props.get("municipality") or doc.get("municipality") or ""
    province = props.get("province") or doc.get("province") or ""
    return ", ".join(p for p in (municipality, province) if p)


def activate_geofences(collection, geofence_type: str, locations: List[str], dry_run: bool) -> Dict[str, int]:
    """Sets status=true on every doc of `geofence_type` matching `locations`.
    Returns {"scanned": n, "matched": n}."""
    matched = 0
    n_scanned = 0

    for doc in collection.find({"geojson.properties.type": geofence_type}):
        n_scanned += 1
        if not location_matches(doc_location(doc), locations):
            continue
        matched += 1
        if dry_run:
            action = "WOULD activate"
        else:
            action = "activated"
            # Real docs store status in geojson.properties; set top-level too defensively
            update = {"status": True}
            if doc.get("geojson"):
                update["geojson.properties.status"] = True
            collection.update_one({"_id": doc["_id"]}, {"$set": update})
        print(f"[{action}] {doc.get('_id')} type={geofence_type!r} location={doc_location(doc)!r}")

    print(f"scanned {n_scanned} geofence(s) of type={geofence_type!r} -> {matched} matched")
    return {"scanned": n_scanned, "matched": matched}


def run_pagasa_pipeline(dry_run: bool = False) -> Dict[str, Any]:
    """
    Scrapes the PAGASA weather advisory and regional forecast, then activates
    the matching geofences in MongoDB (GEOs.geofences).

    Returns a summary dict for HTTP/CLI consumers.
    """
    from pymongo import MongoClient

    if not settings.MONGODB_URI:
        raise RuntimeError("MONGODB_URI not set in .env")

    print("Scraping PAGASA weather advisory ...")
    tiers = scrape_advisory()
    print(f"  weather advisory: {len(tiers)} rainfall tier(s)")
    for tier in tiers.values():
        print(f"    {tier['rainfall_range']}: {len(tier.get('municipalities', []))} location(s)")

    print("Scraping PAGASA regional forecast ...")
    forecast = scrape_forecast()
    provinces = forecast_locations(forecast)
    print(f"  regional forecast: {len(provinces)} province(s)")

    client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=15000)
    collection = client[settings.DATABASE_NAME][GEOFENCES_COLLECTION]

    results: Dict[str, Any] = {
        "advisory_tiers": len(tiers),
        "forecast_provinces": len(provinces),
        "by_type": {},
        "total_activated": 0,
    }
    try:
        # Weather advisory (rainfall tiers, flood/landslide impacts) -> both hazard types
        for geofence_type in (FLOOD_GEOFENCE_TYPE, LANDSLIDE_GEOFENCE_TYPE):
            res = activate_geofences(collection, geofence_type, advisory_locations(tiers), dry_run)
            results["by_type"][f"advisory:{geofence_type}"] = res
            results["total_activated"] += res["matched"]
        # Regional forecast (daily outlook per province) -> flood-prone zones
        res = activate_geofences(collection, FLOOD_GEOFENCE_TYPE, provinces, dry_run)
        results["by_type"][f"forecast:{FLOOD_GEOFENCE_TYPE}"] = res
        results["total_activated"] += res["matched"]

        print(f"TOTAL {'WOULD activate' if dry_run else 'activated'}: {results['total_activated']} geofence(s)")
        return results
    finally:
        client.close()