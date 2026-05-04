"""
Scrapes zag.com.au for Audi A5 Avant (Wagon) demo and used listings.

Fetches the server-rendered HTML pages directly — the /stockapi/results
AJAX endpoint ignores make/body_type filters and returns all stock.
No browser needed.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://www.zag.com.au"

# HTML pages — server-side filtered to A5 Avant (Wagon) per condition.
# The /stockapi/results AJAX endpoint ignores make/body_type params;
# scraping the HTML pages directly is the only way to get pre-filtered results.
CONDITION_PAGES = {
    "Demo": "https://www.zag.com.au/stock?condition=Demo&make%5BAudi%5D=A5&body_type=Wagon&fuel_type=Petrol",
    "Used": "https://www.zag.com.au/stock?condition=Used&make%5BAudi%5D=A5&body_type=Wagon&fuel_type=Petrol",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-AU,en;q=0.9",
}


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
    scraped_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    all_listings = []
    debug_info = {}

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        for condition, url in CONDITION_PAGES.items():
            resp = client.get(url)
            resp.raise_for_status()

            html = resp.text
            soup = BeautifulSoup(html, "lxml")
            listings = _parse_cards(soup, scraped_at, condition)
            all_listings.extend(listings)

            if debug:
                all_links = [a.get("href", "") for a in soup.find_all("a", href=True)]
                detail_links = [l for l in all_links if "stock/details" in l]
                debug_info[condition] = {
                    "status_code": resp.status_code,
                    "html_length": len(html),
                    "total_detail_links": len(detail_links),
                    "listings_after_filter": len(listings),
                    "sample_detail_links": detail_links[:5],
                    "html_snippet": html[:2000],
                }

    if debug:
        return all_listings, debug_info

    return all_listings


def _parse_cards(soup: BeautifulSoup, scraped_at: str, condition: str = "Demo") -> list[dict]:
    listings = []

    # Each listing is a div.stock-item with data-stockno and data-vin attributes
    for card in soup.find_all("div", class_="stock-item"):
        card_text = card.get_text(separator=" ", strip=True)

        # Must mention A5
        if "a5" not in card_text.lower():
            continue

        # Spec spans follow a fixed order:
        # year, make, model, variant, price, "Drive Away", condition,
        # km, consumption, body_type, fuel_type, dealer
        spans = [s.get_text(strip=True) for s in card.find_all("span") if s.get_text(strip=True)]

        # Title link has class "si-title"
        title_link = card.find("a", class_="si-title")
        href = title_link.get("href", "") if title_link else ""
        title = (
            title_link.get("title") or title_link.get_text(strip=True)
            if title_link else card_text[:100]
        )

        # Stock number and VIN from data attributes on the card div
        stock_no = card.get("data-stockno", "")
        vin = card.get("data-vin", "")

        # Dealer is the last span (e.g. "Audi Centre Brighton")
        dealer = spans[-1] if spans else "Zagame Audi"

        # Colour
        colour = ""
        colour_m = re.search(
            r"\b(white|black|grey|gray|silver|blue|red|green|brown|yellow|orange|"
            r"mythos|navarra|glacier|daytona|manhattan|florett|merlin|tango|terra)\b",
            card_text, re.IGNORECASE,
        )
        if colour_m:
            colour = colour_m.group(0).title()

        full_url = BASE_URL + href if href.startswith("/") else href

        listings.append({
            "title": title,
            "dealer": dealer,
            "suburb": "",
            "price": parse_price(card_text),
            "odometer": parse_odometer(card_text),
            "colour": colour,
            "variant": title,
            "stock_no": stock_no,
            "vin": vin,
            "url": full_url,
            "scraped_at": scraped_at,
            "is_new": True,
            "condition": condition,
        })

    return listings
