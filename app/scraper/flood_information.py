from bs4 import BeautifulSoup
from bs4.element import Tag
from typing import TypedDict
import geopandas as gpd

class BasinEntry(TypedDict):
    name: str
    municipalities: list[str]

EnrichedFloodStatus = dict[str, dict[str, list[BasinEntry]]]


FloodStatus = dict[str, dict[str, list[str]]]

def parse_flood_status(html: str) -> FloodStatus:
    """
    Parses river basin / dam status tables into:
    {
        "Flood Watch": {"river_basin": [...], "dam": [...]},
        "Non-Flood Watch": {"river_basin": [...], "dam": [...]}
    }
    """
    soup = BeautifulSoup(html, "html.parser")
    result: FloodStatus = {}

    # Each <thead>/<tbody> pair is one section, in document order
    # (1st pair = river basins, 2nd pair = dams/reservoirs)
    section_keys = ["river_basin", "dam"]
    tbodies = soup.find_all("tbody")

    for section_key, tbody in zip(section_keys, tbodies):
        for row in tbody.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) != 2:
                continue
            name = cells[0].get_text(strip=True)
            link = cells[1].find("a")
            if not isinstance(link, Tag):
                continue
            status = link.get_text(strip=True)

            result.setdefault(status, {"river_basin": [], "dam": []})
            result[status][section_key].append(name)

    return result


def build_basin_municipality_map(
    municipalities_path: str,
    basins_path: str,
    basin_name_col: str = "basin_name",
    municipality_name_col: str = "adm3_en",
) -> dict[str, list[str]]:
    """
    Spatially joins municipality boundaries against river basin polygons.
    Returns { basin_name: [municipality_names...] }.
    """
    municipalities = gpd.read_file(municipalities_path)                         # pyright: ignore[reportUnknownMemberType]
    basins = gpd.read_file(basins_path)                                         # pyright: ignore[reportUnknownMemberType]

    if basins.crs is None:
        raise ValueError(f"{basins_path} has no CRS defined")

    if municipalities.crs != basins.crs:
        municipalities = municipalities.to_crs(basins.crs)

    joined = gpd.sjoin(municipalities, basins, how="inner", predicate="intersects")

    basin_map: dict[str, list[str]] = {}
    for basin_name, group in joined.groupby(basin_name_col):
        basin_map[str(basin_name)] = sorted(
            group[municipality_name_col].unique().tolist()
        )

    return basin_map


def add_municipalities(
    flood_status: FloodStatus,
    municipalities_path: str,
    basins_path: str,
) -> EnrichedFloodStatus:
    """
    Enriches a FloodStatus dict (plain-string basin/dam names) with the
    municipalities that intersect each one.
    """
    basin_map = build_basin_municipality_map(municipalities_path, basins_path)

    enriched: EnrichedFloodStatus = {}
    for status, sections in flood_status.items():
        enriched[status] = {}
        for section_key, names in sections.items():
            enriched[status][section_key] = [
                {"name": name, "municipalities": basin_map.get(name, [])}
                for name in names
            ]

    return enriched

def get_enriched_flood_status(
    html: str,
    municipalities_path: str,
    basins_path: str,
) -> EnrichedFloodStatus:
    """
    Full pipeline: parses the scraped HTML, then enriches every
    river basin / dam entry with the municipalities that touch it.
    """
    flood_status = parse_flood_status(html)
    return add_municipalities(flood_status, municipalities_path, basins_path)