"""
Scrapes zag.com.au (Zagame Automotive — 5 Audi dealers in VIC) for
Audi A5 Avant (Wagon) petrol demo listings using httpx + BeautifulSoup.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://www.zag.com.au"
STOCK_URL = f"{BASE_URL}/stock/list-all?make=Audi&model=A5&condition=Demo"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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
    debug_info: dict = {}

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        resp = client.get(STOCK_URL)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")

    if debug:
        debug_info["status_code"] = resp.status_code
        debug_info["final_url"] = str(resp.url)
        debug_info["page_title"] = soup.title.string if soup.title else ""
        debug_info["html_snippet"] = resp.text[:3000]

    listings = _parse_listings(soup, scraped_at)

    if debug:
        debug_info["raw_cards_found"] = len(
            soup.find_all("a", href=re.compile(r"/stock/details/"))
        )
        debug_info["listings_after_filter"] = len(listings)
        return listings, debug_info

    return listings


def _parse_listings(soup: BeautifulSoup, scraped_at: str) -> list[dict]:
    # Find all unique detail-page links
    seen: set = set()
    listings = []

    for link in soup.find_all("a", href=re.compile(r"/stock/details/")):
        href = link.get("href", "")
        if not href or href in seen:
            continue
        seen.add(href)

        # Walk up to find the card container
        card = link.find_parent(["article", "div", "li"])
        if not card:
            continue

        card_text = card.get_text(separator=" ", strip=True)

        # Must be A5
        if "a5" not in card_text.lower():
            continue

        # Must be Avant/Wagon — not Hatch (Sportback)
        if "wagon" not in card_text.lower() and "avant" not in card_text.lower():
            continue

        # Must be petrol (exclude e-tron, plug-in hybrid, electric)
        text_lower = card_text.lower()
        if any(k in text_lower for k in ["e-tron", "phev", "plug-in", "electric"]):
            continue

        # Title: prefer the link text from an <h3>, else the link itself
        h_tag = card.find(["h2", "h3", "h4"])
        title = (h_tag.get_text(strip=True) if h_tag else link.get_text(strip=True)) or ""

        # Dealer name
        dealer = "Zagame Audi"
        for cls in ["dealer", "location", "branch", "showroom"]:
            el = card.find(class_=re.compile(cls, re.I))
            if el:
                dealer = el.get_text(strip=True)[:80]
                break

        # Colour: often in title or a dedicated element
        colour = ""
        colour_match = re.search(
            r"\b(white|black|grey|gray|silver|blue|red|green|brown|yellow|orange|"
            r"mythos|navarra|glacier|daytona|manhattan|florett|merlin|tango|terra)\b",
            card_text, re.IGNORECASE
        )
        if colour_match:
            colour = colour_match.group(0).title()

        full_url = BASE_URL + href if href.startswith("/") else href
        stock_no_m = re.search(r"OAG-AD-\d+", href)

        listings.append({
            "title": title,
            "dealer": dealer,
            "suburb": "",
            "price": parse_price(card_text),
            "odometer": parse_odometer(card_text),
            "colour": colour,
            "variant": title,
            "stock_no": stock_no_m.group(0) if stock_no_m else "",
            "vin": "",
            "url": full_url,
            "scraped_at": scraped_at,
            "is_new": True,
        })

    return listings
