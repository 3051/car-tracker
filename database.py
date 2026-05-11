"""
SQLite database for persisting Audi A5 Avant listing snapshots.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "listings.db"


def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS listings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                scraped_at  TEXT NOT NULL,
                stock_no    TEXT,
                vin         TEXT,
                title       TEXT,
                dealer      TEXT,
                suburb      TEXT,
                price       REAL,
                odometer    INTEGER,
                colour      TEXT,
                variant     TEXT,
                url         TEXT,
                is_new      INTEGER DEFAULT 0,
                condition   TEXT DEFAULT 'Demo',
                raw_json    TEXT
            )
        """)
        # Migrate existing DBs that lack the condition column
        existing = {row[1] for row in con.execute("PRAGMA table_info(listings)")}
        if "condition" not in existing:
            con.execute("ALTER TABLE listings ADD COLUMN condition TEXT DEFAULT 'Demo'")
        con.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                scraped_at  TEXT NOT NULL,
                count       INTEGER
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_scraped_at ON listings(scraped_at)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_vin ON listings(vin)")


def save_listings(listings: list[dict]):
    """Save a batch of listings, marking which are new vs previously seen."""
    if not listings:
        return

    scraped_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Get previously seen VINs / stock numbers to detect new listings
    with _conn() as con:
        existing_vins = {
            row[0] for row in con.execute(
                "SELECT DISTINCT vin FROM listings WHERE vin != '' AND vin IS NOT NULL"
            )
        }
        existing_stocks = {
            row[0] for row in con.execute(
                "SELECT DISTINCT stock_no FROM listings WHERE stock_no != '' AND stock_no IS NOT NULL"
            )
        }

    rows = []
    for l in listings:
        vin = l.get("vin") or ""
        stock = l.get("stock_no") or ""
        is_new = int(
            (vin and vin not in existing_vins) or
            (stock and stock not in existing_stocks) or
            (not vin and not stock)  # no ID = treat as new
        )
        rows.append((
            scraped_at,
            stock,
            vin,
            l.get("title", ""),
            l.get("dealer", ""),
            l.get("suburb", ""),
            l.get("price"),
            l.get("odometer"),
            l.get("colour", ""),
            l.get("variant", ""),
            l.get("url", ""),
            is_new,
            l.get("condition", "Demo"),
            json.dumps(l),
        ))

    with _conn() as con:
        con.executemany("""
            INSERT INTO listings
                (scraped_at, stock_no, vin, title, dealer, suburb, price,
                 odometer, colour, variant, url, is_new, condition, raw_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, rows)
        con.execute(
            "INSERT INTO snapshots (scraped_at, count) VALUES (?,?)",
            (scraped_at, len(listings))
        )


def get_latest_listings() -> list[dict]:
    """Return the most recent scrape's listings."""
    with _conn() as con:
        row = con.execute(
            "SELECT scraped_at FROM snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return []
        latest_at = row[0]
        rows = con.execute(
            """SELECT dealer, suburb, price, odometer, colour, variant,
                      stock_no, vin, url, scraped_at, is_new, condition
               FROM listings WHERE scraped_at = ?
               ORDER BY price ASC NULLS LAST""",
            (latest_at,)
        ).fetchall()
        cols = ["dealer", "suburb", "price", "odometer", "colour", "variant",
                "stock_no", "vin", "url", "scraped_at", "is_new", "condition"]
        return [dict(zip(cols, r)) for r in rows]


def load_history() -> list[dict]:
    """Return all listing rows for price history charts."""
    with _conn() as con:
        rows = con.execute(
            """SELECT dealer, suburb, price, odometer, colour, variant,
                      stock_no, vin, url, scraped_at, is_new, condition
               FROM listings
               ORDER BY scraped_at ASC"""
        ).fetchall()
        cols = ["dealer", "suburb", "price", "odometer", "colour", "variant",
                "stock_no", "vin", "url", "scraped_at", "is_new", "condition"]
        return [dict(zip(cols, r)) for r in rows]


def get_all_snapshots() -> list[dict]:
    """Return a summary of all scrape runs."""
    with _conn() as con:
        rows = con.execute(
            "SELECT scraped_at, count FROM snapshots ORDER BY id ASC"
        ).fetchall()
        return [{"scraped_at": r[0], "count": r[1]} for r in rows]
