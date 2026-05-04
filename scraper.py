"""
Scrapes carsales.com.au for Audi A5 Avant petrol demo/near-new listings
in Victoria using a real Playwright browser.
"""

import re
import json
from datetime import datetime
from typing import Optional

SEARCH_URL = (
    "https://www.carsales.com.au/cars/audi/a5/"
    "?q=(And.(C.Make.Audi._.Model.A5._.BodyStyle.Wagon."
    "_.Condition.(Or.Demo.%60Near-New%60.)."
    "_.FuelType.Petrol._.State.VIC.))"
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


def scrape_listings(debug: bool = False) -> list[dict] | tuple[list[dict], dict]:
    import subprocess
    subprocess.run(["playwright", "install", "chromium"], capture_output=True)

    from playwright.sync_api import sync_playwright

    listings = []
    scraped_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    api_results = []
    page_title = ""
    page_url = ""
    page_text_snippet = ""

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

        page.goto(SEARCH_URL, wait_until="networkidle", timeout=60000)

        page_title = page.title()
        page_url = page.url

        # Wait for listing cards
        try:
            page.wait_for_selector(
                "[data-webm*='listing'], [class*='listing'], "
                "[class*='card'], [class*='result']",
                timeout=15000,
            )
        except Exception:
            pass

        if debug:
            page_text_snippet = page.inner_text("body")[:3000]

        # Strategy 1: parse intercepted API JSON
        for call in api_results:
            extracted = _parse_api_response(call["body"], scraped_at)
            if extracted:
                listings.extend(extracted)

        # Strategy 2: DOM scrape
        if not listings:
            listings = _scrape_dom(page, scraped_at)

        browser.close()

    # Deduplicate
    seen = set()
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
            "page_text_snippet": page_text_snippet,
        }
    return unique


def _parse_api_response(body, scraped_at: str) -> list[dict]:
    listings = []

    # Unwrap common envelope shapes
    if isinstance(body, dict):
        for key in ["results", "data", "items", "listings", "vehicles", "content"]:
            val = body.get(key)
            if isinstance(val, list):
                body = val
                break
            if isinstance(val, dict):
                for k2 in ["results", "items", "listings", "vehicles"]:
                    if isinstance(val.get(k2), list):
                        body = val[k2]
                        break

    if not isinstance(body, list):
        return []

    for item in body:
        if not isinstance(item, dict):
            continue

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

        title = str(get("title", "name", "description", "heading") or "")
        title_lower = title.lower()

        # Must mention A5
        if "a5" not in title_lower:
            continue

        # Must be Avant / wagon
        body_style = str(get("bodyStyle", "body_style", "bodyType", "style") or "").lower()
        if body_style and "wagon" not in body_style and "avant" not in body_style:
            # Fall back to checking title
            if "avant" not in title_lower and "wagon" not in title_lower:
                continue

        # Must be petrol
        fuel = str(get("fuelType", "fuel_type", "fuel", "fueltype") or "").lower()
        if fuel and "petrol" not in fuel and "tfsi" not in fuel:
            continue

        # Must be demo or near-new
        condition = str(get("condition", "vehicleCondition", "stockType") or "").lower()
        if condition and not any(k in condition for k in ["demo", "near", "new"]):
            continue

        price_raw = get("price", "driveAwayPrice", "advertisedPrice", "priceValue", "retailPrice")
        price = parse_price(price_raw)

        odo_raw = get("odometer", "kilometres", "km", "mileage", "kms")
        odo = parse_odometer(odo_raw)

        url = str(get("url", "detailUrl", "listingUrl", "href", "link") or "")
        if url and not url.startswith("http"):
            url = "https://www.carsales.com.au" + url

        listings.append({
            "title": title,
            "dealer": str(get("dealer", "dealerName", "sellerName", "seller") or "Audi Dealer"),
            "suburb": str(get("suburb", "location", "city", "dealerSuburb") or ""),
            "price": price,
            "odometer": odo,
            "colour": str(get("colour", "color", "exteriorColour", "exteriorColor") or ""),
            "variant": str(get("variant", "badge", "grade", "trim", "series") or title),
            "stock_no": str(get("stockNumber", "stockNo", "stock_no", "id", "listingId") or ""),
            "vin": str(get("vin", "VIN") or ""),
            "url": url,
            "scraped_at": scraped_at,
            "is_new": True,
        })

    return listings


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

    if not cards:
        # Try JSON embedded in script tags
        try:
            for script in page.query_selector_all("script[type='application/json'], script[type='application/ld+json']"):
                try:
                    data = json.loads(script.inner_text())
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

            dealer = "Audi Dealer"
            try:
                for sel in ["[class*='dealer']", "[class*='seller']", "[class*='location']"]:
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
