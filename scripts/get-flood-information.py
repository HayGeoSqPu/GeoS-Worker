from pathlib import Path
import sys

# Add project root (Geos-Worker) to Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.scraper.base import get_html_element

if __name__ == "__main__":
    # ! how to use
    selector = "div.basin-hydro-forecast table"

    url = "https://pagasa.dost.gov.ph/flood"
    
    raw = get_html_element(url, selector)
    # advisory = parse_pagasa_comment_advisory(raw)
    with open("flood-information.txt", "w+") as f:
        f.write(raw)

    print("done")

    # todo put in mongodb / upsert