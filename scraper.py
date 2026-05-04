"""
Scrapes zag.com.au (Zagame Automotive — 5 Audi dealers in VIC) for
Audi A5 Avant (Wagon) petrol demo listings using Playwright.
zag.com.au loads listings dynamically via the AdTorque Edge platform.
"""
from __future__ import annotations

import re
import json
from datetime import datetime
from typing import Optional

STOCK_URL = (
    "https://www.zag.com.au/stock/list-all"
    "?make=Audi&model=A5&condition=Demo"
)
BASE_URL = "https://www.zag.com.au"


def parse_price(text: str) -> Optional[float]:
    if not text:
        return None
    m = re.search(r"\$([\d,]+)", str(text))
    return float(m.group(1).replace(",", "")) if m else None


def parse_odometer(text: str) -> Optional[int]:
    if not text:
        return None
    m = re.search(r"([\d,]+)\s*km\b", str(text), re.IGNORECASE)
    return int(m.group(1).replace(",", "")) if m else None


def scrape_listings(debug: bool = False):
    import subprocess
    subprocess.run(["playwright", "install", "chromium"], capture_output=True)

    from playwright.sync_api import sync_playwright

    scraped_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    api_calls: list[dict] = []
    listings: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-AU",
        )
        page = context.new_page()

        # Intercept ALL JSON responses — AdTorque Edge delivers listings via API
        def on_response(response):
            ct = response.headers.get("content-type", "")
            if "json" in ct:
                try:
                    body = response.json()
                    api_calls.append({"url": response.url, "body": body})
                except Exception:
                    pass

        page.on("response", on_response)

        page.goto(STOCK_URL, wait_until="networkidle", timeout=60000)

        # Wait for listing cards to appear
        try:
            page.wait_for_selector(
                "a[href*='stock/details'], [class*='vehicle'], [class*='listing'], [class*='card']",
                timeout=15000,
            )
        except Exception:
            pass

        page_title = page.title()
        page_url = page.url
        page_html = page.content() if debug else ""

        # Strategy 1: intercepted JSON from AdTorque Edge API
        for call in api_calls:
            found = _parse_api_json(call["body"], scraped_at)
            listings.extend(found)

        # Strategy 2: DOM scraping
        if not listings:
            listings = _scrape_dom(page, scraped_at)

        browser.close()

    # Deduplicate
    seen: set = set()
    unique = []
    for l in listings:
        key = l.get("stock_no") or l.get("url") or l.get("title", "")
        if key and key not in seen:
            seen.add(key)
            unique.append(l)

    if debug:
        return unique, {
            "page_title": page_title,
            "page_url": page_url,
            "api_calls_intercepted": len(api_calls),
            "api_urls": [c["url"] for c in api_calls],
            "listings_after_filter": len(unique),
            "html_snippet": page_html[page_html.find("<body"):page_html.find("<body") + 5000] if page_html else "",
        }
    return unique


def _is_avant_petrol_demo(text: str) -> bool:
    t = text.lower()
    if "a5" not in t:
        return False
    if "wagon" not in t and "avant" not in t:
        return False
    if any(k in t for k in ["e-tron", "phev", "plug-in", "electric"]):
        return False
    return True


def _parse_api_json(body, scraped_at: str, depth: int = 0) -> list[dict]:
    """Recursively search any JSON for listing-shaped objects."""
    if depth > 8:
        return []
    results = []
    if isinstance(body, list):
        for item in body:
            if isinstance(item, dict):
                text = json.dumps(item)
                if _is_avant_petrol_demo(text):
                    listing = _extract_from_dict(item, scraped_at)
                    if listing:
                        results.append(listing)
                else:
                    results.extend(_parse_api_json(item, scraped_at, depth + 1))
            else:
                results.extend(_parse_api_json(item, scraped_at, depth + 1))
    elif isinstance(body, dict):
        text = json.dumps(body)
        if _is_avant_petrol_demo(text) and any(k in body for k in ["price", "Price", "driveAway"]):
            listing = _extract_from_dict(body, scraped_at)
            if listing:
                results.append(listing)
        else:
            for v in body.values():
                if isinstance(v, (dict, list)):
                    results.extend(_parse_api_json(v, scraped_at, depth + 1))
    return results


def _extract_from_dict(item: dict, scraped_at: str) -> Optional[dict]:
    def get(*keys):
        for k in keys:
            v = item.get(k)
            if v is not None:
                return v
            for sub in item.values():
                if isinstance(sub, dict):
                    v = sub.get(k)
                    if v is not None:
                        return v
        return None

    title = str(get("title", "name", "heading", "description", "vehicleName") or "")
    if not title:
        return None

    url = str(get("url", "href", "detailUrl", "link") or "")
    if url and not url.startswith("http"):
        url = BASE_URL + url

    return {
        "title": title,
        "dealer": str(get("dealer", "dealerName", "location", "branch") or "Zagame Audi"),
        "suburb": str(get("suburb", "city", "area") or ""),
        "price": parse_price(str(get("price", "driveAway", "advertisedPrice") or "")),
        "odometer": parse_odometer(str(get("odometer", "kilometres", "km") or "")),
        "colour": str(get("colour", "color", "exteriorColour") or ""),
        "variant": str(get("variant", "badge", "grade", "series") or title),
        "stock_no": str(get("stockNumber", "stockNo", "id", "listingId") or ""),
        "vin": str(get("vin", "VIN") or ""),
        "url": url,
        "scraped_at": scraped_at,
        "is_new": True,
    }


def _scrape_dom(page, scraped_at: str) -> list[dict]:
    listings = []
    try:
        links = page.query_selector_all("a[href*='stock/details']")
        seen: set = set()
        for link in links:
            href = link.get_attribute("href") or ""
            if not href or href in seen:
                continue
            seen.add(href)

            card = None
            for _ in range(5):
                parent = link.evaluate_handle("el => el.parentElement")
                text = parent.as_element().inner_text() if parent.as_element() else ""
                if len(text) > 50:
                    card_text = text
                    break
                link = parent.as_element()
            else:
                card_text = link.inner_text()

            if not _is_avant_petrol_demo(card_text):
                continue

            full_url = BASE_URL + href if href.startswith("/") else href
            stock_m = re.search(r"OAG-AD-\d+", href)

            listings.append({
                "title": card_text[:120].split("\n")[0].strip(),
                "dealer": "Zagame Audi",
                "suburb": "",
                "price": parse_price(card_text),
                "odometer": parse_odometer(card_text),
                "colour": "",
                "variant": "Audi A5 Avant",
                "stock_no": stock_m.group(0) if stock_m else "",
                "vin": "",
                "url": full_url,
                "scraped_at": scraped_at,
                "is_new": True,
            })
    except Exception:
        pass
    return listings
