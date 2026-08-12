from pathlib import Path
import sys

# Add project root (Geos-Worker) to Python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.scraper.base import get_html_element
from app.scraper.flood_information import get_enriched_flood_status



if __name__ == "__main__":
    # ! how to use
    selector = "div.basin-hydro-forecast table"
    url = "https://pagasa.dost.gov.ph/flood"

    municipalities_path = "data/phl_admin_level3.geojson"
    basins_path = "data/phl_river_basins.geojson"

    raw = get_html_element(url, selector)
    info = get_enriched_flood_status(raw, municipalities_path, basins_path)
    

    # print(info)