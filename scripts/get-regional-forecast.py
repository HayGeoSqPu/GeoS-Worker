from pathlib import Path
import json
import sys

# Add project root (Geos-Worker) to Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.scraper.base import get_html_element
from app.scraper.regional_forecast import parse_regional_forecast


def run_get_regional_forecast(
    url: str = "https://pagasa.dost.gov.ph/regional-forecast/slprsd",
) -> dict:
    raw = get_html_element(url, "body")
    return parse_regional_forecast(raw)


if __name__ == "__main__":
    forecast = run_get_regional_forecast()
    # print(json.dumps(forecast, indent=2, ensure_ascii=False))