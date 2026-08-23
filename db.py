import sqlite3
from pathlib import Path
from datetime import datetime,timezone

DB=Path("auction_sniper_v2.db")
SCHEMA="""
CREATE TABLE IF NOT EXISTS lots(source_id TEXT PRIMARY KEY,auctioneer TEXT,source_url TEXT,address TEXT,image_url TEXT,postcode TEXT,property_type TEXT,lot_number TEXT,guide_price REAL,annual_rent REAL,gross_yield REAL,tenure TEXT,vat_status TEXT,togc_status TEXT,legal_pack_status TEXT,legal_pack_url TEXT,scanned_at TEXT);
CREATE TABLE IF NOT EXISTS source_status(source TEXT PRIMARY KEY,status TEXT,lots_seen INTEGER,message TEXT,checked_at TEXT);
"""
def connect(): return sqlite3.connect(DB)
def init_db():
    with connect() as con: con.executescript(SCHEMA)
def replace_snapshot(results):
    now=datetime.now(timezone.utc).isoformat()
    with connect() as con:
        con.execute("DELETE FROM lots"); con.execute("DELETE FROM source_status")
        for r in results:
            con.execute("INSERT INTO source_status VALUES (?,?,?,?,?)",(r.source,r.status,len(r.lots),r.message,now))
            for lot in r.lots:
                x=lot.as_dict()
                con.execute("INSERT OR REPLACE INTO lots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(x["source_id"],x["auctioneer"],x["source_url"],x["address"],x["image_url"],x["postcode"],x["property_type"],x["lot_number"],x["guide_price"],x["annual_rent"],x["gross_yield"],x["tenure"],x["vat_status"],x["togc_status"],x["legal_pack_status"],x["legal_pack_url"],now))
def count_all():
    with connect() as con: return con.execute("SELECT COUNT(*) FROM lots").fetchone()[0]
def get_lots(max_price=250000,min_yield=0,include_unknown=True):
    where=["(guide_price IS NULL OR guide_price<=?)"];params=[max_price]
    if min_yield>0:
        where.append("(gross_yield IS NULL OR gross_yield>=?)" if include_unknown else "gross_yield>=?");params.append(min_yield)
    with connect() as con:
        con.row_factory=sqlite3.Row
        q="SELECT * FROM lots WHERE "+" AND ".join(where)+" ORDER BY CASE WHEN gross_yield IS NULL THEN 1 ELSE 0 END,gross_yield DESC"
        return [dict(r) for r in con.execute(q,params)]
def get_sources():
    with connect() as con:
        con.row_factory=sqlite3.Row
        return [dict(r) for r in con.execute("SELECT * FROM source_status ORDER BY source")]
