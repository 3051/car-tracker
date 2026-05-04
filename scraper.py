"""
Scrapes autotrader.com.au for Audi A5 Avant petrol demo/near-new listings
in Victoria using a real Playwright browser.
"""
from __future__ import annotations

import re
import json
from datetime import datetime
from typing import Optional

SEARCH_URL = (
    "https://www.autotrader.com.au/cars"
    "?make=Audi&model=A5&state=VIC"
)


def parse_price(text: str) -> Optional[float]:
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", str(text))
    return float(digits) if digits else None


def parse_odometer(text: str) -> Optional[int]:
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", str(text))
    return int(digits) if digits else None


def _is_relevant(item: dict) -> bool:
    """Return True if the listing is an A5 Avant/Wagon, petrol, demo/near-new in VIC."""
    def val(*keys) -> str:
        for k in keys:
            v = item.get(k)
            if v:
                return str(v).lower()
            for sub in item.values():
                if isinstance(sub, dict):
                    v = sub.get(k)
                    if v:
                        return str(v).lower()
        return ""

    title = val("title", "name", "heading", "description")
    if "a5" not in title:
        return False

    body = val("bodyStyle", "body_style", "bodyType", "style")
    if body and "wagon" not in body and "avant" not in body:
        if "avant" not in title and "wagon" not in title:
            return False

    fuel = val("fuelType", "fuel_type", "fuel")
    if fuel and "petrol" not in fuel and "tfsi" not in fuel:
        return False

    condition = val("condition", "vehicleCondition", "stockType", "listingType")
    if condition and not any(k in condition for k in ["demo", "near"]):
        return False

    state = val("state", "location", "suburb", "area", "sellerState")
    if state and "vic" not in state and "victoria" not in state:
        return False

    return True


def _extract_listing(item: dict, scraped_at: str) -> dict:
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

    title = str(get("title", "name", "heading", "description") or "")
    url = str(get("url", "href", "detailUrl", "listingUrl", "link") or "")
    if url and not url.startswith("http"):
        url = "https://www.carsales.com.au" + url

    price_raw = get("price", "advertisedPrice", "driveAwayPrice", "priceValue")
    odo_raw = get("odometer", "kilometres", "km", "mileage", "kms")

    return {
        "title": title,
        "dealer": str(get("dealer", "dealerName", "sellerName", "seller") or "Audi Dealer"),
        "suburb": str(get("suburb", "location", "city", "area") or ""),
        "price": parse_price(price_raw),
        "odometer": parse_odometer(odo_raw),
        "colour": str(get("colour", "color", "exteriorColour") or ""),
        "variant": str(get("variant", "badge", "grade", "trim", "series") or title),
        "stock_no": str(get("stockNumber", "stockNo", "stock_no", "id", "listingId") or ""),
        "vin": str(get("vin", "VIN") or ""),
        "url": url,
        "scraped_at": scraped_at,
        "is_new": True,
    }


def _search_json(obj, scraped_at: str, depth: int = 0) -> list[dict]:
    """Recursively search any JSON structure for listing-shaped objects."""
    if depth > 8:
        return []
    listings = []
    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict) and _is_relevant(item):
                listings.append(_extract_listing(item, scraped_at))
            else:
                listings.extend(_search_json(item, scraped_at, depth + 1))
    elif isinstance(obj, dict):
        # If this dict itself looks like a listing, extract it
        if _is_relevant(obj):
            listings.append(_extract_listing(obj, scraped_at))
        else:
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    listings.extend(_search_json(v, scraped_at, depth + 1))
    return listings


def scrape_listings(debug: bool = False):
    import subprocess
    subprocess.run(["playwright", "install", "chromium"], capture_output=True)

    from playwright.sync_api import sync_playwright

    scraped_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    listings = []
    api_results = []
    page_title = ""
    page_url = ""
    page_html_snippet = ""

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

        def handle_response(response):
            ct = response.headers.get("content-type", "")
            if "json" in ct:
                try:
                    body = response.json()
                    api_results.append({"url": response.url, "body": body})
                except Exception:
                    pass

        page.on("response", handle_response)

        page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
        # Give JS time to execute and render
        page.wait_for_timeout(4000)

        page_title = page.title()
        page_url = page.url

        # --- Strategy 1: __NEXT_DATA__ (carsales uses Next.js) ---
        try:
            next_data_text = page.evaluate(
                "() => { const el = document.getElementById('__NEXT_DATA__'); return el ? el.textContent : null; }"
            )
            if next_data_text:
                next_data = json.loads(next_data_text)
                found = _search_json(next_data, scraped_at)
                listings.extend(found)
        except Exception:
            pass

        # --- Strategy 2: intercepted API JSON responses ---
        if not listings:
            for call in api_results:
                found = _search_json(call["body"], scraped_at)
                listings.extend(found)

        # --- Strategy 3: all <script type="application/json"> tags ---
        if not listings:
            try:
                scripts = page.query_selector_all(
                    "script[type='application/json'], script[type='application/ld+json']"
                )
                for script in scripts:
                    try:
                        data = json.loads(script.inner_text())
                        found = _search_json(data, scraped_at)
                        listings.extend(found)
                    except Exception:
                        pass
            except Exception:
                pass

        # --- Strategy 4: DOM card scraping ---
        if not listings:
            listings = _scrape_dom(page, scraped_at)

        if debug:
            page_html_snippet = page.content()[:4000]

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
            "api_calls_intercepted": len(api_results),
            "api_urls": [r["url"] for r in api_results],
            "page_html_snippet": page_html_snippet,
        }
    return unique


def _scrape_dom(page, scraped_at: str) -> list[dict]:
    listings = []
    card_selectors = [
        "[data-webm*='listing-item']",
        "[class*='listing-item']",
        "[class*='vehicle-card']",
        "[class*='car-card']",
        "[class*='result-item']",
        "article[class*='card']",
        "article",
    ]
    cards = []
    for sel in card_selectors:
        try:
            found = page.query_selector_all(sel)
            if found:
                cards = found
                break
        except Exception:
            continue

    for card in cards:
        try:
            text = card.inner_text()
            if "a5" not in text.lower():
                continue
            price_match = re.search(r"\$[\d,]+", text)
            price = parse_price(price_match.group()) if price_match else None
            odo_match = re.search(r"([\d,]+)\s*k(?:m|ms)\b", text, re.IGNORECASE)
            odo = parse_odometer(odo_match.group(1)) if odo_match else None
            url = ""
            try:
                link = card.query_selector("a")
                if link:
                    url = link.get_attribute("href") or ""
                    if url and not url.startswith("http"):
                        url = "https://www.carsales.com.au" + url
            except Exception:
                pass
            listings.append({
                "title": text[:120].split("\n")[0].strip(),
                "dealer": "Audi Dealer",
                "suburb": "",
                "price": price,
                "odometer": odo,
                "colour": "",
                "variant": "Audi A5 Avant",
                "stock_no": "",
                "vin": "",
                "url": url,
                "scraped_at": scraped_at,
                "is_new": True,
            })
        except Exception:
            continue

    return listings
