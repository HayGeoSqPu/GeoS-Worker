from typing import List
import urllib.parse
# import pymupdf

import io
import pdfplumber

import json
import re
from typing import Any, Dict, List, Optional
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    )
}


def _pdf_href(href: str) -> str | None:
    """
    Returns the href (cleaned of stray whitespace) if it points at a
    .pdf file, ignoring query strings and fragments (e.g.
    "regional_forecast.pdf?c=31523" still counts); otherwise None.
    """
    href = href.strip()
    if not href:
        return None
    path = urllib.parse.urlparse(href).path
    return href if path.lower().endswith(".pdf") else None


def extract_pdf_links(html: str, selector: str) -> List[str]:
    """
    Given full page HTML and a CSS selector, returns the href of every
    <a> inside the matched element (including the element itself when it
    is an <a>), keeping only links pointing at PDF documents.
    """
    soup = BeautifulSoup(html, "html.parser")
    element = soup.select_one(selector)
    if not element and not soup.find("body"):
        # `html` may be a <body> fragment (e.g. from get_html_element),
        # so wrap it back in a <body> tag for `body > ...` selectors.
        soup = BeautifulSoup(f"<body>{html}</body>", "html.parser")
        element = soup.select_one(selector)
    if not element:
        return []

    anchors = [element] if element.name == "a" else element.find_all("a")

    pdf_links: List[str] = []
    for anchor in anchors:
        href = anchor.get("href")
        if not isinstance(href, str):
            continue
        pdf_href = _pdf_href(href)
        if pdf_href:
            pdf_links.append(pdf_href)

    return pdf_links


def extract_text_from_pdf_url(url: str) -> str:
    """
    Downloads the PDF at `url` into memory and returns its extracted
    text (all pages, joined with blank lines between pages).
    """
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()

    text_parts: list[str] = []
    with pdfplumber.open(io.BytesIO(response.content)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n\n".join(text_parts)
# def extract_html_from_pdf_url(url: str) -> str:
#     """
#     Downloads the PDF at `url` into memory and returns its content as
#     HTML — one <div id="pageN"> per page, with each text run positioned
#     via inline styles (top/left/font-family/font-size). Unlike plain
#     text extraction, this preserves layout, so multi-column tables and
#     spatial structure survive.
#     """
#     response = requests.get(url, headers=HEADERS, timeout=30)
#     response.raise_for_status()

#     html_parts: list[str] = []
#     with pymupdf.open(stream=response.content, filetype="pdf") as doc:
#         for page in doc:
#             html_parts.append(page.get_text("html")) # pyright: ignore[reportUnknownMemberType, reportArgumentType]

#     return "\n".join(html_parts)

# ! clean up ====================================
def _extract_js_object(html: str, var_name: str) -> Optional[Dict[str, Any]]:
    """
    Locates `let <var_name> = {...};` inside a <script> block and parses
    it as JSON. PAGASA renders this via server-side json_encode, so it's
    valid JSON even though it's assigned to a JS variable — brace-matched
    manually since the object can be megabytes and deeply nested.
    """
    match = re.search(rf"\b{re.escape(var_name)}\s*=\s*", html)
    if not match:
        return None

    start = html.find("{", match.end())
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(html)):
        char = html[i]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(html[start : i + 1])
    return None


def _clean_outlook(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Keeps only the meaningful weather fields from one outlook record,
    dropping DB noise (id, created_at, null caused_by/impact, etc.)."""
    fields = [
        "day_description", "day_high", "day_low",
        "day_wind_speed", "day_wind_direction", "day_coastal_condition",
        "night_description", "night_high", "night_low",
        "night_wind_speed", "night_wind_direction", "night_coastal_condition",
    ]
    return {f: entry.get(f) for f in fields if entry.get(f) is not None}


def parse_regional_forecast(html: str) -> Dict[str, Any]:
    """
    Extracts the headline + per-province outlook data embedded in the
    page's `regional` JS object into a clean, JSON-friendly shape:

    {
        "headline": "...",
        "issued": "...",
        "valid": "...",
        "provinces": [
            {"Albay": {"latitude": ..., "longitude": ..., "outlook": [...]}},
            ...
        ]
    }
    """
    regional = _extract_js_object(html, "regional")
    if not regional:
        return {}

    weather = regional.get("weather", {})
    province_data = regional.get("provincial", {}).get("data", {})

    provinces: List[Dict[str, Any]] = []
    for province in province_data.values():
        name = province.get("name", "Unknown")
        outlook = [_clean_outlook(o) for o in province.get("outlook", [])]
        provinces.append({
            name: {
                "latitude": province.get("latitude"),
                "longitude": province.get("longitude"),
                "outlook": outlook,
            }
        })

    return {
        "headline": weather.get("condition"),
        "issued": weather.get("issued_date"),
        "valid": weather.get("valid_date"),
        "provinces": provinces,
    }