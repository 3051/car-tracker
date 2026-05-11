"""
Scrapes drive.com.au for Audi A5 Avant (Wagon) petrol demo and used listings in VIC.
Uses the GraphQL API at drive-carsforsale-prod.graphcdn.app.
No browser needed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

GRAPHQL_URL = "https://drive-carsforsale-prod.graphcdn.app"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/json",
    "Origin": "https://www.drive.com.au",
    "Referer": "https://www.drive.com.au/cars-for-sale/",
}

_QUERY = """
query GET_MARKETPLACE_LISTINGS_DYNAMIC(
  $where: WhereOptionsDealerListing,
  $limit: Int!
) {
  marketplaceListings: DealerListings(
    paginate: { page: 0, pageSize: $limit }
    where: $where
  ) {
    pageInfo { itemCount }
    results {
      id
      year
      makeName: makeDescription
      modelName: familyDescription
      priceDriveAway: priceIgc
      odometer
      listType: stockType
      variant: description
      dealer: Dealer {
        name
        suburb
        state
      }
    }
  }
}
"""

_WHERE = {
    "makeSlug": {"eq": "audi"},
    "familySlug": {"eq": "a5"},
    "bodyType": {"eq": "Wagon"},
    "state": {"eq": "VIC"},
    "stockType": {"in": ["Demo", "Used"]},
}


def scrape_listings(debug: bool = False):
    scraped_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    payload = {
        "operationName": "GET_MARKETPLACE_LISTINGS_DYNAMIC",
        "query": _QUERY,
        "variables": {
            "limit": 200,
            "where": _WHERE,
        },
    }

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        resp = client.post(GRAPHQL_URL, json=payload)
        resp.raise_for_status()

    data = resp.json()

    if "errors" in data:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")

    ml = data["data"]["marketplaceListings"]
    total_api = ml["pageInfo"]["itemCount"]

    listings = []
    for r in ml["results"]:
        variant = r.get("variant") or ""
        # Exclude PHEVs — variant contains "Hybrid" for e-hybrid models
        if "hybrid" in variant.lower():
            continue

        dealer = r.get("dealer") or {}
        condition = (r.get("listType") or "demo").capitalize()
        listing_id = r["id"]

        listings.append({
            "title": f"{r.get('year', '')} Audi A5 Avant",
            "dealer": dealer.get("name", "Unknown"),
            "suburb": dealer.get("suburb", ""),
            "price": r.get("priceDriveAway"),
            "odometer": r.get("odometer"),
            "colour": "",
            "variant": variant,
            "stock_no": str(listing_id),
            "vin": "",
            "url": f"https://www.drive.com.au/cars-for-sale/{listing_id}/",
            "scraped_at": scraped_at,
            "is_new": True,
            "condition": condition,
        })

    if debug:
        return listings, {
            "status_code": resp.status_code,
            "total_from_api": total_api,
            "listings_after_filter": len(listings),
        }

    return listings


_HISTORY_QUERY = """
query GET_MARKETPLACE_LISTINGS_DYNAMIC($where: WhereOptionsDealerListing, $limit: Int!) {
  marketplaceListings: DealerListings(
    paginate: { page: 0, pageSize: $limit }
    where: $where
  ) {
    results {
      id
      priceDriveAway: priceIgc
      dealer: Dealer { name }
      History(where: { fields: [price_igc] }) {
        newValues
        oldValues
        createdAt
      }
    }
  }
}
"""


def get_price_history(listing_ids: list[str]) -> dict[str, list[dict]]:
    """
    Returns {listing_id: [{date, price, dealer}, ...]} ordered oldest → newest.
    Pulls price-change history directly from drive.com.au API.
    """
    if not listing_ids:
        return {}

    payload = {
        "operationName": "GET_MARKETPLACE_LISTINGS_DYNAMIC",
        "query": _HISTORY_QUERY,
        "variables": {
            "limit": 200,
            "where": {**_WHERE, "id": {"in": [int(i) for i in listing_ids]}},
        },
    }

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        resp = client.post(GRAPHQL_URL, json=payload)
        resp.raise_for_status()

    data = resp.json()
    if "errors" in data:
        return {}

    result = {}
    today = datetime.now(timezone.utc).date().isoformat()

    for r in data["data"]["marketplaceListings"]["results"]:
        listing_id = str(r["id"])
        current_price = r.get("priceDriveAway")
        dealer = (r.get("dealer") or {}).get("name", "Unknown")
        entries = r.get("History") or []

        timeline: list[dict] = []

        if entries:
            # entries come newest-first; reverse for chronological order
            for entry in reversed(entries):
                dt = datetime.fromisoformat(entry["createdAt"].replace("Z", "+00:00"))
                # On the first (oldest) entry, add the original price one day before
                if not timeline:
                    old_price = entry["oldValues"].get("price_igc")
                    if old_price:
                        start = (dt - timedelta(days=1)).date().isoformat()
                        timeline.append({"date": start, "price": old_price, "dealer": dealer})
                new_price = entry["newValues"].get("price_igc")
                if new_price:
                    timeline.append({"date": dt.date().isoformat(), "price": new_price, "dealer": dealer})

        if current_price:
            if timeline and timeline[-1]["date"] == today:
                timeline[-1]["price"] = current_price
            else:
                timeline.append({"date": today, "price": current_price, "dealer": dealer})

        if timeline:
            result[listing_id] = timeline

    return result
