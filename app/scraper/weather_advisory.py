from bs4 import BeautifulSoup, Comment

from typing import List, Any, Dict, TypedDict, Optional
import re

# todo: potential to scrape 
# * <div class="weekly-content-adv"></div> => https://www.pagasa.dost.gov.ph/weather/weather-advisory
# * contains municipalitied which are included in a rainfall advisory 

class GeofenceProperties(TypedDict, total=False):
    name: str
    description: str
    type: str
    status: bool
    color: str
    # Added these based on your requirements
    province: str
    municipality: str


class GeofenceGeometry(TypedDict, total=False):
    type: str
    coordinates: List[Any]

class GeoJSON(TypedDict, total=False):
    type: str
    geometry: GeofenceGeometry
    properties: GeofenceProperties

class GeofenceDoc(TypedDict, total=False):
    user_id: str
    fence_id: str
    geojson: GeoJSON



# @dataclass
class RainfallTier(TypedDict, total=False):
    rainfall_range: str          # e.g. ">200 mm", "100 – 200 mm"
    municipalities: List[str]    # union of provinces across Today/Tomorrow/Day3
    impact: str                  # PAGASA's standard impact statement for this tier


def match_geofences_with_alerts(headlines : List[str], geofences : List[GeofenceDoc]) -> List[Dict[str, Any]]:
    """
    Compares geofence locations against scraped PAGASA headlines.
    Performs case-insensitive keyword matching.
    """
    matched_alerts : List[Dict[str, Any]] = []

    for alert in headlines:
        alert_lower = alert.lower()

        for gf in geofences:
            # Safely navigate nested GeoJSON properties
            geojson = gf.get("geojson") or {}
            properties = geojson.get("properties") or {}

            # Look inside geojson.properties first, then fall back to top-level
            province = properties.get("province") or gf.get("province") or ""
            municipality = properties.get("municipality") or gf.get("municipality") or ""

            province_lower = province.lower()
            municipality_lower = municipality.lower()

            # Check if province or municipality is mentioned in the alert text
            has_province_match = bool(province_lower and province_lower in alert_lower)
            has_municipality_match = bool(
                municipality_lower and municipality_lower in alert_lower
            )

            if has_province_match or has_municipality_match:
                matched_alerts.append(
                    {
                        "geofence_id": gf.get("id") or gf.get("fence_id"),
                        "matched_location": municipality or province,
                        "headline": alert,
                    }
                )

    return matched_alerts


# ! Simulated Geofence DB records 
# ! no clue, have no acess to mongodb
sample_geofences: List[GeofenceDoc] = [
        {
            "user_id": "50f4ba94-908c-44cf-981c-4545485595e7",
            "fence_id": "4a5d825a-7e53-42ae-ac06-43f539469aa8",
            "geojson": {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [] # Truncated for readability
                },
                "properties": {
                    "name": "Naga City Flood Zone",
                    "description": "asfsfsdafds",
                    "type": "Flood prone",
                    "status": True,
                    "color": "#2c5a82",
                    # Appended these to simulate what Pete's DB has
                    "province": "Camarines Sur",
                    "municipality": "Naga City" 
                }
            }
        }
    ]


# Header/noise words that can leak into a location list when they sit
# next to it in the flattened text (table headers, day labels, etc).
HEADER_NOISE = {
    "today",
    "tomorrow",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "forecast",
    "rainfall",
    "potential",
    "impacts",
}

# ! =================== where to put this ================
# PAGASA's advisory table has no real <table> markup -- it's one <p> with
# runs of whitespace standing in for column breaks. This bracket is the
# only reliable delimiter between severity tiers.
SEVERITY_PATTERN = re.compile(r"\(([^)]*?mm)\)", re.IGNORECASE)

# The three impact tiers PAGASA reuses verbatim across advisories. Used to
# split "which provinces" text from "what happens" text within a tier.
IMPACT_LEAD_WORDS = r"(?:Widespread|Numerous|Localized|Isolated)"
IMPACT_PATTERN = re.compile(rf"{IMPACT_LEAD_WORDS}[^.]*\.(?:\s*[^.]*\.)?")

# Known PH provinces/regions, longest-name-first so "Ilocos Norte" is
# matched before "Ilocos". Used only to re-insert a delimiter between two
# province names that got glued together across day-columns (see notes).
PH_PROVINCES = sorted(
    [
        "Metro Manila", "Ilocos Norte", "Ilocos Sur", "La Union", "Pangasinan",
        "Batanes", "Cagayan", "Isabela", "Nueva Vizcaya", "Quirino", "Aurora",
        "Bataan", "Bulacan", "Nueva Ecija", "Pampanga", "Tarlac", "Zambales",
        "Batangas", "Cavite", "Laguna", "Quezon", "Rizal", "Marinduque",
        "Occidental Mindoro", "Oriental Mindoro", "Palawan", "Romblon",
        "Albay", "Camarines Norte", "Camarines Sur", "Catanduanes", "Masbate",
        "Sorsogon", "Aklan", "Antique", "Capiz", "Guimaras", "Iloilo",
        "Negros Occidental", "Bohol", "Cebu", "Negros Oriental", "Siquijor",
        "Biliran", "Eastern Samar", "Leyte", "Northern Samar", "Samar",
        "Southern Leyte", "Zamboanga del Norte", "Zamboanga del Sur",
        "Zamboanga Sibugay", "Bukidnon", "Camiguin", "Lanao del Norte",
        "Misamis Occidental", "Misamis Oriental", "Davao de Oro",
        "Davao del Norte", "Davao del Sur", "Davao Occidental",
        "Davao Oriental", "Cotabato", "Sarangani", "South Cotabato",
        "Sultan Kudarat", "Basilan", "Lanao del Sur",
        "Maguindanao del Norte", "Maguindanao del Sur", "Sulu", "Tawi-Tawi",
        "Abra", "Apayao", "Benguet", "Ifugao", "Kalinga", "Mountain Province",
        "Baguio",
    ],
    key=len,
    reverse=True,
)
_PROVINCE_PATTERN = re.compile(
    r"(?<!,\s)\b(" + "|".join(re.escape(p) for p in PH_PROVINCES) + r")\b"
)

def _extract_advisory_text(html_content: str) -> Optional[str]:
    """
        Pull the raw advisory paragraph out of PAGASA's commented-out block.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    comment = soup.find(string=lambda t: isinstance(t, Comment))
    inner = BeautifulSoup(str(comment), "html.parser") if comment else soup

    paragraph = inner.find("p")
    text = paragraph.get_text(" ", strip=True) if paragraph else inner.get_text(" ", strip=True)
    if not text:
        return None

    text = text.replace("\xa0", " ").replace("\ufffd", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text

def _split_locations(blob: str) -> List[str]:
    """Turn a comma/'and'-joined, day-column-concatenated blob into a
    deduped list of place names, in first-seen order."""
    blob = blob.strip(" -\u2013\u2014")
    if not blob:
        return []

    # "X and Y" -> "X, Y"
    blob = re.sub(r"\s+and\s+", ", ", blob)
    # Re-insert a delimiter where one day-column's list runs straight into
    # the next with no comma (e.g. "...Oriental Mindoro La Union...").
    blob = _PROVINCE_PATTERN.sub(r", \1", blob)

    seen: List[str] = []
    for part in blob.split(","):
        part = part.strip(" -\u2013\u2014")
        if not part or part.lower() in HEADER_NOISE:
            continue
        if part not in seen:
            seen.append(part)
    return seen


def parse_pagasa_comment_advisory(html_content: str) -> Dict[str, RainfallTier]:
    """
    Parse a PAGASA heavy-rainfall advisory embedded as an HTML comment
    (see weekly-content-adv on the PAGASA site) into one entry per
    rainfall-severity bracket.

    Returns a dict keyed by the raw rainfall range string (e.g. ">200 mm"),
    each holding the deduped municipalities/provinces mentioned for that
    bracket (across all forecast days -- see caveat below) and PAGASA's
    impact statement for that tier.

    Note: deviates from Dict[str, List[str]] on purpose -- collapsing
    severity + rainfall + impact text into a flat list of strings would
    throw away which piece is which. The rainfall range is still the dict
    key, matching your original intent.
    """
    text = _extract_advisory_text(html_content)
    if not text:
        return {}

    matches = list(SEVERITY_PATTERN.finditer(text))
    result: Dict[str, RainfallTier] = {}

    for i, match in enumerate(matches):
        rainfall_range = re.sub(r"\s+", " ", match.group(1)).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        segment = text[start:end].strip()

        impact_match = IMPACT_PATTERN.search(segment)
        if impact_match:
            impact = impact_match.group(0).strip()
            locations_blob = segment[: impact_match.start()]
        else:
            impact = ""
            locations_blob = segment

        result[rainfall_range] = RainfallTier(
            rainfall_range=rainfall_range,
            municipalities=_split_locations(locations_blob),
            impact=impact,
        )

    return result





    