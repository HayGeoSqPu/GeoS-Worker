from pathlib import Path
import json
import sys

# Add project root (Geos-Worker) to Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.scraper.base import get_html_element
from app.scraper.regional_forecast import  parse_regional_forecast

if __name__ == "__main__":
    # ! how to use
    url = "https://pagasa.dost.gov.ph/regional-forecast/slprsd"

    # selector = 'a[href*=\"regional_forecast.pdf\"]'
    # Replace the multi-line selector string with any option above
    selector = 'a[href*="regional_forecast.pdf"]'

    raw = get_html_element(url, "body")
    forecast = parse_regional_forecast(raw)   # <-- pass the page HTML, not a PDF URL

    with open("something.txt", "w+", encoding="utf-8") as f:
        f.write(json.dumps(forecast, indent=2, ensure_ascii=False))