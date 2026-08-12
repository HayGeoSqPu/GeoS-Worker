from pathlib import Path
import json
import sys

# Add project root (Geos-Worker) to Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.scraper.base import get_html_element
from app.scraper.weather_advisory import parse_pagasa_comment_advisory


def run_get_weather_advisory(
    url: str = "https://www.pagasa.dost.gov.ph/weather/weather-advisory",
) -> dict:
    raw = get_html_element(url, "div.weekly-advisory-content")
    return parse_pagasa_comment_advisory(raw)


if __name__ == "__main__":
    advisory = run_get_weather_advisory()
    print(json.dumps(advisory, indent=2, ensure_ascii=False))