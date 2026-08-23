import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB = Path("auction_sniper.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS lots(
id INTEGER PRIMARY KEY,
source_id TEXT UNIQUE,
auctioneer TEXT NOT NULL,
source_url TEXT NOT NULL,
image_url TEXT,
address TEXT NOT NULL,
postcode TEXT,
property_type TEXT,
auction_date TEXT,
lot_number TEXT,
status TEXT DEFAULT 'Live',
guide_price REAL,
target_price REAL,
hard_max_price REAL DEFAULT 250000,
annual_rent REAL,
gross_yield REAL,
tenure TEXT,
vat_status TEXT DEFAULT 'UNKNOWN',
option_to_tax TEXT DEFAULT 'UNKNOWN',
togc_status TEXT DEFAULT 'UNKNOWN',
legal_pack_status TEXT DEFAULT 'UNKNOWN',
legal_pack_url TEXT,
tenant_name TEXT,
lease_expiry TEXT,
break_dates TEXT,
rent_review_dates TEXT,
service_charge REAL,
service_charge_recoverable TEXT DEFAULT 'UNKNOWN',
rateable_value REAL,
epc_status TEXT DEFAULT 'UNKNOWN',
buyer_fees REAL,
area_classification TEXT,
pitch_classification TEXT,
location_score REAL,
area_score REAL,
relettability_score REAL,
tenant_score REAL,
lease_score REAL,
income_sustainability_score REAL,
property_score REAL,
sniper_score REAL,
comparable_sales_count INTEGER DEFAULT 0,
comparable_rents_count INTEGER DEFAULT 0,
market_rent_low REAL,
market_rent_high REAL,
risk_flags TEXT,
first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
last_seen TEXT DEFAULT CURRENT_TIMESTAMP,
last_changed TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scans(
id INTEGER PRIMARY KEY,
source TEXT NOT NULL,
status TEXT NOT NULL,
lots_seen INTEGER DEFAULT 0,
message TEXT,
checked_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

def connect():
    return sqlite3.connect(DB)

def init_db():
    with connect() as con:
        con.executescript(SCHEMA)

def upsert_lots(lots):
    if not lots:
        return
    now = datetime.now(timezone.utc).isoformat()
    allowed = {
        "source_id","auctioneer","source_url","image_url","address","postcode",
        "property_type","auction_date","lot_number","status","guide_price",
        "annual_rent","gross_yield","tenure","vat_status","option_to_tax",
        "togc_status","legal_pack_status","legal_pack_url","tenant_name","risk_flags"
    }
    with connect() as con:
        for lot in lots:
            row = {k:v for k,v in lot.items() if k in allowed}
            row["last_seen"] = now
            existing = con.execute(
                "SELECT id,guide_price,annual_rent,status,tenure,vat_status FROM lots WHERE source_id=?",
                (row["source_id"],)
            ).fetchone()
            if existing:
                old = existing[1:]
                new = tuple(row.get(k) for k in ["guide_price","annual_rent","status","tenure","vat_status"])
                changed = old != new
                sets = ", ".join(f"{k}=?" for k in row if k != "source_id")
                vals = [row[k] for k in row if k != "source_id"]
                if changed:
                    sets += ", last_changed=?"
                    vals.append(now)
                vals.append(row["source_id"])
                con.execute(f"UPDATE lots SET {sets} WHERE source_id=?", vals)
            else:
                row["first_seen"] = now
                row["last_changed"] = now
                cols = list(row)
                qs = ",".join("?" for _ in cols)
                con.execute(
                    f"INSERT INTO lots ({','.join(cols)}) VALUES ({qs})",
                    [row[c] for c in cols]
                )

def record_scan(source, status, lots_seen, message=""):
    with connect() as con:
        con.execute(
            "INSERT INTO scans(source,status,lots_seen,message) VALUES (?,?,?,?)",
            (source,status,lots_seen,message)
        )

def get_lots(max_price=250000, min_yield=10):
    with connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """SELECT * FROM lots
               WHERE (guide_price IS NULL OR guide_price <= ?)
               AND (gross_yield IS NULL OR gross_yield >= ?)
               ORDER BY COALESCE(sniper_score,0) DESC,
                        CASE WHEN gross_yield IS NULL THEN 1 ELSE 0 END,
                        gross_yield DESC,
                        last_changed DESC""",
            (max_price,min_yield)
        ).fetchall()
        return [dict(x) for x in rows]

def get_scan_status():
    with connect() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """SELECT s.* FROM scans s
               JOIN (SELECT source,MAX(id) id FROM scans GROUP BY source) x
               ON s.id=x.id ORDER BY s.source"""
        ).fetchall()
        return [dict(x) for x in rows]
