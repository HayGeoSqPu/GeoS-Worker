from pathlib import Path
import sys

# Add project root (Geos-Worker) to Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.scraper.base import get_html_element
from app.scraper.weather_advisory import parse_pagasa_comment_advisory
if __name__ == "__main__":
    # ! how to use
    url = "https://www.pagasa.dost.gov.ph/weather/weather-advisory"
    raw = get_html_element(url, "div.weekly-advisory-content")
    advisory = parse_pagasa_comment_advisory(raw)

    
    # TODO: SCRAPE FOR OTHER PAGE  
    print(advisory)