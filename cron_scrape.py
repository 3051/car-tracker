"""
Standalone scrape script — run on a schedule (cron, GitHub Actions, Railway cron).
Usage: python cron_scrape.py
"""
import sys
from scraper import scrape_listings
from database import init_db, save_listings

def main():
    print("Initialising database...")
    init_db()

    print("Scraping drive.com.au for A5 Avant TFSI petrol listings in VIC...")
    try:
        listings = scrape_listings()
    except Exception as e:
        print(f"ERROR: Scrape failed — {e}")
        sys.exit(1)

    if not listings:
        print("No listings found.")
        sys.exit(0)

    print(f"Found {len(listings)} listing(s):")
    for l in listings:
        price = f"${l['price']:,.0f}" if l.get('price') else "POA"
        print(f"  • {l.get('dealer','?')} — {price} — {l.get('colour','?')} — {l.get('odometer','?')} km")

    save_listings(listings)
    print("Saved to database.")

if __name__ == "__main__":
    main()
