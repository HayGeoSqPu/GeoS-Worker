# contains generics (function shared by other functions)
from bs4 import BeautifulSoup
import requests
from typing import Dict

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait



def get_html_element(url: str, selector : str = "div.weekly-advisory-content") -> str:
    """Fetches the PAGASA weather advisory page and captures the advisory
    content from the `.weekly-advisory-content` div using BeautifulSoup.

    Loads the page with headless Chrome (Selenium) so JS-rendered content is
    available, captures the FULL rendered DOM, then extracts the inner HTML of
    the advisory container div. Falls back to a plain HTTP fetch if the driver
    fails or returns nothing.
    """
    headers: Dict[str, str] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/115.0.0.0 Safari/537.36"
        )
    }

    # Configure headless Chrome options
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(f"user-agent={headers['User-Agent']}")

    html_source = ""
    driver = None

    # Render the page with Selenium so JS-loaded content is available
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.get(url)

        # Wait for the advisory content div to appear in the rendered DOM
        try:
            WebDriverWait(driver, timeout=15).until(
                EC.presence_of_element_located(
                    (
                        # wait, why? dunno

                        By.CSS_SELECTOR,
                        f"{selector}",
                    )
                )
            )
        except TimeoutException:
            print("Timed out waiting for advisory content; using current DOM.")

        # Capture the ENTIRE rendered document (not just the iframe)
        html_source = driver.page_source or ""

    except Exception as e:
        print(f"Error rendering page with Selenium: {e}")

    finally:
        if driver:
            driver.quit()

    # If Selenium failed or returned nothing, fall back to plain HTTP.
    # The raw source still contains the advisory content.
    if not html_source.strip():
        print("No rendered HTML captured; falling back to raw HTTP fetch.")
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            html_source = response.text
        except requests.RequestException as e:
            print(f"Error fetching PAGASA website: {e}")
            return ""

    # Capture the advisory content from its container div
    # e.g. <div class="col-md-12  weekly-advisory-content">
    soup = BeautifulSoup(html_source, "html.parser")
    target_element = soup.select_one(f"{selector}")

    if target_element:
        return target_element.decode_contents().strip()

    return ""
