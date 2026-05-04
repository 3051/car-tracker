"""
Scrapes the Zagame Automotive stock API (zag.com.au) for
Audi A5 Avant (Wagon) petrol demo listings.

The API endpoint returns {"html": "...listing cards..."} — JSON-wrapped HTML.
No browser needed.
"""
from __future__ import annotations

import re
import json
from datetime import datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

API_URL = (
    "https://www.zag.com.au/stockapi/results"
    "?make=Audi&model=A5&condition=Demo"
)
BASE_URL = "https://www.zag.com.au"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Referer": "https://www.zag.com.au/stock/list-all?make=Audi&model=A5&condition=Demo",
    "X-Requested-With": "XMLHttpRequest",
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

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        resp = client.get(API_URL)
        resp.raise_for_status()

    # Response is {"html": "...escaped listing HTML..."}
    data = resp.json()
    html = data.get("html", "") if isinstance(data, dict) else resp.text

    soup = BeautifulSoup(html, "lxml")
    listings = _parse_cards(soup, scraped_at)

    if debug:
        all_links = [a.get("href", "") for a in soup.find_all("a", href=True)]
        detail_links = [l for l in all_links if "stock/details" in l]
        return listings, {
            "status_code": resp.status_code,
            "response_keys": list(data.keys()) if isinstance(data, dict) else "not json",
            "html_length": len(html),
            "total_detail_links": len(detail_links),
            "listings_after_filter": len(listings),
            "sample_detail_links": detail_links[:5],
            "html_snippet": html[:3000],
        }

    return listings


def _parse_cards(soup: BeautifulSoup, scraped_at: str) -> list[dict]:
    seen: set = set()
    listings = []

    for link in soup.find_all("a", href=re.compile(r"stock/details", re.I)):
        href = link.get("href", "")
        if not href or href in seen:
            continue

        # Skip "Explore Vehicle" buttons — keep title/image links
        link_text = link.get_text(strip=True).lower()
        if "explore" in link_text or "save" in link_text:
            continue

        seen.add(href)

        # Walk up to find the card container (has price + specs)
        card = link
        for _ in range(6):
            parent = card.parent
            if not parent:
                break
            parent_text = parent.get_text(separator=" ", strip=True)
            if "$" in parent_text and "km" in parent_text.lower():
                card = parent
                break
            card = parent

        card_text = card.get_text(separator=" ", strip=True)

        # Filter: must mention A5
        if "a5" not in card_text.lower():
            continue

        # Extract spec spans — format: Demo · 2,105 km · 7.4L/100km · Wagon · 2.0L Petrol
        spans = [s.get_text(strip=True) for s in card.find_all("span") if s.get_text(strip=True)]

        # Filter: must be Wagon/Avant
        body_type = _find_span(spans, ["wagon", "avant"])
        if not body_type:
            continue

        # Filter: must be petrol (reject electric/hybrid)
        fuel = _find_span(spans, ["petrol"])
        if not fuel:
            if _find_span(spans, ["electric", "hybrid", "e-tron"]):
                continue

        # Title: prefer <h2>/<h3> in card, else first link text
        title = ""
        for tag in card.find_all(["h2", "h3", "h4", "strong"]):
            t = tag.get_text(strip=True)
            if "a5" in t.lower() and len(t) > 10:
                title = t
                break
        if not title:
            title = link.get("title") or link.get_text(strip=True) or card_text[:80]

        # Dealer name
        dealer = "Zagame Audi"
        for cls_hint in ["dealer", "location", "branch", "showroom", "store"]:
            el = card.find(class_=re.compile(cls_hint, re.I))
            if el:
                dealer = el.get_text(strip=True)[:80]
                break

        # Colour from title
        colour = ""
        colour_m = re.search(
            r"\b(white|black|grey|gray|silver|blue|red|green|brown|yellow|orange|"
            r"mythos|navarra|glacier|daytona|manhattan|florett|merlin|tango|terra)\b",
            card_text, re.IGNORECASE,
        )
        if colour_m:
            colour = colour_m.group(0).title()

        full_url = BASE_URL + href if href.startswith("/") else href
        stock_m = re.search(r"OAG-AD-\d+", href)

        listings.append({
            "title": title,
            "dealer": dealer,
            "suburb": "",
            "price": parse_price(card_text),
            "odometer": parse_odometer(card_text),
            "colour": colour,
            "variant": title,
            "stock_no": stock_m.group(0) if stock_m else "",
            "vin": "",
            "url": full_url,
            "scraped_at": scraped_at,
            "is_new": True,
        })

    return listings


def _find_span(spans: list[str], keywords: list[str]) -> Optional[str]:
    """Return the first span whose text matches any keyword (case-insensitive)."""
    for span in spans:
        if any(kw in span.lower() for kw in keywords):
            return span
    return None
