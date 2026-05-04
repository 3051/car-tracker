"""
Scrapes audi.com.au/en/audi-used-car-search/ for A5 Avant petrol demo listings
near Melbourne using a real Playwright browser (handles JS-rendered content).
"""

import re
import json
from datetime import datetime
from typing import Optional

SEARCH_URL = (
    "https://www.audi.com.au/en/audi-used-car-search/"
    "?modelrange=A5"
    "&bodystyle=AVANT"
    "&fueltype=PETROL"
    "&condition=DEMONSTRATION"
    "&postcode=3000"
    "&radius=150"
)


def parse_price(text: str) -> Optional[float]:
    """Extract numeric price from a string like '$98,990 drive away'."""
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return float(digits) if digits else None


def parse_odometer(text: str) -> Optional[int]:
    """Extract odometer km from strings like '1,147 kms' or '1147km'."""
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def scrape_listings(debug: bool = False) -> list[dict] | tuple[list[dict], dict]:
    """
    Launch a headless Chromium browser, navigate to the Audi AU used car search
    filtered for A5 Avant Petrol Demo listings, wait for results to render,
    then extract and return structured listing data.

    If debug=True, returns (listings, debug_info) instead of just listings.
    """
    import subprocess
    subprocess.run(["playwright", "install", "chromium"], capture_output=True)

    from playwright.sync_api import sync_playwright

    listings = []
    scraped_at = datetime.now().strftime("%Y-%m-%d %H:%M")

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

        # Intercept ALL JSON API responses (broadened from keyword filter)
        api_results = []

        def handle_response(response):
            url = response.url
            ct = response.headers.get("content-type", "")
            if "json" in ct:
                try:
                    body = response.json()
                    api_results.append({"url": url, "body": body})
                except Exception:
                    pass

        page.on("response", handle_response)

        # Navigate and wait for listing cards to appear
        page.goto(SEARCH_URL, wait_until="networkidle", timeout=45000)

        page_title = page.title()
        page_url = page.url

        # Give the SPA extra time to render
        try:
            page.wait_for_selector(
                "[class*='result'], [class*='listing'], [class*='vehicle-card'], "
                "[class*='car-tile'], [class*='search-result']",
                timeout=15000,
            )
        except Exception:
            pass

        page_text_snippet = page.inner_text("body")[:2000] if debug else ""

        # --- Strategy 1: Parse intercepted API JSON responses ---
        for api_call in api_results:
            body = api_call["body"]
            extracted = _parse_api_response(body, scraped_at)
            if extracted:
                listings.extend(extracted)

        # --- Strategy 2: Scrape the rendered DOM ---
        if not listings:
            listings = _scrape_dom(page, scraped_at)

        browser.close()

    # Deduplicate by stock number or URL
    seen = set()
    unique = []
    for l in listings:
        key = l.get("stock_no") or l.get("url") or l.get("title", "")
        if key and key not in seen:
            seen.add(key)
            unique.append(l)

    if debug:
        debug_info = {
            "page_title": page_title,
            "page_url": page_url,
            "api_calls_intercepted": len(api_results),
            "api_urls": [r["url"] for r in api_results],
            "page_text_snippet": page_text_snippet,
        }
        return unique, debug_info

    return unique


def _parse_api_response(body: dict | list, scraped_at: str) -> list[dict]:
    """
    Try to extract listing data from a JSON API response body.
    Handles common response shapes from Audi / VW Group search APIs.
    """
    listings = []

    # Flatten if wrapped
    if isinstance(body, dict):
        # Try common wrapper keys
        for key in ["data", "results", "vehicles", "items", "listings", "content"]:
            if key in body and isinstance(body[key], list):
                body = body[key]
                break
        else:
            if "vehicles" in body:
                body = body["vehicles"]
            elif isinstance(body.get("data"), dict):
                for k in ["vehicles", "results", "items"]:
                    if k in body["data"]:
                        body = body["data"][k]
                        break

    if not isinstance(body, list):
        return []

    for item in body:
        if not isinstance(item, dict):
            continue

        # Try to extract fields with multiple fallback key names
        def get(*keys):
            for k in keys:
                v = item.get(k)
                if v is not None:
                    return v
                # nested — e.g. item["vehicle"]["price"]
                for sub in item.values():
                    if isinstance(sub, dict) and k in sub:
                        return sub[k]
            return None

        title = get("title", "name", "modelName", "description") or ""
        # Only keep A5 Avant petrol demos
        title_lower = (title or "").lower()
        body_style = (get("bodyStyle", "bodystyle", "body_style", "bodyType") or "").lower()
        fuel = (get("fuelType", "fuel_type", "fuel") or "").lower()
        condition = (get("condition", "vehicleCondition") or "").lower()

        # Filter: must be Avant (wagon), petrol, demo
        if body_style and "avant" not in body_style and "wagon" not in body_style:
            continue
        if fuel and "petrol" not in fuel and "tfsi" not in fuel:
            continue
        if condition and "demo" not in condition and "demonstration" not in condition:
            continue

        price_raw = get("price", "driveAwayPrice", "priceDisplay", "retailPrice")
        price = parse_price(str(price_raw)) if price_raw else None

        odo_raw = get("odometer", "mileage", "kilometres", "km")
        odo = parse_odometer(str(odo_raw)) if odo_raw else None

        listings.append({
            "title": title,
            "dealer": get("dealerName", "dealer", "dealership", "sellerName") or "Audi Dealer",
            "suburb": get("suburb", "dealerSuburb", "location", "city") or "",
            "price": price,
            "odometer": odo,
            "colour": get("colour", "color", "exteriorColour", "exteriorColor") or "",
            "variant": get("variant", "modelVariant", "grade", "trim") or title,
            "stock_no": str(get("stockNumber", "stock_no", "stockNo", "id") or ""),
            "vin": get("vin", "VIN") or "",
            "url": get("url", "detailUrl", "listingUrl", "link") or "",
            "scraped_at": scraped_at,
            "is_new": True,
        })

    return listings


def _scrape_dom(page, scraped_at: str) -> list[dict]:
    """
    Fall back to scraping the rendered HTML DOM when API interception doesn't work.
    Tries multiple common selector patterns used by Audi/VW Group SPA templates.
    """
    listings = []

    # Try to get all result cards using various likely selectors
    card_selectors = [
        "[class*='vehicle-card']",
        "[class*='car-result']",
        "[class*='listing-item']",
        "[class*='result-item']",
        "[class*='car-tile']",
        "[data-type='vehicle']",
        "[class*='search-result-item']",
        "[class*='stock-item']",
        "article",
    ]

    cards = []
    for sel in card_selectors:
        try:
            cards = page.query_selector_all(sel)
            if len(cards) >= 1:
                break
        except Exception:
            continue

    # If still no cards, grab the full page text and try to parse it
    if not cards:
        try:
            # Look for JSON embedded in a script tag (common in SSR/hydration)
            scripts = page.query_selector_all("script[type='application/json'], script[type='application/ld+json']")
            for script in scripts:
                try:
                    content = script.inner_text()
                    data = json.loads(content)
                    parsed = _parse_api_response(data, scraped_at)
                    if parsed:
                        listings.extend(parsed)
                except Exception:
                    pass
        except Exception:
            pass
        return listings

    for card in cards:
        try:
            text = card.inner_text()
            # Skip if clearly not an A5 Avant petrol demo
            text_lower = text.lower()
            if "a5" not in text_lower:
                continue

            # Try to find price
            price_match = re.search(r"\$[\d,]+", text)
            price = parse_price(price_match.group()) if price_match else None

            # Try to find odometer
            odo_match = re.search(r"([\d,]+)\s*k(?:m|ms)\b", text, re.IGNORECASE)
            odo = parse_odometer(odo_match.group(1)) if odo_match else None

            # Try to get link
            url = ""
            try:
                link = card.query_selector("a")
                if link:
                    url = link.get_attribute("href") or ""
                    if url and not url.startswith("http"):
                        url = "https://www.audi.com.au" + url
            except Exception:
                pass

            # Extract dealer name — usually a visible text element
            dealer = "Audi Dealer"
            try:
                for sel in ["[class*='dealer']", "[class*='location']", "[class*='seller']"]:
                    el = card.query_selector(sel)
                    if el:
                        dealer = el.inner_text().strip()[:80]
                        break
            except Exception:
                pass

            listings.append({
                "title": text[:120].split("\n")[0].strip(),
                "dealer": dealer,
                "suburb": "",
                "price": price,
                "odometer": odo,
                "colour": "",
                "variant": "A5 Avant TFSI Petrol",
                "stock_no": "",
                "vin": "",
                "url": url,
                "scraped_at": scraped_at,
                "is_new": True,
            })
        except Exception:
            continue

    return listings
