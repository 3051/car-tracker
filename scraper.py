"""
Scrapes drive.com.au for Audi A5 Avant (Wagon) petrol demo and used listings in VIC.
Uses the GraphQL API at drive-carsforsale-prod.graphcdn.app.
No browser needed.
"""
from __future__ import annotations

from datetime import datetime
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
  $limit: Int!,
  $sort: SortInput
) {
  marketplaceListings: DealerListings(
    sort: $sort
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
            "sort": {"by": "priceDriveAway", "order": "ASC"},
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
