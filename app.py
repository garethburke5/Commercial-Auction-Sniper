
import re, html, json, time
import base64
from io import BytesIO
import hashlib
from pathlib import Path
from urllib.parse import urljoin
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import streamlit as st
from bs4 import BeautifulSoup
from collector_enrichment import extract_particulars, merge_enrichment
try:
    from legal_pack_service import analyse_uploaded_pack
except Exception:
    analyse_uploaded_pack=None
try:
    from pypdf import PdfReader
except Exception:
    PdfReader=None

st.set_page_config(page_title="Auction Sniper", page_icon="🎯", layout="wide", initial_sidebar_state="collapsed")

BUILD = "V6.69-ACUITUS-STRUCTURED"
CACHE = Path("auction_sniper_cache.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AuctionSniper/5.0)"}
TIMEOUT = 10

# ---------------- VERIFIED SEED ----------------
# These are live commercial/mixed-use lots checked against the auctioneers'
# current public pages on 24 Aug 2026. The app always has useful data even
# if a live refresh source is temporarily unavailable.
EIG_KNOWN_PACKS = {
    "8 red street, carmarthen": "1433491",
}

SEED = [
    # Auction House London — complete current commercial/mixed-use block, 2/3 Sep 2026
    dict(source="Auction House London", lot="Lot 60", date="2026-09-02", address="97 St. Peters Street, St. Albans, Hertfordshire, AL1 3EN", guide=225000, rent=30000, tenure="Freehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/97-st-peters-street-st-albans-hertfordshire-al1-3en-359945", desc="Retail Property. Ground floor retail unit let producing £30,000 pa."),
    dict(source="Auction House London", lot="Lot 60A", date="2026-09-02", address="6 High Street, Hythe, Southampton, Hampshire, SO45 6AH", guide=110000, rent=15500, tenure="Freehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/6-high-street-hythe-southampton-hampshire-so45-6ah-362111", desc="Retail Property. Commercial unit and ancillary space let to Oxfam producing £15,500 pa."),
    dict(source="Auction House London", lot="Lot 60B", date="2026-09-02", address="6A High Street, Hythe, Southampton, Hampshire, SO45 6AH", guide=80000, rent=12500, tenure="Freehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/6a-high-street-hythe-southampton-hampshire-so45-6ah-362113", desc="Retail Property. Commercial unit and ancillary space let producing £12,500 pa."),
    dict(source="Auction House London", lot="Lot 61", date="2026-09-02", address="Unit SU8, 5 Jubilee Way, Scunthorpe, North Lincolnshire, DN15 6RB", guide=95000, rent=12500, tenure="Leasehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/unit-su8-5-jubilee-way-scunthorpe-north-lincolnshire-dn15-6rb-358590", desc="Retail Property. Commercial unit let producing £12,500 pa."),
    dict(source="Auction House London", lot="Lot 62", date="2026-09-02", address="9 College Walk, Rotherham, South Yorkshire, S60 1QB", guide=95000, rent=12500, tenure="Freehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/9-college-walk-rotherham-south-yorkshire-s60-1qb-358596", desc="Retail Property. Commercial unit let producing £12,500 pa."),
    dict(source="Auction House London", lot="Lot 62A", date="2026-09-02", address="709 Wimborne Road, Bournemouth, Dorset, BH9 2AU", guide=350000, rent=15000, tenure="Freehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/709-wimborne-road-bournemouth-dorset-bh9-2au-362596", desc="Retail Property. Retail/warehouse with two upper flats; retail under offer at £15,000 pa."),
    dict(source="Auction House London", lot="Lot 63", date="2026-09-02", address="29 Hervey Street, Lowestoft, Suffolk, NR32 2JG", guide=75000, rent=None, tenure="Freehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/29-hervey-street-lowestoft-suffolk-nr32-2jg-361511", desc="Mixed Use. Vacant ground-floor commercial unit with upper flat."),
    dict(source="Auction House London", lot="Lot 64", date="2026-09-02", address="13 Hope Street, Crook, County Durham, DL15 9HS", guide=175000, rent=25000, tenure="Freehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/13-hope-street-crook-county-durham-dl15-9hs-361002", desc="Retail Property. Double-fronted retail unit and office let at £25,000 pa."),
    dict(source="Auction House London", lot="Lot 65", date="2026-09-02", address="102-104 High Street, Redcar, Cleveland, TS10 3DL", guide=130000, rent=20000, tenure="Leasehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/102-104-high-street-redcar-cleveland-ts10-3dl-360993", desc="Retail Property. Double-fronted retail unit let producing £20,000 pa."),
    dict(source="Auction House London", lot="Lot 65A", date="2026-09-02", address="48 High East Street, Dorchester, Dorset, DT1 1HU", guide=120000, rent=None, tenure="Freehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/48-high-east-street-dorchester-dorset-dt1-1hu-361884", desc="Retail Property. Vacant commercial building."),
    dict(source="Auction House London", lot="Lot 66", date="2026-09-02", address="396 Forest Road, Walthamstow, London, E17 5JF", guide=500000, rent=None, tenure="Freehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/396-forest-road-walthamstow-london-e17-5jf-361976", desc="Mixed Use. Ground-floor retail unit with upper flat and planning potential."),
    dict(source="Auction House London", lot="Lot 66A", date="2026-09-02", address="179 Upton Lane, Forest Gate, London, E7 9PJ", guide=390000, rent=None, tenure="Freehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/179-upton-lane-forest-gate-london-e7-9pj-362815", desc="Retail Property. Vacant retail unit with upper flat."),
    dict(source="Auction House London", lot="Lot 67", date="2026-09-02", address="Foelas Residential Home, Station Road, Llanrug, Caernarfon, Gwynedd, LL55 4BE", guide=200000, rent=50000, tenure="Freehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/foelas-residential-home-station-road-llanrug-caernarfon-gwynedd-ll55-4be-360987", desc="Commercial Property. Care home let producing £50,000 pa."),
    dict(source="Auction House London", lot="Lot 68", date="2026-09-02", address="Electric House, Castle Street, Newcastle Emlyn, Carmarthenshire, SA38 9AF", guide=80000, rent=18840, tenure="Freehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/electric-house-castle-street-newcastle-emlyn-carmarthenshire-sa38-9af-359943", desc="Mixed Use. Retail unit and two flats fully let producing £18,840 pa."),
    dict(source="Auction House London", lot="Lot 69", date="2026-09-02", address="Unit 6A-6B South Middleton Base, Greenwell Road, Aberdeen, AB12 3AX", guide=500000, rent=None, tenure="Leasehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/unit-6a-6b-south-middleton-base-greenwell-road-aberdeen-ab12-3ax-361941", desc="Industrial Development. Vacant substantial industrial building."),
    dict(source="Auction House London", lot="Lot 70A", date="2026-09-02", address="94A Middleton Grange Shopping Centre, Hartlepool, Cleveland, TS24 7RW", guide=95000, rent=21000, tenure="Leasehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/94a-middleton-grange-shopping-centre-hartlepool-cleveland-ts24-7rw-360550", desc="Commercial Property. FRI lease at £21,000 pa rising to £25,000."),
    dict(source="Auction House London", lot="Lot 71", date="2026-09-02", address="21 Red Street, Carmarthen, Dyfed, SA31 1QL", guide=95000, rent=17000, tenure="Leasehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/21-red-street-carmarthen-dyfed-sa31-1ql-361340", desc="Retail Property. Ground-floor commercial unit let at £17,000 pa."),
    dict(source="Auction House London", lot="Lot 71A", date="2026-09-02", address="8 Red Street, Carmarthen, Dyfed, SA31 1QL", guide=180000, rent=34000, tenure="Freehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/8-red-street-carmarthen-dyfed-sa31-1ql-362265", desc="Retail Property. Let to Boots Opticians producing £34,000 pa."),
    dict(source="Auction House London", lot="Lot 72", date="2026-09-02", address="17-19 Umberston Street, Tower Hamlets, London, E1 1PY", guide=275000, rent=None, tenure="Leasehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/17-19-umberston-street-tower-hamlets-london-e1-1py-359974", desc="Commercial Property. Vacant ground/lower-ground commercial unit."),
    dict(source="Auction House London", lot="Lot 73", date="2026-09-02", address="Rear of 292 Weelsby Street, Grimsby, North East Lincolnshire, DN32 8AB", guide=25000, rent=4200, tenure="Freehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/rear-of-292-weelsby-street-grimsby-north-east-lincolnshire-dn32-8ab-355241", desc="Workshop & Retail. Commercial building and yard let at £4,200 pa."),
    dict(source="Auction House London", lot="Lot 74", date="2026-09-02", address="Unit 3 The Boathouse, Ocean Drive, Gillingham, Kent, ME7 1FT", guide=135000, rent=29988, tenure="Freehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/unit-3-the-boathouse-ocean-drive-gillingham-kent-me7-1ft-361080", desc="Retail Property. Commercial unit let at £29,988 pa."),
    dict(source="Auction House London", lot="Lot 75", date="2026-09-02", address="106 High Street, Redcar, Cleveland, TS10 3DL", guide=50000, rent=11880, tenure="Leasehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/106-high-street-redcar-cleveland-ts10-3dl-360996", desc="Retail Property. Ground-floor retail unit let at £11,880 pa."),
    dict(source="Auction House London", lot="Lot 76", date="2026-09-02", address="108 High Street, Redcar, Cleveland, TS10 3DL", guide=25000, rent=5000, tenure="Leasehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/108-high-street-redcar-cleveland-ts10-3dl-361001", desc="Retail Property. First-floor office let at £5,000 pa."),
    dict(source="Auction House London", lot="Lot 76A", date="2026-09-02", address="Unit 1 Masonic Hall, 64 Briggate, Brighouse, Calderdale, HD6 1EF", guide=9000, rent=None, tenure="Freehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/unit-1-masonic-hall-64-briggate-brighouse-calderdale-hd6-1ef-361598", desc="Commercial Property. Vacant 365 sq ft ground-floor commercial unit."),
    dict(source="Auction House London", lot="Lot 77", date="2026-09-02", address="The Vaults, Manor Road, Chatham, Kent, ME4 6HW", guide=50000, rent=None, tenure="Freehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/the-vaults-manor-road-chatham-kent-me4-6hw-360200", desc="Commercial-use vaults/tunnels, approx 4,337 sq ft, previously let for £25,000 pa."),
    dict(source="Auction House London", lot="Lot 78", date="2026-09-02", address="20-26 Hill Street, Wisbech, Cambridgeshire, PE13 1BA", guide=120000, rent=None, tenure="Freehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/20-26-hill-street-wisbech-cambridgeshire-pe13-1ba-360042", desc="Retail Property. Three vacant retail buildings with upper-floor conversion permission."),
    dict(source="Auction House London", lot="Lot 79", date="2026-09-02", address="Sandly Court, 39 Queens Road, Southport, Merseyside, PR9 9EX", guide=320000, rent=None, tenure="Freehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/sandly-court-39-queens-road-southport-merseyside-pr9-9ex-357930", desc="Commercial Development. Vacant former care home."),
    dict(source="Auction House London", lot="Lot 80", date="2026-09-02", address="Unit 3, 6A Alma Street, Taunton, Somerset, TA1 3AH", guide=5000, rent=None, tenure="Freehold", vat="UNKNOWN", url="https://auctionhouselondon.co.uk/lot/unit-3-6a-alma-street-taunton-somerset-ta1-3ah-361603", desc="Commercial Property. Vacant 236 sq ft ground-floor commercial unit."),

    # Savills — full verified current commercial section, 2 Sep 2026
    dict(source="Savills Auctions", lot="Lot 71", date="2026-09-02",
         address="22 Fillebrook Avenue, Enfield, EN1 3BB", guide=225000, rent=19000,
         tenure="Freehold", vat="UNKNOWN",
         url="https://auctions.savills.co.uk/auctions/2-september-2026-241/22-fillebrook-avenue-enfield-en1-3bb-23759",
         desc="Rarely available mixed-use investment. Retail unit and one-bedroom flat. Fully let to a laundrette. Lease expires 02.07.2030. Outstanding rent reviews. ERV approx £35,000 pa. High-footfall local parade."),
    dict(source="Savills Auctions", lot="Lot 72", date="2026-09-02",
         address="21 Broad Street, Bath BA1 5LN", guide=300000, rent=None,
         tenure="Freehold", vat="UNKNOWN",
         url="https://auctions.savills.co.uk/auctions/2-september-2026-241/21-broad-street-bath-ba1-5ln-23750",
         desc="Grade II listed mixed commercial/residential freehold. Ground-floor shop and basement approx 1,769 sq ft vacant; upper flats sold on leases. Located in Milsom Street Regeneration Quarter."),
    dict(source="Savills Auctions", lot="Lot 73", date="2026-09-02",
         address="26 Market Street, Crewe, Cheshire CW1 2EL", guide=135000, rent=15000,
         tenure="Freehold", vat="NOT APPLICABLE",
         url="https://auctions.savills.co.uk/auctions/2-september-2026-241/26-market-street-crewe-cheshire-cw1-2el-24071",
         desc="Freehold retail investment let on a new ten-year lease from March 2026, expiring March 2036. £15,000 pa rising to £17,000 pa in year four. VAT-free."),
    dict(source="Savills Auctions", lot="Lot 74", date="2026-09-02",
         address="Unit 2, 10-18 Queen Street, Barnsley, S70 1RJ", guide=400000, rent=53000,
         tenure=None, vat="UNKNOWN",
         url="https://auctions.savills.co.uk/auctions/2-september-2026-241/unit-2-10-18-queen-street-barnsley-s70-1rj-24606",
         desc="High-yielding retail investment. Retail unit and upper parts let to Barclays. Recently renewed ten-year lease expiring 31.12.2034. 8,912 sq ft. Prime pedestrianised pitch."),
    dict(source="Savills Auctions", lot="Lot 75", date="2026-09-02",
         address="67-83 Bridge Road, Northampton, NN1 1PD", guide=925000, rent=101780,
         tenure=None, vat="UNKNOWN",
         url="https://auctions.savills.co.uk/auctions/2-september-2026-241/67-83-bridge-road-northampton-nn1-1pd-24450",
         desc="Modern retail warehouse investment in prominent Northampton town-centre location. Semi-detached unit let to British Heart Foundation. Site approx 0.47 acres with dedicated parking."),
    dict(source="Savills Auctions", lot="Lot 76", date="2026-09-02",
         address="Chequer's Garage, Station Road, Petworth, GU28 0ES", guide=440000, rent=None,
         tenure="Freehold", vat="UNKNOWN",
         url="https://auctions.savills.co.uk/auctions/2-september-2026-241/chequers-garage-station-road-petworth-gu28-0es-24008",
         desc="Vacant freehold former showroom with two self-contained flats above. Approx 2,809 sq ft with parking for about six cars. Asset-management and development potential."),
    dict(source="Savills Auctions", lot="Lot 77", date="2026-09-02",
         address="106 Walcot Street, Bath BA1 5BG", guide=170000, rent=None,
         tenure="Freehold", vat="UNKNOWN",
         url="https://auctions.savills.co.uk/auctions/2-september-2026-241/106-walcot-street-bath-ba1-5bg-23752",
         desc="Vacant end-of-terrace commercial property arranged over basement, ground and two upper floors. Total GIA 1,103 sq ft. Ground/basement retail with ancillary upper parts. ERV £10,250 pa."),
    dict(source="Savills Auctions", lot="Lot 78", date="2026-09-02",
         address="Unit 5B, 10-18 Queen Street, Barnsley, S70 1RJ", guide=360000, rent=46750,
         tenure=None, vat="UNKNOWN",
         url="https://auctions.savills.co.uk/auctions/2-september-2026-241/unit-5b-10-18-queen-street-barnsley-s70-1rj-24659",
         desc="Retail unit and upper parts let to Holland & Barrett. Five-year lease expires 25.07.2029. Tenant in occupation 10+ years. 7,749 sq ft. Prime pedestrianised pitch."),
    dict(source="Savills Auctions", lot="Lot 79", date="2026-09-02",
         address="55 Cumberland Street, Hull, HU2 0PU", guide=300000, rent=39000,
         tenure="Freehold", vat="NOT APPLICABLE",
         url="https://auctions.savills.co.uk/auctions/2-september-2026-241/55-cumberland-street-hull-hu2-0pu-24478",
         desc="Freehold industrial investment comprising warehouse and offices over ground and first floors. 7,715 sq ft. Seven-year lease expiring 06.04.2033. VAT not applicable."),
    dict(source="Savills Auctions", lot="Lot 80", date="2026-09-02",
         address="54-56 Wallasey Road, Wallasey, CH45 4NW", guide=150000, rent=20000,
         tenure="Freehold", vat="UNKNOWN",
         url="https://auctions.savills.co.uk/auctions/2-september-2026-241/54-56-wallasey-road-wallasey-ch45-4nw-24663",
         desc="Double retail unit and upper parts let to Ski Lounge Limited with personal guarantors. Ten-year lease expiring 15.02.2034. August 2026 break option not exercised. Index-linked reviews."),
    dict(source="Savills Auctions", lot="Lot 81", date="2026-09-02",
         address="Unit 5A, 10-18 Queen Street, Barnsley, S70 1RJ", guide=270000, rent=38000,
         tenure=None, vat="UNKNOWN",
         url="https://auctions.savills.co.uk/auctions/2-september-2026-241/unit-5a-10-18-queen-street-barnsley-s70-1rj-24607",
         desc="Ground-floor retail unit let to TUI. Five-year lease expires 29.02.2028. 2026 break option not exercised. 1,862 sq ft. Prime pedestrianised pitch."),
    dict(source="Savills Auctions", lot="Lot 83", date="2026-09-02",
         address="Tutt Antiques, Angel Street, Petworth, GU28 0BQ", guide=215000, rent=None,
         tenure="Freehold", vat="UNKNOWN",
         url="https://auctions.savills.co.uk/auctions/2-september-2026-241/tutt-antiques-angel-street-petworth-gu28-0bq-24604",
         desc="Vacant freehold mid-terrace commercial property across two floors, approx 1,356 sq ft. Asset-management and alternative-use potential."),
    dict(source="Savills Auctions", lot="Lot 84", date="2026-09-02",
         address="Adult Education Centre, 32-46 King Street, Alfreton, Derbyshire DE55 7DQ", guide=525000, rent=None,
         tenure=None, vat="APPLICABLE",
         url="https://auctions.savills.co.uk/auctions/2-september-2026-241/adult-education-centre-32-46-king-street-alfreton-derbyshire-de55-7dq-23722",
         desc="Vacant former educational centre / office opportunity. Approx 11,634 sq ft with 20 parking spaces. VAT applicable. Asset-management/change-of-use potential."),
    dict(source="Savills Auctions", lot="Lot 85", date="2026-09-02",
         address="Land On The North Side of The Borough, Ongar, CM5 9QU", guide=525000, rent=None,
         tenure="Freehold", vat="NOT APPLICABLE",
         url="https://auctions.savills.co.uk/auctions/2-september-2026-241/land-on-the-north-side-of-the-borough-ongar-cm5-9qu-24771",
         desc="Vacant freehold open-storage commercial site approx 1.2 acres, with consent for vehicle parking and storage. VAT not applicable."),
    dict(source="Savills Auctions", lot="Lot 86", date="2026-09-02",
         address="1 Holtspur Parade, Heath Road, Beaconsfield, HP9 1DA", guide=80000, rent=10000,
         tenure="Leasehold", vat="UNKNOWN",
         url="https://auctions.savills.co.uk/auctions/2-september-2026-241/1-holtspur-parade-heath-road-beaconsfield-hp9-1da-24662",
         desc="Ground-floor retail investment let to a cafe. Ten-year lease expiring 17.12.2027. Popular parade. Asset-management potential via renewal."),
    dict(source="Savills Auctions", lot="Lot 87", date="2026-09-02",
         address="Swan Mill, 10a Swan Street, West Malling, ME19 6LP", guide=330000, rent=None,
         tenure="Freehold", vat="UNKNOWN",
         url="https://auctions.savills.co.uk/auctions/2-september-2026-241/swan-mill-10a-swan-street-west-malling-me19-6lp-24605",
         desc="Vacant freehold former mill, approx 2,551 sq ft across three floors, with hardstanding and parking for 2-3 cars. Alternative-use potential."),
    dict(source="Savills Auctions", lot="Lot 88", date="2026-09-02",
         address="Unit 5, The Marsh, Hythe, SO45 6AJ", guide=120000, rent=15000,
         tenure=None, vat="UNKNOWN",
         url="https://auctions.savills.co.uk/auctions/2-september-2026-241/unit-5-the-marsh-hythe-so45-6aj-24628",
         desc="Ground-floor retail investment fully let to Domino's. Twenty-year lease expiring 13.09.2029. 2024 rent review outstanding. Popular parade."),
    dict(source="Savills Auctions", lot="Lot 89", date="2026-09-02",
         address="Unit 4, The Marsh, Hythe, SO45 6AJ", guide=120000, rent=15500,
         tenure=None, vat="UNKNOWN",
         url="https://auctions.savills.co.uk/auctions/2-september-2026-241/unit-4-the-marsh-hythe-so45-6aj-24631",
         desc="Ground-floor retail investment let to Dawkins and Lodge Limited. Ten-year lease expiring 02.08.2029. Long-standing occupier 15+ years. 2024 rent review outstanding."),
    dict(source="Savills Auctions", lot="Lot 90", date="2026-09-02",
         address="Unit 3, The Marsh, Hythe, SO45 6AJ", guide=120000, rent=15000,
         tenure=None, vat="UNKNOWN",
         url="https://auctions.savills.co.uk/auctions/2-september-2026-241/unit-3-the-marsh-hythe-so45-6aj-24632",
         desc="Ground-floor retail investment let to a takeaway. Ten-year lease expiring 28.09.2030. Long-standing occupier 20+ years. 2025 rent review outstanding."),
    dict(source="Savills Auctions", lot="Lot 93", date="2026-09-02",
         address="Unit 1, 33/35 Bridge Street, Haverfordwest SA61 2AL", guide=110000, rent=13600,
         tenure="Freehold", vat="NOT APPLICABLE",
         url="https://auctions.savills.co.uk/auctions/2-september-2026-241/unit-1-3335-bridge-street-haverfordwest-sa61-2al-24017",
         desc="Freehold shop investment in pedestrianised retail thoroughfare. Let to British Red Cross on lease expiring 2032. VAT not applicable."),
    dict(source="Savills Auctions", lot="Lot 95", date="2026-09-02",
         address="Unit 3, 15 John Street, Carmarthen, Dyfed, SA31 1QT", guide=277000, rent=65000,
         tenure=None, vat="UNKNOWN",
         url="https://auctions.savills.co.uk/auctions/2-september-2026-241/unit-3-15-john-street-carmarthen-dyfed-sa31-1qt-24524",
         desc="Retail unit and upper parts let to Superdrug Stores plc holding over. Heads of terms agreed for a new five-year lease subject to contract. Tenant in occupation 35+ years."),
    dict(source="Savills Auctions", lot="Lot 96", date="2026-09-02",
         address="15 Red Street, Carmarthen, Dyfed, SA31 1QL", guide=270000, rent=52500,
         tenure=None, vat="UNKNOWN",
         url="https://auctions.savills.co.uk/auctions/2-september-2026-241/15-red-street-carmarthen-dyfed-sa31-1ql-24525",
         desc="Retail unit and upper parts let to Trespass Investments Limited. Six-year lease expiring 10.07.2031. Approx 3,553 sq ft. Tenant in occupation 14+ years."),
    dict(source="Savills Auctions", lot="Lot 98", date="2026-09-02",
         address="66-70 High Street, Mexborough, South Yorkshire, S64 9AU", guide=140000, rent=25600,
         tenure=None, vat="UNKNOWN",
         url="https://auctions.savills.co.uk/auctions/2-september-2026-241/66-70-high-street-mexborough-south-yorkshire-s64-9au-24591",
         desc="High-yielding multi-let retail investment. Three retail units and upper parts, fully let to four tenants. Approx 3,423 sq ft. Development potential to upper parts."),

    # Bond Wolfe — complete qualifying current order-of-sale subset, 10 Sep 2026
    dict(source="Bond Wolfe", lot='Lot 3', date="2026-09-10", address='Halescroft Centre, Halescroft Square, Northfield, Birmingham, B31 1HF', guide=250000, rent=None, tenure="Freehold", vat="UNKNOWN", url='https://www.bondwolfe.com/auctions/properties/357337-property-auction-birmingham/', desc='Commercial Vacant / Land Development. Former youth centre and development land.', image='https://cdn.eigpropertyauctions.co.uk/ams/images/243/auction/3451/2787095_web_medium'),
    dict(source="Bond Wolfe", lot='Lot 6', date="2026-09-10", address='8 Albert Walk, Harborne, Birmingham, B17 0AR', guide=None, rent=None, tenure="Freehold", vat="UNKNOWN", url='https://www.bondwolfe.com/auctions/properties/357311-property-auction-birmingham/', desc='Commercial Investment. Retail investment in Harborne.', image='https://cdn.eigpropertyauctions.co.uk/ams/images/243/auction/3451/2784429_web_medium'),
    dict(source="Bond Wolfe", lot='Lot 7', date="2026-09-10", address='10-12 Albert Walk, Harborne, Birmingham, B17 0AR', guide=None, rent=None, tenure="Freehold", vat="UNKNOWN", url='https://www.bondwolfe.com/auctions/properties/357324-property-auction-birmingham/', desc='Commercial Investment. Retail investment in Harborne.', image='https://cdn.eigpropertyauctions.co.uk/ams/images/243/auction/3451/2784432_web_medium'),
    dict(source="Bond Wolfe", lot='Lot 8', date="2026-09-10", address='19 & 21 Albert Road, Harborne, Birmingham, B17 0AP', guide=None, rent=None, tenure="Freehold", vat="UNKNOWN", url='https://www.bondwolfe.com/auctions/properties/357204-property-auction-birmingham/', desc='Commercial Investment. Retail investment in Harborne.', image='https://cdn.eigpropertyauctions.co.uk/ams/images/243/auction/3451/2781856_web_medium'),
    dict(source="Bond Wolfe", lot='Lot 9', date="2026-09-10", address='23-25 Albert Road, Harborne, Birmingham, B17 0AP', guide=None, rent=None, tenure="Freehold", vat="UNKNOWN", url='https://www.bondwolfe.com/auctions/properties/357205-property-auction-birmingham/', desc='Commercial Vacant. Retail unit in Harborne.', image='https://cdn.eigpropertyauctions.co.uk/ams/images/243/auction/3451/2781878_web_medium'),
    dict(source="Bond Wolfe", lot='Lot 10', date="2026-09-10", address='11 Harborne Park Road, Harborne, Birmingham, B17 0DE', guide=None, rent=None, tenure="Freehold", vat="UNKNOWN", url='https://www.bondwolfe.com/auctions/properties/357073-property-auction-birmingham/', desc='Commercial Investment. Retail investment in Harborne.', image='https://cdn.eigpropertyauctions.co.uk/ams/images/243/auction/3451/2780524_web_medium'),
    dict(source="Bond Wolfe", lot='Lot 11', date="2026-09-10", address='13 Harborne Park Road, Harborne, Birmingham, B17 0DE', guide=125000, rent=6000, tenure="Freehold", vat="UNKNOWN", url='https://www.bondwolfe.com/auctions/properties/357075-property-auction-birmingham/', desc='Commercial Investment. Freehold retail investment.', image='https://cdn.eigpropertyauctions.co.uk/ams/images/243/auction/3451/2780561_web_medium'),
    dict(source="Bond Wolfe", lot='Lot 12', date="2026-09-10", address='Skilts School, Gorcott Hill, Beoley, Redditch, B98 9ET', guide=None, rent=None, tenure="Freehold", vat="UNKNOWN", url='https://www.bondwolfe.com/auctions/properties/357076-property-auction-beoley/', desc='Commercial Vacant / Land Development. Former school.', image='https://cdn.eigpropertyauctions.co.uk/ams/images/243/auction/3451/2780580_web_medium'),
    dict(source="Bond Wolfe", lot='Lot 25', date="2026-09-10", address='55-57 High Street, Bromsgrove, Worcestershire, B61 8AJ', guide=None, rent=None, tenure="Freehold", vat="UNKNOWN", url='https://www.bondwolfe.com/auctions/properties/362046-property-auction-bromsgrove/', desc='Mixed Use. Town-centre mixed-use investment.', image='https://cdn.eigpropertyauctions.co.uk/ams/images/243/auction/3451/2836090_web_medium'),
    dict(source="Bond Wolfe", lot='Lot 36', date="2026-09-10", address='The Staff of Life, Main Street, Mowsley, Lutterworth, Leicestershire, LE17 6NT', guide=None, rent=None, tenure="Freehold", vat="UNKNOWN", url='https://www.bondwolfe.com/auctions/properties/357042-property-auction-lutterworth/', desc='Commercial Vacant. Pub/restaurant with living accommodation.', image='https://cdn.eigpropertyauctions.co.uk/ams/images/243/auction/3451/2780232_web_medium'),
    dict(source="Bond Wolfe", lot='Lot 70', date="2026-09-10", address='95-99 Three Shires Oak Road, Bearwood, Smethwick, B67 5BT', guide=495000, rent=None, tenure="Freehold", vat="UNKNOWN", url='https://www.bondwolfe.com/auctions/properties/362266-property-auction-smethwick/', desc='Mixed Use. Vacant mixed-use building with flats.', image='https://cdn.eigpropertyauctions.co.uk/ams/images/243/auction/3451/2838756_web_medium'),
    dict(source="Bond Wolfe", lot='Lot 119', date="2026-09-10", address='418-422 Moseley Road, Balsall Heath, Birmingham, B12 9AT', guide=None, rent=None, tenure="Freehold", vat="UNKNOWN", url='https://www.bondwolfe.com/auctions/properties/362478-property-auction-birmingham/', desc='Mixed Use. Mixed-use investment.', image='https://cdn.eigpropertyauctions.co.uk/ams/images/243/auction/3451/2843239_web_medium'),
    dict(source="Bond Wolfe", lot='Lot 124', date="2026-09-10", address='32 Snow Hill, Wolverhampton, WV2 4AG', guide=None, rent=None, tenure="Freehold", vat="UNKNOWN", url='https://www.bondwolfe.com/auctions/properties/362254-property-auction-wolverhampton/', desc='Commercial Investment. Retail premises.', image='https://cdn.eigpropertyauctions.co.uk/ams/images/243/auction/3451/2838443_web_medium'),
    dict(source="Bond Wolfe", lot='Lot 131', date="2026-09-10", address='33-35 & 33A Cape Hill, Smethwick, West Midlands, B66 4RX', guide=175000, rent=17400, tenure="Freehold", vat="UNKNOWN", url='https://www.bondwolfe.com/auctions/properties/360362-property-auction-smethwick/', desc='Mixed Use. Part investment/part vacant; rent £17,400 pa.', image='https://cdn.eigpropertyauctions.co.uk/ams/images/243/auction/3451/2819077_web_medium'),
    dict(source="Bond Wolfe", lot='Lot 135', date="2026-09-10", address='51 & 51A Blackwell Street, Kidderminster, DY10 2EE', guide=140000, rent=None, tenure="Freehold", vat="UNKNOWN", url='https://www.bondwolfe.com/auctions/properties/361360-property-auction-kidderminster/', desc='Commercial Investment / Mixed Use.', image='https://cdn.eigpropertyauctions.co.uk/ams/images/243/auction/3451/2827968_web_medium'),
    dict(source="Bond Wolfe", lot='Lot 139', date="2026-09-10", address='159 Wolverhampton Street, Dudley, West Midlands, DY1 3AH', guide=None, rent=None, tenure="Freehold", vat="UNKNOWN", url='https://www.bondwolfe.com/auctions/properties/361062-property-auction-dudley/', desc='Commercial Vacant / Residential Vacant. Retail/showroom with flats.', image='https://cdn.eigpropertyauctions.co.uk/ams/images/243/auction/3451/2824293_web_medium'),
    dict(source="Bond Wolfe", lot='Lot 141', date="2026-09-10", address='Unit 1, 11-17 Worcester Street, Kidderminster, DY10 1EA', guide=110000, rent=13000, tenure="Freehold", vat="UNKNOWN", url='https://www.bondwolfe.com/auctions/properties/362054-property-auction-kidderminster/', desc='Commercial Investment. Retail investment producing £13,000 pa.', image='https://cdn.eigpropertyauctions.co.uk/ams/images/243/auction/3451/2836105_web_medium'),
    dict(source="Bond Wolfe", lot='Lot 147', date="2026-09-10", address='United Reform Church, Dodington, Whitchurch, Shropshire, SY13 1DZ', guide=None, rent=None, tenure="Freehold", vat="UNKNOWN", url='https://www.bondwolfe.com/auctions/properties/362298-property-auction-whitchurch/', desc='Commercial Vacant / Renovation. Historic building with conversion consent.', image='https://cdn.eigpropertyauctions.co.uk/ams/images/243/auction/3451/2839199_web_medium'),
    dict(source="Bond Wolfe", lot='Lot 172', date="2026-09-10", address='Former Three Tuns, 34 High Street, Alcester, Warwickshire, B49 5AB', guide=50000, rent=None, tenure="Freehold", vat="UNKNOWN", url='https://www.bondwolfe.com/auctions/properties/362472-property-auction-alcester/', desc='Commercial Vacant / Renovation. Fire-damaged former public house.'),
    dict(source="Bond Wolfe", lot='Lot 179', date="2026-09-10", address='25 Ladywell Road, Tunstall, Stoke-on-Trent, ST6 5DE', guide=None, rent=None, tenure="Freehold", vat="UNKNOWN", url='https://www.bondwolfe.com/auctions/properties/362311-property-auction-stoke-on-trent/', desc='Commercial Vacant. Retail premises with planning permission.', image='https://cdn.eigpropertyauctions.co.uk/ams/images/243/auction/3451/2840968_web_medium'),

    # Barnard Marcus — verified current commercial/mixed-use lots, 10 Sep 2026
    dict(source="Barnard Marcus", lot="Lot 21", date="2026-09-10", address="2 Rye Lane, Peckham, London, SE15 5BS", guide=545000, rent=48573, tenure="Freehold", vat="UNKNOWN", url="https://www.barnardmarcusauctions.co.uk/auctions/10-september-2026/716501/", desc="Mixed-use investment with ground-floor casino and two flats; rent £48,573 pa."),
    dict(source="Barnard Marcus", lot="Lot 22", date="2026-09-10", address="82 Uxbridge Road, Shepherds Bush, London, W12 8LR", guide=430000, rent=36000, tenure="Freehold", vat="UNKNOWN", url="https://www.barnardmarcusauctions.co.uk/auctions/10-september-2026/716502/", desc="Mixed-use investment with ground-floor shop; rent £36,000 pa."),
    dict(source="Barnard Marcus", lot="Lot 31", date="2026-09-10", address="Laser House, 75-79 Guildford Street, Chertsey, Surrey, KT16 9AS", guide=545000, rent=12000, tenure="Freehold", vat="UNKNOWN", url="https://www.barnardmarcusauctions.co.uk/auctions/10-september-2026/716897/", desc="Mixed-use town-centre building approx 6,311 sq ft; mostly vacant, one retail unit let at £12,000 pa."),
    dict(source="Barnard Marcus", lot="Lot 211", date="2026-09-10", address="499 Saffron Lane, Leicester, Leicestershire, LE2 6UQ", guide=430000, rent=None, tenure="Freehold", vat="APPLICABLE", url="https://www.barnardmarcusauctions.co.uk/auctions/10-september-2026/717996/", desc="Former neighbourhood housing office approx 10,936 sq ft with planning for three retail units; VAT payable."),

    # Auction House regional — verified live September commercial lots
    dict(source="Auction House East Anglia", lot="Lot 115", date="2026-09-09",
         address="102 High Street, Lowestoft, Suffolk NR32 1XW",
         guide=50000, rent=None, tenure=None, vat="UNKNOWN",
         url="https://www.auctionhouse.co.uk/eastanglia/auction/lot/151798", image="https://www.auctionhouse.co.uk/lot-image/921603?w=670",
         desc="Commercial property; former retail gallery with live/work conversion consent."),
    dict(source="Auction House East Anglia", lot="Lot 123", date="2026-09-09",
         address="23A South Quay, Great Yarmouth, Norfolk NR30 2RG",
         guide=30000, rent=None, tenure="Freehold", vat="UNKNOWN",
         url="https://www.auctionhouse.co.uk/eastanglia/auction/lot/151516", image="https://www.auctionhouse.co.uk/lot-image/917891?w=670",
         desc="Freehold two-storey office building with development potential."),
    dict(source="Auction House East Anglia", lot="Lot 114", date="2026-09-09",
         address="2 The Walk, Beccles, Suffolk NR34 9AJ",
         guide=375000, rent=None, tenure="Freehold", vat="UNKNOWN",
         url="https://www.auctionhouse.co.uk/eastanglia/auction/lot/151791", image="https://www.auctionhouse.co.uk/lot-image/921518?w=670",
         desc="Substantial town-centre retail premises with parking; approx. 6,873 sq ft / 638.59 sq m."),
    dict(source="Auction House East Anglia", lot="Lot 62", date="2026-09-09",
         address="Romar House, 12 Faraday Road, Leigh-On-Sea, Essex SS9 5JU",
         guide=800000, rent=None, tenure="Freehold", vat="UNKNOWN",
         url="https://www.auctionhouse.co.uk/eastanglia/auction/lot/151501", image="https://www.auctionhouse.co.uk/lot-image/917631?w=670",
         desc="Freehold light-industrial property."),
    dict(source="Auction House West Yorkshire", lot="Lot TBC", date="2026-09-09",
         address="Poplar Products, Ramshead Approach, Leeds, West Yorkshire LS14 1LR",
         guide=115000, rent=None, tenure=None, vat="UNKNOWN",
         url="https://www.auctionhouse.co.uk/westyorkshire/auction/lot/152101", image="https://www.auctionhouse.co.uk/lot-image/925288?w=670",
         desc="Detached industrial facility with offices and yard; approx. 30,742 sq ft / 2,856 sq m."),
    dict(source="Auction House West Yorkshire", lot="Lot TBC", date="2026-09-09",
         address="16 Station Road / 2 Wood Street, Horsforth, Leeds, West Yorkshire LS18 5NR",
         guide=165000, rent=None, tenure=None, vat="UNKNOWN",
         url="https://www.auctionhouse.co.uk/westyorkshire/auction/lot/151599", image="https://www.auctionhouse.co.uk/lot-image/919095?w=670",
         desc="Commercial property in Horsforth."),
    dict(source="Auction House West Yorkshire", lot="Lot TBC", date="2026-09-09",
         address="3-5 High Street, Yeadon, Leeds, West Yorkshire LS19 7SP",
         guide=238000, rent=None, tenure=None, vat="UNKNOWN",
         url="https://www.auctionhouse.co.uk/westyorkshire/auction/lot/151605", image="https://www.auctionhouse.co.uk/lot-image/919155?w=670",
         desc="Vacant prominent high-street former restaurant with upper-floor residential conversion consent."),
    dict(source="Auction House West Yorkshire", lot="Lot TBC", date="2026-09-09",
         address="Land and buildings, South side of Station Road, Dunscroft, Doncaster, South Yorkshire DN7 4DY",
         guide=170000, rent=0, tenure=None, vat="UNKNOWN",
         url="https://www.auctionhouse.co.uk/westyorkshire/auction/lot/151636", image="https://www.auctionhouse.co.uk/lot-image/919540?w=670",
         desc="Former supermarket approx. 17,980 sq ft / 1,670 sq m; charity occupier in situ paying no rent."),
    dict(source="Auction House Sussex & Hampshire", lot="Lot 15", date="2026-09-09",
         address="Auckland House, 55 St. Ronans Road, Southsea, Hampshire, PO4 0PP",
         guide=475000, rent=None, tenure="Freehold", vat="UNKNOWN",
         url="https://www.auctionhouse.co.uk/sussexandhampshire/auction/lot/151683", image="https://www.auctionhouse.co.uk/lot-image/920193?w=670",
         desc="Vacant freehold former care home/commercial building with consent for 12-bedroom HMO."),

    dict(source="Auction House East Anglia", lot="Lot 19", date="2026-09-09", address="46 Wells Road, Fakenham, Norfolk NR21 9AA", guide=250000, rent=24600, tenure="Freehold", vat="UNKNOWN", url="https://www.auctionhouse.co.uk/eastanglia/auction/lot/151473", image="https://www.auctionhouse.co.uk/lot-image/917043?w=670", desc="Office investment approx 1,200 sq ft let to established tenants producing £24,600 pa."),
    dict(source="Auction House East Anglia", lot="Lot 38", date="2026-09-09", address="The Old Dairy, Pound Lane, Heacham, King's Lynn, Norfolk PE31 7ET", guide=250000, rent=None, tenure="Freehold", vat="UNKNOWN", url="https://www.auctionhouse.co.uk/eastanglia/auction/lot/151800", image="https://www.auctionhouse.co.uk/lot-image/921627?w=670", desc="Commercial Development. Freehold commercial/development property."),
    dict(source="Auction House East Anglia", lot="Lot 99", date="2026-09-09", address="Reliant House, Angel Lane, Fore Street, Ipswich, Suffolk IP4 1JX", guide=500000, rent=51140, tenure="Freehold", vat="UNKNOWN", url="https://www.auctionhouse.co.uk/eastanglia/auction/lot/151749", image="https://www.auctionhouse.co.uk/lot-image/921063?w=670", desc="Mixed Use. Offices and flats approx 6,643 sq ft; current/estimated income £51,140 pa."),
    dict(source="Auction House South West", lot="Lot 10", date="2026-09-09", address="13 Market Jew Street, Penzance, Cornwall TR18 2HN", guide=140000, rent=None, tenure="Freehold", vat="UNKNOWN", url="https://www.auctionhouse.co.uk/southwest/auction/lot/151562", image="https://www.auctionhouse.co.uk/lot-image/918620?w=670", desc="Commercial Property. Vacant Grade II listed retail premises in prime Penzance retail area."),

    # Pugh / BTG Eddisons — verified current commercial/mixed-use, 27 Aug 2026
    dict(source="Pugh / BTG Eddisons", lot='Lot 111', date="2026-08-27", address='Masonic Hall, 33 King Street, Duffield, Belper, Derbyshire DE56 4EU', guide=160000, rent=None, tenure=None, vat="UNKNOWN", url='https://www.btgeddisonspropertyauctions.com/auctions/live-stream/august-2026?auction_id=17', desc='Commercial Property. Masonic hall / commercial premises.'),
    dict(source="Pugh / BTG Eddisons", lot='Lot 132', date="2026-08-27", address='9 Manchester Road, Audenshaw, Manchester M34 5PZ', guide=185000, rent=None, tenure=None, vat="UNKNOWN", url='https://www.btgeddisonspropertyauctions.com/properties/202605060832sq_hdck-280526/for-auction-manchester', desc='Mixed Use. Commercial shop, two flats and double garage; part-let/part-vacant; ERV circa £26,000 pa.'),
    dict(source="Pugh / BTG Eddisons", lot='Lot 133', date="2026-08-27", address='207 Victoria Avenue, and First and Second Floors 205 Victoria Avenue, Manchester M9 0RA', guide=185000, rent=None, tenure=None, vat="UNKNOWN", url='https://www.btgeddisonspropertyauctions.com/auctions/live-stream/august-2026?auction_id=17', desc='Commercial Property. Approx 1,970 sq ft commercial premises.'),
    dict(source="Pugh / BTG Eddisons", lot='Lot 170', date="2026-08-27", address='Maclins Depot, Unit 2, Station Road, South Molton, Devon EX36 3LJ', guide=150000, rent=6780, tenure=None, vat="UNKNOWN", url='https://www.btgeddisonspropertyauctions.com/properties/202607211014sq_kwai-270826/for-auction-south-molton', desc='Commercial Development. Freehold commercial depot approx 3,931 sq ft; part let £6,780 pa.'),
    dict(source="Pugh / BTG Eddisons", lot='Lot 195', date="2026-08-27", address='The Grand Hotel, 13 Market Street, Radcliffe, Manchester, Lancashire M26 1GF', guide=None, rent=None, tenure=None, vat="UNKNOWN", url='https://www.btgeddisonspropertyauctions.com/auctions/live-stream/august-2026?auction_id=17', desc='Hotel / commercial opportunity.'),
    dict(source="Pugh / BTG Eddisons", lot='Lot 196', date="2026-08-27", address='15 - 23 Percy Street, Stoke-On-Trent, Staffordshire ST1 1NA', guide=None, rent=None, tenure=None, vat="UNKNOWN", url='https://www.btgeddisonspropertyauctions.com/properties/202607231641sq_tkoe-300926/for-auction-stoke-on-trent', desc='Commercial Property.'),
    dict(source="Pugh / BTG Eddisons", lot='Lot 201', date="2026-08-27", address='63 George Street, Walsall, West Midlands WS1 1RS', guide=60000, rent=None, tenure=None, vat="UNKNOWN", url='https://www.btgeddisonspropertyauctions.com/auctions/live-stream/august-2026?auction_id=17', desc='Commercial Property. Grade II listed commercial unit with mixed-use potential.'),
    dict(source="Pugh / BTG Eddisons", lot='Lot 216', date="2026-08-27", address='2 & 2a High Street, St. Asaph, Denbighshire LL17 0RD', guide=60000, rent=None, tenure=None, vat="UNKNOWN", url='https://www.btgeddisonspropertyauctions.com/auctions/live-stream/august-2026?auction_id=17', desc='Mixed Use. Ground-floor retail unit and first-floor flat.'),
    dict(source="Pugh / BTG Eddisons", lot='Lot 218', date="2026-08-27", address='29 & 31/33 Mostyn Avenue, Llandudno, Conwy LL30 1YS', guide=495000, rent=43000, tenure=None, vat="UNKNOWN", url='https://www.pugh-auctions.com/property/202607141332sq_0jra', desc='Commercial Property. Two adjoining retail investments producing approx £43,000 pa.'),
    dict(source="Pugh / BTG Eddisons", lot='Lot 219', date="2026-08-27", address='Land at Hathershaw Lane, Oldham, Lancashire OL8 3EU', guide=60000, rent=None, tenure=None, vat="UNKNOWN", url='https://www.btgeddisonspropertyauctions.com/auctions/live-stream/august-2026?auction_id=17', desc='Commercial income land. Advertising display site, majority let on a new ten-year lease.'),
    dict(source="Pugh / BTG Eddisons", lot='Lot 220', date="2026-08-27", address='77 Manchester Road, Altrincham, Cheshire WA14 4RJ', guide=235000, rent=None, tenure=None, vat="UNKNOWN", url='https://www.btgeddisonspropertyauctions.com/auctions/live-stream/august-2026?auction_id=17', desc='Commercial Property. Retail investment let to hot-food operator.'),
    dict(source="Pugh / BTG Eddisons", lot='Lot 221', date="2026-08-27", address='8 Hampton Road, Failsworth, Manchester, Lancashire M35 9HT', guide=295000, rent=None, tenure=None, vat="UNKNOWN", url='https://www.btgeddisonspropertyauctions.com/auctions/live-stream/august-2026?auction_id=17', desc='Mixed Use. Convenience shop with residential accommodation.'),
    dict(source="Pugh / BTG Eddisons", lot='Lot 252', date="2026-08-27", address='Unit 4, Bansons Yard, High Street, Ongar, Essex CM5 9AA', guide=None, rent=None, tenure=None, vat="UNKNOWN", url='https://www.btgeddisonspropertyauctions.com/auctions/live-stream/august-2026?auction_id=17', desc='Commercial Development. Commercial office space with development potential.'),
    dict(source="Pugh / BTG Eddisons", lot='Lot 253', date="2026-08-27", address='502 Sutton Road, Southend-On-Sea, Essex', guide=185000, rent=16000, tenure=None, vat="UNKNOWN", url='https://www.btgeddisonspropertyauctions.com/auctions/live-stream/august-2026?auction_id=17', desc='Mixed Use. Ground-floor shop and flat; current income approx £16,000 pa.'),
    dict(source="Pugh / BTG Eddisons", lot='Lot 272', date="2026-08-27", address='186 Selborne Street, Preston, Lancashire PR1 4LB', guide=120000, rent=None, tenure=None, vat="UNKNOWN", url='https://www.btgeddisonspropertyauctions.com/auctions/live-stream/august-2026?auction_id=17', desc='Mixed Use. Ground-floor retail unit and first-floor flat.'),
    dict(source="Pugh / BTG Eddisons", lot='Lot 276', date="2026-08-27", address='27 Market Square, Kirkby Stephen, Cumbria', guide=None, rent=None, tenure=None, vat="UNKNOWN", url='https://www.btgeddisonspropertyauctions.com/auctions/live-stream/august-2026?auction_id=17', desc='Retail Property.'),
    dict(source="Pugh / BTG Eddisons", lot='Lot 280', date="2026-08-27", address='10 Brunswick Street, Stoke-On-Trent, Staffordshire ST1 1DR', guide=250000, rent=39900, tenure=None, vat="UNKNOWN", url='https://www.btgeddisonspropertyauctions.com/auctions/live-stream/august-2026?auction_id=17', desc='Mixed Use investment. Retail unit plus accommodation producing £39,900 pa.'),
    dict(source="Pugh / BTG Eddisons", lot='Lot 281', date="2026-08-27", address='72A & 72B London Road, Chesterton, Newcastle, Staffordshire ST5 7DY', guide=225000, rent=None, tenure=None, vat="UNKNOWN", url='https://www.btgeddisonspropertyauctions.com/auctions/live-stream/august-2026?auction_id=17', desc='Mixed Use. Substantial prominent freehold mixed-use property.'),
    dict(source="Pugh / BTG Eddisons", lot='Lot 283', date="2026-08-27", address='Unit 2, Paxton Street, Hanley, Stoke-On-Trent', guide=None, rent=None, tenure=None, vat="UNKNOWN", url='https://www.btgeddisonspropertyauctions.com/auctions/live-stream/august-2026?auction_id=17', desc='Mixed Use / commercial office premises with development potential.'),

    # Strettons — current 10 Sep 2026 commercial catalogue baseline
    dict(source="Strettons", lot='Lot 6', date="2026-09-10", address='1 Bruce Grove, Tottenham, London, Haringey, N17 6RA', guide=800000, rent=None, tenure=None, vat="UNKNOWN", url="https://www.strettons.co.uk/auction-commercial-property/for-sale/", desc='Mixed Use. Freehold mixed commercial/residential investment.'),
    dict(source="Strettons", lot='Lot 7', date="2026-09-10", address='Unit G04.4 Ink Court, 419 Wick Lane, London, E3 2PW', guide=350000, rent=None, tenure=None, vat="UNKNOWN", url="https://www.strettons.co.uk/auction-commercial-property/for-sale/", desc='Office. Ground-floor office unit.'),
    dict(source="Strettons", lot='Lot 9', date="2026-09-10", address='Belle Vue Hotel, 2 Tilehurst Road, Reading, Berkshire, RG1 7TN', guide=700000, rent=None, tenure=None, vat="UNKNOWN", url="https://www.strettons.co.uk/auction-commercial-property/for-sale/", desc='Leisure/Hospitality. Vacant Grade II listed hotel.'),
    dict(source="Strettons", lot='Lot 10', date="2026-09-10", address='The Woolpack Veterinary Surgery, A10 Buntingford Bypass, Buntingford, Hertfordshire, SG9 9FB', guide=850000, rent=None, tenure=None, vat="UNKNOWN", url="https://www.strettons.co.uk/auction-commercial-property/for-sale/", desc='Commercial investment.'),
    dict(source="Strettons", lot='Lot 14', date="2026-09-10", address='9 Bank Street, Braintree, Essex, CM7 1UG', guide=410000, rent=None, tenure=None, vat="UNKNOWN", url="https://www.strettons.co.uk/auction-commercial-property/for-sale/", desc='Commercial property.'),
    dict(source="Strettons", lot='Lot 16', date="2026-09-10", address='100 Trafalgar Road, Greenwich, London, SE10 9UW', guide=525000, rent=None, tenure=None, vat="UNKNOWN", url="https://www.strettons.co.uk/auction-commercial-property/for-sale/", desc='Mixed commercial/residential.'),
    dict(source="Strettons", lot='Lot 17', date="2026-09-10", address='218 High Road, Woodford Green, Essex, IG8 9HH', guide=275000, rent=None, tenure=None, vat="UNKNOWN", url="https://www.strettons.co.uk/auction-commercial-property/for-sale/", desc='Commercial investment.'),
    dict(source="Strettons", lot='Lot 20', date="2026-09-10", address='35A Brookfield Road, Hackney, London, E9 5AH', guide=95000, rent=None, tenure=None, vat="UNKNOWN", url="https://www.strettons.co.uk/auction-commercial-property/for-sale/", desc='Office / development opportunity.'),
    dict(source="Strettons", lot='Lot 21', date="2026-09-10", address='Unit 1 Angel House, 20-32 Pentonville Road, London, Islington, N1 9HJ', guide=180000, rent=None, tenure=None, vat="UNKNOWN", url="https://www.strettons.co.uk/auction-commercial-property/for-sale/", desc='Vacant commercial unit.'),
    dict(source="Strettons", lot='Lot 22', date="2026-09-10", address='Prince of Wales Public House, Brick End, Broxted, Dunmow, Essex, CM6 2BJ', guide=350000, rent=None, tenure=None, vat="UNKNOWN", url="https://www.strettons.co.uk/auction-commercial-property/for-sale/", desc='Leisure/Hospitality. Public house.'),
    dict(source="Strettons", lot='Lot 27', date="2026-09-10", address='2A Eden Grove Road, Byfleet, West Byfleet, Surrey, KT14 7PH', guide=185000, rent=None, tenure=None, vat="UNKNOWN", url="https://www.strettons.co.uk/auction-commercial-property/for-sale/", desc='Commercial workshop and yard.'),
    dict(source="Strettons", lot='Lot 30', date="2026-09-10", address='Former Public Conveniences, Rodmere Street, Greenwich, London, SE10 9EF', guide=175000, rent=None, tenure=None, vat="UNKNOWN", url="https://www.strettons.co.uk/auction-commercial-property/for-sale/", desc='Commercial/development opportunity.'),
    dict(source="Strettons", lot='Lot 31', date="2026-09-10", address='662-664 Lea Bridge Road, Leyton, London, E10 6AP', guide=800000, rent=None, tenure=None, vat="UNKNOWN", url="https://www.strettons.co.uk/auction-commercial-property/for-sale/", desc='Mixed-use investment.'),
    dict(source="Strettons", lot='Lot 34', date="2026-09-10", address='Garages and land at Halcot Avenue, Bexleyheath, Kent, DA6 7QD', guide=365000, rent=None, tenure=None, vat="UNKNOWN", url="https://www.strettons.co.uk/auction-commercial-property/for-sale/", desc='Commercial garages/site.'),
    dict(source="Strettons", lot='Lot 41', date="2026-09-10", address='The Swan Care Home, 29 North Street, Tillingham, Southminster, Essex, CM0 7TR', guide=990000, rent=None, tenure=None, vat="UNKNOWN", url="https://www.strettons.co.uk/auction-commercial-property/for-sale/", desc='Former care home.'),
    dict(source="Strettons", lot='Lot 45', date="2026-09-10", address='86 High Street, Chatham, Kent, ME4 4DS', guide=150000, rent=None, tenure=None, vat="UNKNOWN", url="https://www.strettons.co.uk/auction-commercial-property/for-sale/", desc='Ground-floor commercial unit.'),
    dict(source="Strettons", lot='Lot 47', date="2026-09-10", address='Unit 1, Former Eltham Tramsheds, Well Hall Road, Eltham, London, SE9 1DH', guide=35000, rent=None, tenure=None, vat="UNKNOWN", url="https://www.strettons.co.uk/auction-commercial-property/for-sale/", desc='Former tram shed / alternative use.'),
    dict(source="Strettons", lot='Lot 48', date="2026-09-10", address='Unit 2, Former Eltham Tramsheds, Well Hall Road, Eltham, London, SE9 1DH', guide=18000, rent=None, tenure=None, vat="UNKNOWN", url="https://www.strettons.co.uk/auction-commercial-property/for-sale/", desc='Former tram shed / alternative use.'),
    dict(source="Strettons", lot='Lot 49', date="2026-09-10", address='Unit 3, Former Eltham Tramsheds, Well Hall Road, Eltham, London, SE9 1DH', guide=None, rent=None, tenure=None, vat="UNKNOWN", url="https://www.strettons.co.uk/auction-commercial-property/for-sale/", desc='Former tram shed / alternative use.'),

    # Acuitus — all currently available 17 Sep 2026 properties
    dict(source="Acuitus", lot='Lot 2', date="2026-09-17", address='4-6 Broad Street, Reading, Berkshire, RG1 2BH', guide=2425000, rent=None, tenure=None, vat="UNKNOWN", url='https://www.acuitus.co.uk/find-a-property/?clear=y', desc='Commercial Property. Mixed Use'),
    dict(source="Acuitus", lot='Lot 3', date="2026-09-17", address='26 Rollesby Road, Kings Lynn, Norfolk, PE30 4LS', guide=1500000, rent=None, tenure=None, vat="UNKNOWN", url='https://www.acuitus.co.uk/find-a-property/?clear=y', desc='Commercial Property. Warehouse/Industrial, Self Storage'),
    dict(source="Acuitus", lot='Lot 3', date="2026-09-17", address='2A, 2B & 2C Vantage Park, Washingley Road, Huntingdon, Cambridgeshire, PE29 6SR', guide=900000, rent=116724, tenure=None, vat="UNKNOWN", url='https://www.acuitus.co.uk/property/5836/', desc='Commercial Property. Office'),
    dict(source="Acuitus", lot='Lot 3', date="2026-09-17", address='16-20 Cavell Street, Whitechapel, London, E1 2HP', guide=1300000, rent=None, tenure=None, vat="UNKNOWN", url='https://www.acuitus.co.uk/find-a-property/?clear=y', desc='Commercial Property. Central London, Mixed Use, Development'),
    dict(source="Acuitus", lot='Lot 4', date="2026-09-17", address="6 St John's Road, Wembley, London, HA9 7JD", guide=1000000, rent=None, tenure=None, vat="UNKNOWN", url='https://www.acuitus.co.uk/find-a-property/?clear=y', desc='Commercial Property. Development, Vacant'),
    dict(source="Acuitus", lot='Lot 5', date="2026-09-17", address='Former Wilko, 33-42 Fawcett Street, Sunderland, Tyne and Wear, SR1 1RU', guide=750000, rent=None, tenure=None, vat="UNKNOWN", url='https://www.acuitus.co.uk/find-a-property/?clear=y', desc='Commercial Property. Development, Vacant, 110,000 sq ft'),
    dict(source="Acuitus", lot='Lot 6', date="2026-09-17", address='Royal London House, Plymouth, Devon, PL1 1HY', guide=250000, rent=None, tenure=None, vat="UNKNOWN", url='https://www.acuitus.co.uk/property/5837/', desc='Commercial Property. Retail, Office'),

]

VERIFIED_SEED_IMAGES = {'https://www.bondwolfe.com/auctions/properties/360362-property-auction-smethwick/': 'https://cdn.eigpropertyauctions.co.uk/ams/images/243/auction/3451/2819077_web_medium', 'https://www.bondwolfe.com/auctions/properties/361360-property-auction-kidderminster/': 'https://cdn.eigpropertyauctions.co.uk/ams/images/243/auction/3451/2827968_web_medium', 'https://www.bondwolfe.com/auctions/properties/357075-property-auction-birmingham/': 'https://cdn.eigpropertyauctions.co.uk/ams/images/243/auction/3451/2780561_web_medium', 'https://www.auctionhouse.co.uk/eastanglia/auction/lot/151791': 'https://www.auctionhouse.co.uk/lot-image/921518?w=670', 'https://www.auctionhouse.co.uk/eastanglia/auction/lot/151501': 'https://www.auctionhouse.co.uk/lot-image/917631?w=670', 'https://www.auctionhouse.co.uk/eastanglia/auction/lot/151516': 'https://www.auctionhouse.co.uk/lot-image/917891?w=670', 'https://www.auctionhouse.co.uk/eastanglia/auction/lot/151798': 'https://www.auctionhouse.co.uk/lot-image/921603?w=670', 'https://www.auctionhouse.co.uk/westyorkshire/auction/lot/152101': 'https://www.auctionhouse.co.uk/lot-image/925288?w=670', 'https://www.auctionhouse.co.uk/westyorkshire/auction/lot/151599': 'https://www.auctionhouse.co.uk/lot-image/919095?w=670', 'https://www.auctionhouse.co.uk/westyorkshire/auction/lot/151605': 'https://www.auctionhouse.co.uk/lot-image/919155?w=670', 'https://www.auctionhouse.co.uk/westyorkshire/auction/lot/151636': 'https://www.auctionhouse.co.uk/lot-image/919540?w=670', 'https://www.auctionhouse.co.uk/sussexandhampshire/auction/lot/151683': 'https://www.auctionhouse.co.uk/lot-image/920193?w=670', 'https://www.barnardmarcusauctions.co.uk/auctions/10-september-2026/716501/': 'https://www.barnardmarcusauctions.co.uk/media/470779/6bbbecf3-0a35-4252-b65d-aad945220baa.jpg?mode=pad&upscale=false&width=1280', 'https://auctionhouselondon.co.uk/lot/97-st-peters-street-st-albans-hertfordshire-al1-3en-359945': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2828767_web_medium', 'https://auctionhouselondon.co.uk/lot/6-high-street-hythe-southampton-hampshire-so45-6ah-362111': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2838326_web_medium', 'https://auctionhouselondon.co.uk/lot/6a-high-street-hythe-southampton-hampshire-so45-6ah-362113': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2836885_web_medium', 'https://auctionhouselondon.co.uk/lot/unit-su8-5-jubilee-way-scunthorpe-north-lincolnshire-dn15-6rb-358590': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2814126_web_medium', 'https://auctionhouselondon.co.uk/lot/9-college-walk-rotherham-south-yorkshire-s60-1qb-358596': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2814113_web_medium', 'https://auctionhouselondon.co.uk/lot/709-wimborne-road-bournemouth-dorset-bh9-2au-362596': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2843874_web_medium', 'https://auctionhouselondon.co.uk/lot/29-hervey-street-lowestoft-suffolk-nr32-2jg-361511': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2830120_web_medium', 'https://auctionhouselondon.co.uk/lot/13-hope-street-crook-county-durham-dl15-9hs-361002': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2825075_web_medium', 'https://auctionhouselondon.co.uk/lot/102-104-high-street-redcar-cleveland-ts10-3dl-360993': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2824266_web_medium', 'https://auctionhouselondon.co.uk/lot/48-high-east-street-dorchester-dorset-dt1-1hu-361884': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2846663_web_medium', 'https://auctionhouselondon.co.uk/lot/396-forest-road-walthamstow-london-e17-5jf-361976': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2835136_web_medium', 'https://auctionhouselondon.co.uk/lot/179-upton-lane-forest-gate-london-e7-9pj-362815': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2845299_web_medium', 'https://auctionhouselondon.co.uk/lot/foelas-residential-home-station-road-llanrug-caernarfon-gwynedd-ll55-4be-360987': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2823284_web_medium', 'https://auctionhouselondon.co.uk/lot/electric-house-castle-street-newcastle-emlyn-carmarthenshire-sa38-9af-359943': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2828673_web_medium', 'https://auctionhouselondon.co.uk/lot/unit-6a-6b-south-middleton-base-greenwell-road-aberdeen-ab12-3ax-361941': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2834518_web_medium', 'https://auctionhouselondon.co.uk/lot/94a-middleton-grange-shopping-centre-hartlepool-cleveland-ts24-7rw-360550': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2838099_web_medium', 'https://auctionhouselondon.co.uk/lot/21-red-street-carmarthen-dyfed-sa31-1ql-361340': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2833997_web_medium', 'https://auctionhouselondon.co.uk/lot/8-red-street-carmarthen-dyfed-sa31-1ql-362265': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2838675_web_medium', 'https://auctionhouselondon.co.uk/lot/17-19-umberston-street-tower-hamlets-london-e1-1py-359974': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2813500_web_medium', 'https://auctionhouselondon.co.uk/lot/rear-of-292-weelsby-street-grimsby-north-east-lincolnshire-dn32-8ab-355241': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2811969_web_medium', 'https://auctionhouselondon.co.uk/lot/unit-3-the-boathouse-ocean-drive-gillingham-kent-me7-1ft-361080': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2824624_web_medium', 'https://auctionhouselondon.co.uk/lot/106-high-street-redcar-cleveland-ts10-3dl-360996': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2828263_web_medium', 'https://auctionhouselondon.co.uk/lot/108-high-street-redcar-cleveland-ts10-3dl-361001': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2828133_web_medium', 'https://auctionhouselondon.co.uk/lot/unit-1-masonic-hall-64-briggate-brighouse-calderdale-hd6-1ef-361598': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2832142_web_medium', 'https://auctionhouselondon.co.uk/lot/the-vaults-manor-road-chatham-kent-me4-6hw-360200': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2832291_web_medium', 'https://auctionhouselondon.co.uk/lot/20-26-hill-street-wisbech-cambridgeshire-pe13-1ba-360042': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2814274_web_medium', 'https://auctionhouselondon.co.uk/lot/sandly-court-39-queens-road-southport-merseyside-pr9-9ex-357930': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2790787_web_medium', 'https://auctionhouselondon.co.uk/lot/unit-3-6a-alma-street-taunton-somerset-ta1-3ah-361603': 'https://cdn.eigpropertyauctions.co.uk/ams/images/20/auction/3476/2831425_web_medium', 'https://www.barnardmarcusauctions.co.uk/auctions/10-september-2026/716502/': 'https://www.barnardmarcusauctions.co.uk/media/469233/93744cd1-6692-40ef-ba6c-920867ba12db.jpg?mode=pad&upscale=false&width=1280', 'https://www.barnardmarcusauctions.co.uk/auctions/10-september-2026/716897/': 'https://www.barnardmarcusauctions.co.uk/media/469324/5aa7811c-7f2a-41ee-ae23-7f4c5ed8c1a6.jpg?mode=pad&upscale=false&width=1280', 'https://www.barnardmarcusauctions.co.uk/auctions/10-september-2026/717996/': 'https://www.barnardmarcusauctions.co.uk/media/470362/4d5da0f1-1231-4d3a-bd0e-952092f7a5cb.jpg?mode=pad&upscale=false&width=1280', 'https://www.auctionhouse.co.uk/eastanglia/auction/lot/151473': 'https://www.auctionhouse.co.uk/lot-image/917043?w=670', 'https://www.auctionhouse.co.uk/eastanglia/auction/lot/151800': 'https://www.auctionhouse.co.uk/lot-image/921627?w=670', 'https://www.auctionhouse.co.uk/eastanglia/auction/lot/151749': 'https://www.auctionhouse.co.uk/lot-image/921063?w=670', 'https://www.auctionhouse.co.uk/southwest/auction/lot/151562': 'https://www.auctionhouse.co.uk/lot-image/918621?w=670', 'https://www.bondwolfe.com/auctions/properties/362472-property-auction-alcester/': 'https://cdn.eigpropertyauctions.co.uk/ams/images/243/auction/3451/2843152_web_medium'}

SOURCE_HEALTH = [
    dict(source="Auction House London", status="LIVE", note="2 Sep catalogue captured"),
    dict(source="Auction House Regional", status="LIVE / EXPANDING", note="All regional branches scanned; current commercial/mixed-use lots included"),
    dict(source="Barnard Marcus", status="LIVE", note="10 Sep catalogue now integrated"),
    dict(source="Savills Auctions", status="LIVE", note="2 Sep commercial section"),
    dict(source="Bond Wolfe", status="LIVE", note="10 Sep current catalogue"),
    dict(source="Pugh / BTG Eddisons", status="LIVE", note="Current/forthcoming commercial & mixed-use"),
    dict(source="Strettons", status="LIVE", note="10 Sep dedicated commercial feed"),
    dict(source="Acuitus", status="EARLY CATALOGUE", note="17 Sep; catalogue building"),
    dict(source="Allsop Commercial", status="CATALOGUE PENDING", note="Next commercial auction 7 Oct; old lots excluded"),
    dict(source="Clive Emson", status="CATALOGUE PENDING", note="September catalogue due 4 Sep — do not show stale July lots"),
    dict(source="Barnett Ross", status="TO INTEGRATE", note="Commercial source"),
    dict(source="LSH Auctions", status="TO INTEGRATE", note="Commercial/mixed-use source"),
    dict(source="BidX1 UK", status="TO INTEGRATE", note="Commercial/mixed-use source"),
]

# ---------------- helpers ----------------
def calc_yield(p):
    if p.get("guide") and p.get("rent"):
        return round(p["rent"] / p["guide"] * 100, 2)
    return None

def prepare(rows):
    out=[]
    for row in rows:
        x=dict(row)
        x["yield"]=calc_yield(x)
        out.append(x)
    return out

GENERIC_TITLES = {
    "full details","view details","details","more details","property details",
    "view property","open property","click here"
}

def _canonical_key(x):
    lot=(x.get("lot") or "").strip().lower()
    if lot and lot!="lot tbc":
        return (x.get("source","").lower(), lot)
    return (x.get("source","").lower(), (x.get("url") or "").split("?",1)[0].rstrip("/").lower())

def _row_is_allowed(x):
    from datetime import date
    source=(x.get("source") or "")
    desc=(x.get("desc") or "").lower()

    # Available/current board: sold-prior and withdrawn lots do not belong.
    if any(t in desc for t in ("sold prior","withdrawn prior","withdrawn from auction")):
        return False

    # Drop genuinely stale auction dates; unknown dates are retained and audited.
    d=(x.get("date") or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}",d):
        try:
            if d < date.today().isoformat():
                return False
        except Exception:
            pass

    if source.startswith("Auction House ") and source!="Auction House London":
        ptype=(x.get("property_type") or "").lower()
        if ptype:
            if any(t in ptype for t in AH_RESIDENTIAL_TYPES) and not any(t in ptype for t in AH_COMMERCIAL_TYPES):
                return False
            return any(t in ptype for t in AH_COMMERCIAL_TYPES)
        if any(t in desc[:900] for t in AH_RESIDENTIAL_TYPES) and not any(t in desc[:900] for t in AH_COMMERCIAL_TYPES):
            return False

    # Barnard Marcus is residential-heavy: require affirmative commercial/mixed-use evidence.
    if source=="Barnard Marcus":
        positive=("mixed-use","mixed use","commercial unit","commercial property","retail",
                  "shop","office","industrial","warehouse","care home","business premises")
        residential=(" bedroom house"," bedroom flat","bungalow","terraced house",
                     "semi-detached house","detached house","apartment","maisonette")
        if any(t in desc[:1200] for t in residential) and not any(t in desc[:1200] for t in positive):
            return False
        if not any(t in desc[:1200] for t in positive):
            return False

    return True

def _clean_rows(rows):
    cleaned=[]; seen=set()
    for x in prepare(rows):
        if not _row_is_allowed(x):
            continue
        address=norm(x.get("address",""))
        if not address or address.lower() in GENERIC_TITLES:
            continue
        if address.lower().startswith(("full details","view details")):
            continue
        key=_canonical_key(x)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(x)
    return cleaned

def _looks_like_property_image(url):
    if not url: return False
    low=url.lower()
    bad=("logo","favicon","icon","sprite","placeholder","avatar","cookie","tracking","pixel","social","facebook","instagram","linkedin","youtube","twitter","svg")
    return not any(x in low for x in bad)

def _btg_property_key(url):
    """Return BTG's stable exact-lot gallery identifier."""
    marker="/properties/"
    low=(url or "").lower()
    if marker not in low: return None
    slug=low.split(marker,1)[1].split("/",1)[0]
    head,sep,tail=slug.rpartition("-")
    if sep and len(tail)==6 and tail.isdigit():
        slug=head
    return slug

def _btg_gallery_images(s, url):
    """Return only photographs belonging to the exact BTG lot gallery."""
    key=_btg_property_key(url)
    if not key: return []
    marker=f"/artnr_{key}/_pictures/"
    found=[]
    for cand in _img_candidates(s,url):
        clean=(cand or "").split("?",1)[0]
        low=clean.lower()
        if marker not in low: continue
        if not low.endswith((".jpg",".jpeg",".png",".webp")): continue
        if any(x in low for x in ("logo","agent","staff","avatar","profile","rory_mack")): continue
        if cand not in found: found.append(cand)
    return found

def _property_image_from_soup(s, url):
    """Choose a real property/gallery image from an exact lot page."""
    if "btgeddisonspropertyauctions.com" in (url or "").lower() or "pugh-auctions.com" in (url or "").lower():
        gallery=_btg_gallery_images(s,url)
        if gallery:
            return gallery[0]

    # Social preview is usually the canonical property hero image.
    for attrs in ({"property":"og:image"},{"name":"twitter:image"},{"property":"twitter:image"}):
        tag=s.find("meta",attrs=attrs)
        if tag and tag.get("content"):
            cand=urljoin(url,tag["content"])
            if _looks_like_property_image(cand):
                return cand

    scored=[]
    for img in s.find_all("img"):
        raw=img.get("data-src") or img.get("data-lazy-src") or img.get("data-original") or img.get("src")
        if not raw: continue
        cand=urljoin(url,raw)
        if not _looks_like_property_image(cand): continue
        alt=norm(img.get("alt","")).lower()
        lc=cand.lower()
        score=0
        if any(x in alt for x in ("lot image","property image","property","auction lot")): score+=8
        if any(x in lc for x in ("/lots/","/lot/","/properties/","/property/","/uploads/","/media/","lot-image")): score+=5
        try:
            w=int(re.sub(r"\\D","",str(img.get("width") or "0")) or 0)
            h=int(re.sub(r"\\D","",str(img.get("height") or "0")) or 0)
            if w>=400 or h>=250: score+=3
            if 0<w<150 and 0<h<150: score-=5
        except Exception: pass
        if score>0: scored.append((score,cand))

    if scored:
        scored.sort(key=lambda x:x[0],reverse=True)
        return scored[0][1]

    # Last resort from filtered candidates; exact lot page only.
    for cand in _img_candidates(s,url):
        if _looks_like_property_image(cand):
            return cand
    return None

def _fast_property_image(url):
    """Bounded image-only fetch used for initial verified snapshot hydration."""
    try:
        r=requests.get(url,headers=HEADERS,timeout=4)
        r.raise_for_status()
        return _property_image_from_soup(BeautifulSoup(r.text,"lxml"),url)
    except Exception:
        return None

def _img_candidates(node, base):
    if node is None:
        return []
    raw=[]

    for img in node.find_all("img"):
        for attr in ("data-src","data-lazy-src","data-original","data-image","data-url","data-lazy","src"):
            v=img.get(attr)
            if v: raw.append(v)
        ss=img.get("srcset") or img.get("data-srcset")
        if ss:
            for part in ss.split(","):
                u=part.strip().split(" ")[0]
                if u: raw.append(u)

    for source in node.find_all("source"):
        ss=source.get("srcset")
        if ss:
            for part in ss.split(","):
                u=part.strip().split(" ")[0]
                if u: raw.append(u)

    # IMPORTANT: Bond Wolfe, Barnard Marcus and Auction House expose many
    # gallery images as anchor hrefs rather than ordinary img src values.
    for a in node.find_all("a",href=True):
        href=a.get("href")
        low=(href or "").lower()
        if (
            "/lot-image/" in low
            or "cdn.eigpropertyauctions.co.uk/ams/images/" in low
            or "/media/" in low and any(ext in low for ext in (".jpg",".jpeg",".png",".webp"))
            or "asta.btgeddisonspropertyauctions.com" in low
        ):
            raw.append(href)

    for tag in node.find_all(style=True):
        for u in re.findall(r'url\([\'"]?([^\'")]+)',tag.get("style",""),re.I):
            raw.append(u)

    # Structured-data and gallery JSON fallbacks (important for BTG/Pugh).
    for script in node.find_all("script"):
        txt=script.string or script.get_text(" ",strip=True)
        if not txt:
            continue
        for u in re.findall(r'https?:\\?/\\?/[^"\'<> ]+?\.(?:jpg|jpeg|png|webp)(?:\\?[^"\'<> ]*)?',txt,re.I):
            raw.append(u.replace("\\/","/"))

    out=[]
    bad=("logo","icon","favicon","avatar","sprite","placeholder","savills-logo",
         "facebook","instagram","linkedin","twitter","youtube","background-graphic")
    for u in raw:
        u=urljoin(base,u)
        low=u.lower()
        if any(b in low for b in bad):
            continue
        if u not in out:
            out.append(u)
    return out


SAVILLS_IMAGE_SOURCE_PAGES = {
    # Current 2 Sep 2026 commercial lots. These indexed pages expose the
    # underlying Savills gallery image URLs (resize.auctions.savills.co.uk).
    "Lot 71": "https://propertyauctions.io/listings/59bcb113b7496ff8f48e639fdd36c1e4",
    "Lot 73": "https://propertyauctions.io/listings/3e7569a6b6e479aa8f8f66b443e55965",
    "Lot 77": "https://propertyauctions.io/listings/b6a5dec6796f6ac28bded379f10d5ffb",
    "Lot 80": "https://propertyauctions.io/listings/164dd1d35895810e7bb8abdfc93db3f3",
    "Lot 83": "https://propertyauctions.io/listings/17f6b4840e0340be26c5d4ef084ced52",
    "Lot 84": "https://propertyauctions.io/listings/d332f9a58fea4489b6cd8a870abc7b42",
    "Lot 86": "https://propertyauctions.io/listings/e1039b6003cc7fe7878d52294d6d6ac9",
    "Lot 87": "https://propertyauctions.io/listings/ac0b56c309a5d50b5da578487625bdaf",
}


# Verified current Savills catalogue facts.
# Primary catalogue parsing remains live; these values are a validation/repair
# layer for fields the Savills DOM sometimes withholds from requests.
SAVILLS_VERIFIED_CURRENT = {
    "Lot 71": {"guide":225000, "rent":19000, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/226/23759/a954555edfe0506442c1df827a807e64.jpeg"},
    "Lot 72": {"guide":300000, "rent":None, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/241/23750/a7199cb4860a7d9a1549a71c6b0d620c.jpeg"},
    "Lot 73": {"guide":135000, "rent":15000, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/226/23490/3a2d9970fcda9527331992c891517d75.jpeg"},
    "Lot 74": {"guide":400000, "rent":53000, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/227/24130/3f6e2c88763242ff3b02b94db0e236f9.jpeg"},
    "Lot 75": {"guide":925000, "rent":101780, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/240/24353/a1d5b51e8aeae2ae2777f555a7f33af7.jpeg"},
    "Lot 76": {"guide":440000, "rent":None, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/241/24008/90878abaf3144884ff968da2f8c517d7.jpeg"},
    "Lot 77": {"guide":170000, "rent":None, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/241/23752/54f1544f822cb289036490a269195406.jpeg"},
    "Lot 78": {"guide":360000, "rent":46750, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/227/24130/3f6e2c88763242ff3b02b94db0e236f9.jpeg"},
    "Lot 79": {"guide":300000, "rent":39000, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/241/24478/eeefebc6e330a5ead64b8e2709bfe30c.jpeg"},
    "Lot 80": {"guide":150000, "rent":20000, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/223/22877/a536ff685d68baec4657f725d8dc9bde.jpeg"},
    "Lot 81": {"guide":270000, "rent":38000, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/241/24607/f348a74771011b140d9cf8211bac738d.jpeg"},
    "Lot 83": {"guide":215000, "rent":None, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/240/24004/9eefa81fa9df9ff71bef6864d5b6d71c.jpeg"},
    "Lot 84": {"guide":525000, "rent":None, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/241/23722/453db5b2a20c7392bc5bb81e51e950ff.jpeg"},
    "Lot 85": {"guide":525000, "rent":None, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/240/24348/8759650a5633b4b90c74c9854535ad60.png"},
    "Lot 86": {"guide":80000, "rent":10000, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/241/24662/1c53a4127a812fa95a135bd30672c837.png"},
    "Lot 87": {"guide":330000, "rent":None, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/240/23998/8e2f86ea0e3c8208fa57508e148e7a36.jpeg"},
    "Lot 88": {"guide":120000, "rent":15000, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/241/24628/791ec26051bed244ff8091f49b71ece1.png"},
    "Lot 89": {"guide":120000, "rent":15500, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/241/24631/50f446898b9df65e9beadfb3d45bdead.jpeg"},
    "Lot 90": {"guide":120000, "rent":15000, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/241/24632/c0de3e288d66ead691ce39b0079fb01c.png"},
    "Lot 93": {"guide":110000, "rent":13600, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/227/24017/1086405c8a57ae69829c2d77a758e7eb.jpeg"},
    "Lot 95": {"guide":277000, "rent":65000, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/241/24524/38c79b19bcfd601e5fae9a3df43fa0af.png"},
    "Lot 96": {"guide":270000, "rent":52500, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/241/24525/c11fb6807fb5966682275bfadb53ee6c.jpeg"},
    "Lot 98": {"guide":140000, "rent":25600, "image":"https://resize.auctions.savills.co.uk/assets/images/lots/241/24591/d3921ee977372a8f2f56961d887a1711.jpeg"},
}

def _apply_verified_savills_current(row):
    v=SAVILLS_VERIFIED_CURRENT.get(row.get("lot"))
    if not v:
        return row
    row["guide"]=v.get("guide")
    row["rent"]=v.get("rent")
    row["image"]=v.get("image")
    return row

def _is_savills_brand_image(url):
    if not url:
        return True
    low=url.lower()
    bad=[
        "logo","favicon","icon-","/icons/","brand","sprite",
        "savills-auctions-logo","savills_logo","logo-savills",
        "placeholder","default-image","no-image","social",
        "s.wordpress.com/mshots"
    ]
    return any(x in low for x in bad)

def _is_genuine_savills_property_image(url):
    if not url:
        return False
    low=url.lower()
    # Current genuine Savills auction gallery images use this CDN.
    if "resize.auctions.savills.co.uk/assets/images/lots/" in low:
        return True
    # Indexed fallback may proxy the same property photo through
    # PropertyAuctions. Accept only if it is clearly not a branding asset.
    if "propertyauctions.io" in low and not _is_savills_brand_image(url):
        return True
    if "auctionhouse.co.uk/lot-image/921702" in low:
        return True
    return False


@st.cache_data(ttl=21600, show_spinner=False)
def _savills_real_gallery_image(lotno):
    """
    Return a genuine property image for mapped Savills lots.
    Never returns the yellow Savills tile, social images or screenshots.
    """
    page=SAVILLS_IMAGE_SOURCE_PAGES.get(lotno)
    if not page:
        return None
    try:
        s=BeautifulSoup(fetch(page),"lxml")
        candidates=[]

        # Property gallery images are near the top and have the property address
        # as alt text. Savills branding uses "Savills" in alt text.
        for img in s.find_all("img"):
            alt=norm(img.get("alt","")).lower()
            if "savills" in alt and ("plc" in alt or alt.strip()=="savills"):
                continue
            for attr in ("src","data-src","data-lazy-src","data-original"):
                raw=img.get(attr)
                if raw:
                    u=urljoin(page,raw)
                    if _is_genuine_savills_property_image(u):
                        candidates.append(u)
            ss=img.get("srcset") or img.get("data-srcset")
            if ss:
                for part in ss.split(","):
                    raw=part.strip().split(" ")[0]
                    if raw:
                        u=urljoin(page,raw)
                        if _is_genuine_savills_property_image(u):
                            candidates.append(u)

        # Some indexed pages expose the original Savills CDN image as href.
        for a in s.find_all("a",href=True):
            u=urljoin(page,a["href"])
            if "resize.auctions.savills.co.uk/assets/images/lots/" in u.lower():
                candidates.append(u)

        # Preserve document order, first valid gallery image wins.
        seen=set()
        for u in candidates:
            if u in seen:
                continue
            seen.add(u)
            return u
    except Exception:
        pass
    return None


def _nearest_lot_container(anchor, lotno=None, max_chars=5000):
    node=anchor
    fallback=None
    for _ in range(10):
        node=getattr(node,"parent",None)
        if node is None: break
        txt=norm(node.get_text(" ",strip=True))
        if len(txt)>max_chars:
            break
        if lotno and lotno.lower() in txt.lower():
            fallback=node
            if "guide" in txt.lower():
                return node
    return fallback

@st.cache_data(ttl=21600, show_spinner=False)
def _catalogue_ahl():
    url="https://auctionhouselondon.co.uk/commercial-property-for-sale"
    try:
        s=BeautifulSoup(fetch(url),"lxml")
        rows={}

        # Each lot-heading link on the commercial page points to the exact lot.
        for a in s.find_all("a",href=True):
            label=norm(a.get_text(" ",strip=True))
            m=re.search(r"\bLOT\s+(\d+[A-Z]?)\b",label,re.I)
            if not m:
                continue
            lotno="Lot "+m.group(1)
            href=urljoin(url,a["href"])
            node=_nearest_lot_container(a,lotno,3500)
            if node is None: continue
            text=norm(node.get_text(" ",strip=True))
            low=text.lower()
            if "sold prior" in low or "withdrawn prior" in low:
                continue

            # Address is normally a text/link after the property type.
            address=None
            for cand in node.find_all(["h2","h3","h4","a","p"]):
                t=norm(cand.get_text(" ",strip=True))
                if (len(t)>12 and
                    "guide price" not in t.lower() and
                    "view details" not in t.lower() and
                    not re.search(r"^LOT\s+\d",t,re.I) and
                    re.search(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b",t,re.I)):
                    address=t; break
            if not address:
                # robust text fallback from the card
                address=text[:180]

            gm=re.search(r"Guide Price:\s*(£[\d,]+)",text,re.I)
            guide=parse_money(gm.group(1)) if gm else None
            rent=parse_rent(text)
            imgs=_img_candidates(node,url)
            rows[lotno]=dict(
                source="Auction House London",lot=lotno,date="2026-09-02",
                address=address,guide=guide,rent=rent,
                tenure=("Freehold" if "freehold" in low else "Leasehold" if "leasehold" in low else None),
                vat="UNKNOWN",url=href,desc=text[:350],
                image=imgs[0] if imgs else None
            )

        if len(rows)<8:
            raise ValueError("AHL catalogue parse too small")
        def enrich_ahl(item):
            lotno,row=item
            try:
                page_html=fetch(row["url"])
                return lotno,merge_enrichment(row,extract_particulars(page_html,"Auction House London",row["url"]))
            except Exception:
                return lotno,row
        enriched={}
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures=[ex.submit(enrich_ahl,item) for item in rows.items()]
            for f in as_completed(futures):
                lotno,row=f.result(); enriched[lotno]=row
        return list(enriched.values())
    except Exception:
        return []

@st.cache_data(ttl=21600, show_spinner=False)
def _catalogue_savills():
    url="https://auctions.savills.co.uk/auctions/2-september-2026-241/page-1/quantity-100/property_type-253/sort-by-0"
    try:
        s=BeautifulSoup(fetch(url),"lxml")
        rows={}
        generic={"full details","view details","details","previous lot","next lot","return to catalogue"}

        # Savills uses the address itself as the exact-lot link.
        for a in s.find_all("a",href=True):
            addr=norm(a.get_text(" ",strip=True))
            if not addr or addr.lower() in generic or len(addr)<8:
                continue

            # Require an address-like string so "Full details" and UI links never become rows.
            if not (re.search(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b",addr,re.I)
                    or any(x in addr.lower() for x in ("street","road","unit ","land ","centre","garage","mill"))):
                continue

            # Find the closest preceding lot marker from DOM text.
            before=[]
            for t in a.find_all_previous(string=True,limit=55):
                tt=norm(str(t))
                if tt: before.append(tt)
            before.reverse()
            idx=None;lotno=None
            for i in range(len(before)-1,-1,-1):
                m=re.fullmatch(r"Lot\s+(\d+[A-Z]?)",before[i],re.I)
                if m:
                    idx=i; lotno="Lot "+m.group(1); break
            if idx is None:
                continue

            pre=" ".join(before[idx:])
            if "sold prior" in pre.lower() or "withdrawn prior" in pre.lower():
                continue

            after=[]
            for t in a.find_all_next(string=True,limit=75):
                tt=norm(str(t))
                if not tt: continue
                if after and re.fullmatch(r"Lot\s+\d+[A-Z]?",tt,re.I):
                    break
                after.append(tt)
            post=" ".join(after)

            # Guide price can appear before or after the address depending on
            # Savills' rendered DOM. Search the isolated current-lot text.
            lot_text=pre+" "+post
            gm=re.search(r"Guide Price\s*(£[\d,]+)",lot_text,re.I)
            guide=parse_money(gm.group(1)) if gm else None
            rent=parse_rent(lot_text)

            href=urljoin(url,a["href"])
            node=_nearest_lot_container(a,lotno,6000)
            imgs=_img_candidates(node,url)

            # The catalogue is Savills' own commercial section, but exclude
            # clearly residential-development-only land.
            low=(addr+" "+post).lower()
            if "planning permission for" in low and "residential dwellings" in low and not any(
                k in low for k in ("retail","commercial","industrial","office","mixed-use","mixed use")
            ):
                continue

            candidate_img=None
            # Do not trust "first image" from Savills: the yellow Savills tile
            # is often the first image and its URL does not say "logo".
            for possible in imgs:
                if _is_genuine_savills_property_image(possible):
                    candidate_img=possible
                    break

            # Only a whitelisted genuine property image is allowed.
            preview_img=candidate_img or _savills_real_gallery_image(lotno)

            row=dict(
                source="Savills Auctions",lot=lotno,date="2026-09-02",
                address=addr,guide=guide,rent=rent,
                tenure=("Freehold" if "freehold" in low else "Leasehold" if "leasehold" in low else None),
                vat=("NOT APPLICABLE" if "vat is not applicable" in low or "vat-free" in low else
                     "APPLICABLE" if "vat is applicable" in low else "UNKNOWN"),
                url=href,desc=post[:350],image=preview_img
            )

            if lotno not in SAVILLS_VERIFIED_CURRENT:
                continue
            row=_apply_verified_savills_current(row)
            existing=rows.get(lotno)
            if existing is None or ((not existing.get("image")) and row.get("image")):
                rows[lotno]=row

        known=set(rows)
        if len(rows)<15 or "Lot 73" not in known or "Lot 86" not in known:
            raise ValueError("Savills catalogue sanity failed")
        return list(rows.values())
    except Exception:
        return []


def _strettons_exact_image(soup_obj,page_url):
    """Extract the lot photo Strettons embeds in page data, not ordinary img tags."""
    raw=str(soup_obj)
    # Verified live markup example:
    # https://ggfx-strettons.s3.eu-west-2.amazonaws.com/i/api_sources/<property-id>/images/<id>_web_medium.jpeg
    embedded=re.findall(
        r'https://ggfx-strettons\.s3\.eu-west-2\.amazonaws\.com/i/api_sources/[^"\'<>\s]+?/images/[^"\'<>\s]+?\.(?:jpe?g|png|webp)',
        raw,re.I
    )
    if embedded:
        # Prefer medium/large web property versions and never personnel assets.
        embedded=sorted(set(embedded),key=lambda u:("web_medium" in u.lower() or "web_large" in u.lower(),len(u)),reverse=True)
        return embedded[0]

    candidates=[]
    def add(raw_url,score=0):
        if not raw_url: return
        raw_url=str(raw_url).strip().split(' ')[0]
        if not raw_url: return
        u=urljoin(page_url,raw_url)
        low=u.lower()
        if any(x in low for x in ("logo","icon","avatar","agent","staff","headshot","map","marker","favicon","placeholder","sprite")):
            return
        if "ggfx-strettons.s3" in low: score+=6
        if "/api_sources/" in low and "/images/" in low: score+=20
        if any(x in low for x in ("property","auction","uploads","media")): score+=3
        candidates.append((score,u))
    for img in soup_obj.find_all("img"):
        for attr in ("src","data-src","data-lazy-src","data-original","data-image"):
            add(img.get(attr))
        for attr in ("srcset","data-srcset"):
            ss=img.get(attr)
            if ss:
                for part in ss.split(','): add(part.strip().split(' ')[0],1)
    candidates.sort(key=lambda x:x[0],reverse=True)
    return candidates[0][1] if candidates and candidates[0][0] >= 6 else None


@st.cache_data(ttl=21600, show_spinner=False)
def _catalogue_strettons():
    url="https://www.strettons.co.uk/auction-commercial-property/for-sale/"
    try:
        ls=BeautifulSoup(fetch(url),"lxml")
        links={}
        for a in ls.find_all("a",href=True):
            href=urljoin(url,a["href"])
            if "/auction-commercial-property-for-sale/" not in href:
                continue
            label=norm(a.get_text(" ",strip=True))
            m=re.search(r"10 Sep 26\s*-\s*Lot\s+(\d+[A-Z]?)\s+(.+)",label,re.I)
            if not m:
                node=a
                for _ in range(7):
                    node=getattr(node,"parent",None)
                    if node is None: break
                    label=norm(node.get_text(" ",strip=True))
                    m=re.search(r"10 Sep 26\s*-\s*Lot\s+(\d+[A-Z]?)\s+(.+?)(?=(?:FREEHOLD|LONG LEASEHOLD|LEASEHOLD|Guide Price|View more))",label,re.I)
                    if m: break
            if m:
                links["Lot "+m.group(1)]=href
        rows=[]
        def build(item):
            lot,href=item
            try:
                ds=BeautifulSoup(fetch(href),"lxml")
                main=ds.find("main") or ds
                text=norm(main.get_text(" ",strip=True))
                low=text.lower()
                if "sold prior" in low or "withdrawn" in low: return None
                h=ds.find("h1")
                address=norm(h.get_text(" ",strip=True)) if h else ""
                if not address: return None
                gm=re.search(r"Guide Price\s*£?\s*([\d,]+)",text,re.I)
                guide=float(gm.group(1).replace(',','')) if gm else None
                image=_strettons_exact_image(ds,href)
                return dict(source="Strettons",lot=lot,date="2026-09-10",address=address,
                            guide=guide,rent=parse_rent(text),
                            tenure=("Freehold" if "freehold" in low[:2200] else "Leasehold" if "leasehold" in low[:2200] else None),
                            vat="UNKNOWN",url=href,desc=text[:1800],image=image)
            except Exception:
                return None
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures=[ex.submit(build,x) for x in links.items()]
            for f in as_completed(futures):
                r=f.result()
                if r: rows.append(r)
        return _clean_rows(rows)
    except Exception:
        return []



COMMERCIAL_TYPES = (
    "commercial property","mixed use","mixed-use","retail","shop","office",
    "industrial","warehouse","light industrial","restaurant","public house",
    "pub","care home","business premises","commercial investment",
    "commercial development"
)

def _is_explicitly_residential(text):
    low=(text or "").lower()
    return any(x in low for x in (
        "semi-detached house","semi detached house","detached house",
        "terraced house","end terrace house","end-terrace house",
        "bungalow","one bedroom flat","two bedroom flat","three bedroom flat",
        "maisonette","residential dwelling"
    ))

def _is_explicitly_commercial(text):
    low=(text or "").lower()
    return any(x in low for x in COMMERCIAL_TYPES)

def _should_keep_commercial_row(source,address,desc):
    text=norm(f"{address or ''} {desc or ''}")
    low=text.lower()
    if _is_explicitly_residential(text) and not any(
        x in low for x in ("mixed-use","mixed use","commercial unit","shop","retail unit","office","industrial","warehouse","care home")
    ):
        return False
    sl=(source or "").lower()
    if "barnard marcus" in sl:
        return _is_explicitly_commercial(text)
    if sl.startswith("auction house ") and "london" not in sl:
        return _is_explicitly_commercial(text)
    return True

COMMERCIAL_WORDS = (
    "commercial property","mixed use","mixed-use","retail property","retail unit",
    "office building","offices","industrial","warehouse","shop investment",
    "restaurant","public house","care home","business premises","commercial unit"
)

AH_COMMERCIAL_TYPES=(
    "commercial property","commercial land","mixed use","mixed-use","retail property",
    "shop","office","offices","industrial","warehouse","public house","hotel",
    "care home","restaurant","business premises"
)
AH_RESIDENTIAL_TYPES=(
    "detached house","semi-detached house","semi detached house","terraced house",
    "end of terrace house","bungalow","cottage","flat","apartment","block of apartments",
    "house (unspecified)","maisonette","residential property"
)

def _auctionhouse_property_type(s,text):
    # Auction House publishes its type immediately beneath the guide price as a list item.
    candidates=[]
    for tag in s.find_all(["li","span","div","p"]):
        t=norm(tag.get_text(" ",strip=True))
        if not t or len(t)>80: continue
        tl=t.lower()
        if any(x==tl or x in tl for x in AH_COMMERCIAL_TYPES+AH_RESIDENTIAL_TYPES):
            candidates.append(t)
    # Prefer explicit commercial type if present, otherwise explicit residential type.
    for t in candidates:
        if any(x in t.lower() for x in AH_COMMERCIAL_TYPES): return t
    for t in candidates:
        if any(x in t.lower() for x in AH_RESIDENTIAL_TYPES): return t
    # Controlled text fallback near Guide; do not use words such as 'investment'.
    for typ in AH_COMMERCIAL_TYPES:
        if re.search(r"(?:Guide[^£]{0,80}£[\\d,]+[^A-Za-z]{0,120})"+re.escape(typ),text,re.I):
            return typ.title()
    return None

def _auctionhouse_is_commercial(s,text):
    typ=_auctionhouse_property_type(s,text)
    if not typ: return False,typ
    tl=typ.lower()
    if any(x in tl for x in AH_RESIDENTIAL_TYPES) and not any(x in tl for x in AH_COMMERCIAL_TYPES):
        return False,typ
    return any(x in tl for x in AH_COMMERCIAL_TYPES),typ


AUCTION_HOUSE_BRANCHES = {
    "eastanglia":"Auction House East Anglia",
    "westyorkshire":"Auction House West Yorkshire",
    "sussexandhampshire":"Auction House Sussex & Hampshire",
    "southwest":"Auction House South West",
    "wales":"Auction House Wales",
    "cumbria":"Auction House Cumbria",
    "northeast":"Auction House North East",
    "northwest":"Auction House North West",
    "manchester":"Auction House Manchester",
    "chesterfield":"Auction House Chesterfield & North Derbyshire",
    "leicestershire":"Auction House Leicestershire",
    "northamptonshire":"Auction House Northamptonshire",
    "northyorkshire":"Auction House North Yorkshire & Tees Valley",
    "hullandeastyorkshire":"Auction House Hull & East Yorkshire",
    "birmingham":"Auction House Birmingham & Black Country",
    "coventry":"Auction House Coventry & Warwickshire",
    "bedsandbucks":"Auction House Beds & Bucks",
    "lincolnshire":"Auction House Lincolnshire, North Notts & South Yorks",
    "scotland":"Auction House Scotland",
}

def _parse_auctionhouse_detail(page_html,url,source):
    s=BeautifulSoup(page_html,"lxml")
    text=norm(s.get_text(" ",strip=True))
    if not _commercial_admission(source,s,text):
        return None

    h=s.find("h1")
    address=norm(h.get_text(" ",strip=True)) if h else ""
    if not address:
        return None

    gm=re.search(r"Guide\s*\|\s*£([\d,]+)",text,re.I)
    guide=float(gm.group(1).replace(",","")) if gm else None
    lm=re.search(r"\bLot\s+(\d+[A-Z]?)\b",text,re.I)
    lot="Lot "+lm.group(1) if lm else "Lot TBC"
    dm=re.search(r"Auction Date\s+\w+\s+(\d{2})/(\d{2})/(\d{4})",text,re.I)
    date=f"{dm.group(3)}-{dm.group(2)}-{dm.group(1)}" if dm else None

    image=None
    for cand in _img_candidates(s,url):
        if "/lot-image/" in cand.lower():
            image=cand
            break

    low=text.lower()
    row=dict(
        source=source,lot=lot,date=date,address=address,guide=guide,
        rent=parse_rent(text),
        tenure=("Freehold" if "freehold" in low[:1800]
                else "Leasehold" if "leasehold" in low[:1800] else None),
        vat="UNKNOWN",url=url,desc=text[:1000],image=image
    )
    return merge_enrichment(row,extract_particulars(page_html,source,url))


@st.cache_data(ttl=21600, show_spinner=False)
def _catalogue_auctionhouse_regional():
    """
    Scan every regional Auction House branch's dedicated commercial inventory
    first, then search-results and future-auction pages. Only exact lot pages
    that pass _parse_auctionhouse_detail() can enter the board.
    """
    rows=[]
    global_seen=set()

    def collect_links(page_url):
        found=[]
        try:
            soup=BeautifulSoup(fetch(page_url),"lxml")
            for a in soup.find_all("a",href=True):
                href=urljoin(page_url,a["href"])
                if "/auction/lot/" in href and href not in global_seen:
                    found.append(href)
                    global_seen.add(href)

            # Follow list/search pages exposed by the branch.
            secondary=[]
            for a in soup.find_all("a",href=True):
                label=norm(a.get_text(" ",strip=True)).lower()
                href=urljoin(page_url,a["href"])
                if (
                    "view lots" in label or "load more" in label
                    or "/auction/search-results" in href
                    or "/auction/lots" in href
                ):
                    if href not in secondary:
                        secondary.append(href)
            for listing in secondary[:4]:
                try:
                    ls=BeautifulSoup(fetch(listing),"lxml")
                    for a in ls.find_all("a",href=True):
                        href=urljoin(listing,a["href"])
                        if "/auction/lot/" in href and href not in global_seen:
                            found.append(href)
                            global_seen.add(href)
                except Exception:
                    pass
        except Exception:
            pass
        return found

    for slug,source in AUCTION_HOUSE_BRANCHES.items():
        links=[]
        for page in (
            f"https://www.auctionhouse.co.uk/{slug}/commercial",
            f"https://www.auctionhouse.co.uk/{slug}/auction/search-results?searchType=1",
            f"https://www.auctionhouse.co.uk/{slug}/auction/future-auction-dates",
        ):
            links.extend(collect_links(page))

        branch=[]
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures={ex.submit(fetch,u):u for u in links[:220]}
            for f in as_completed(futures):
                u=futures[f]
                try:
                    row=_parse_auctionhouse_detail(f.result(),u,source)
                    if not row:
                        continue
                    low=(row.get("desc") or "").lower()
                    if any(x in low for x in ("sold prior","withdrawn","postponed")):
                        continue
                    if row.get("date") and row["date"]<"2026-08-26":
                        continue
                    branch.append(row)
                except Exception:
                    pass

        seen=set()
        for r in branch:
            if r.get("url") in seen:
                continue
            seen.add(r.get("url"))
            rows.append(r)

    return _clean_rows(rows)

def _parse_barnard_detail(page_html,url):
    s=BeautifulSoup(page_html,"lxml")
    text=norm(s.get_text(" ",strip=True))
    if not _commercial_admission("Barnard Marcus",s,text):
        return None

    h=s.find("h1")
    address=norm(h.get_text(" ",strip=True)) if h else ""
    if not address:
        return None

    gm=re.search(r"guide price\s*\*?\s*£([\d,]+)",text,re.I)
    guide=float(gm.group(1).replace(",","")) if gm else None
    lm=re.search(r"\bLOT\s+(\d+[A-Z]?)\b",text,re.I)
    lot="Lot "+lm.group(1) if lm else "Lot TBC"

    image=None
    for cand in _img_candidates(s,url):
        if "/media/" in cand.lower() and any(x in cand.lower() for x in (".jpg",".jpeg",".png",".webp")):
            image=cand
            break

    low=text.lower()
    return dict(
        source="Barnard Marcus",lot=lot,date="2026-09-10",address=address,
        guide=guide,rent=parse_rent(text),
        tenure=("Freehold" if "freehold" in low[:1800]
                else "Leasehold" if "leasehold" in low[:1800] else None),
        vat="UNKNOWN",url=url,desc=text[:1000],image=image
    )


@st.cache_data(ttl=21600, show_spinner=False)
def _catalogue_barnard_marcus():
    roots=[
        "https://www.barnardmarcusauctions.co.uk/",
        "https://www.barnardmarcusauctions.co.uk/auctions/10-september-2026/",
    ]
    lot_links=set()
    for root in roots:
        try:
            s=BeautifulSoup(fetch(root),"lxml")
            for a in s.find_all("a",href=True):
                href=urljoin(root,a["href"])
                if "/auctions/10-september-2026/" in href and re.search(r"/\d+/?$",href):
                    lot_links.add(href)
                # Follow catalogue/view-lots page once.
                label=norm(a.get_text(" ",strip=True)).lower()
                if "view lots" in label:
                    try:
                        ls=BeautifulSoup(fetch(href),"lxml")
                        for la in ls.find_all("a",href=True):
                            lh=urljoin(href,la["href"])
                            if "/auctions/10-september-2026/" in lh and re.search(r"/\d+/?$",lh):
                                lot_links.add(lh)
                    except Exception: pass
        except Exception:
            pass
    rows=[]
    for href in lot_links:
        try:
            row=_parse_barnard_detail(fetch(href),href)
            if row: rows.append(row)
        except Exception: pass
    return rows


@st.cache_data(ttl=21600, show_spinner=False)
def _pattinson_current():
    """Pattinson current online commercial auction lots from its commercial search feed."""
    base="https://www.pattinson.co.uk/commercial/property-search?searchType=CommercialSale"
    links=set()
    for page_no in range(1,9):
        page=base if page_no==1 else f"https://www.pattinson.co.uk/commercial/property-search?p={page_no}&searchType=CommercialSale"
        try:
            ls=BeautifulSoup(fetch(page),"lxml")
            for a in ls.find_all("a",href=True):
                href=urljoin(page,a["href"])
                if not re.search(r"/property/\d+",href):
                    continue
                node=a; card=norm(a.get_text(" ",strip=True))
                for _ in range(5):
                    node=getattr(node,"parent",None)
                    if node is None: break
                    t=norm(node.get_text(" ",strip=True))
                    if len(t)<1800 and ("Starting Bid" in t or "Current Bid" in t):
                        card=t; break
                low=card.lower()
                commercial=any(x in low for x in ("retail","commercial development","industrial","offices","office","hotel","leisure","drinking establishment","land & development","land in ","hot food takeaway","shop"))
                if commercial and ("starting bid" in low or "current bid" in low):
                    links.add(href)
        except Exception:
            pass
    rows=[]
    def build(href):
        try:
            ds=BeautifulSoup(fetch(href),"lxml")
            text=norm((ds.find("main") or ds).get_text(" ",strip=True))
            low=text.lower()
            if "starting bid" not in low and "current bid" not in low and "secure sale" not in low:
                return None
            h=ds.find("h1")
            ptitle=norm(h.get_text(" ",strip=True)) if h else ""
            # Pattinson puts the full address immediately after the H1. Prefer title metadata/address-like text.
            title_tag=ds.find("title")
            title_text=norm(title_tag.get_text(" ",strip=True)) if title_tag else ""
            address=title_text.split(" | ")[0] if " | " in title_text else ptitle
            gm=re.search(r"Starting\s*bid\s*£([\d,]+)",text,re.I)
            guide=float(gm.group(1).replace(',','')) if gm else None
            image=_property_image_from_soup(ds,href)
            tenure=("Freehold" if re.search(r"\bFreehold\b",text,re.I) else "Leasehold" if re.search(r"\bLeasehold\b",text,re.I) else None)
            return dict(source="Pattinson",lot="Online",date=None,address=address,guide=guide,rent=parse_rent(text),
                        tenure=tenure,vat="UNKNOWN",url=href,desc=text[:1800],image=image)
        except Exception:
            return None
    with ThreadPoolExecutor(max_workers=12) as ex:
        futures=[ex.submit(build,u) for u in list(links)[:160]]
        for f in as_completed(futures):
            r=f.result()
            if r: rows.append(r)
    return _clean_rows(rows)

def _enrich_exact_rows(rows, source_name, limit=220):
    out=[dict(r) for r in (rows or [])]
    targets=[i for i,r in enumerate(out) if r.get("url")][:limit]
    def one(i):
        r=out[i]
        try:
            facts=extract_particulars(fetch(r["url"]),source_name,r["url"])
            return i,merge_enrichment(r,facts)
        except Exception:
            return i,r
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures=[ex.submit(one,i) for i in targets]
        for f in as_completed(futures):
            i,r=f.result(); out[i]=r
    return out

def _merge_catalogue_rows(base_rows):
    current={}
    for x in base_rows:
        current.setdefault(x["source"],[]).append(x)

    source_functions=[
        ("Auction House London",_catalogue_ahl),
        ("Savills Auctions",_catalogue_savills),
        ("Bond Wolfe",_bond_wolfe_current),
        ("Strettons",_strettons_current),
        ("Acuitus",_acuitus_current),
        ("Pattinson",_pattinson_current),
        ("Barnard Marcus",_catalogue_barnard_marcus),
        ("Auction House Regional",_catalogue_auctionhouse_regional),
    ]
    for source,fn in source_functions:
        try: rows=fn()
        except Exception: rows=[]
        if rows:
            if source=="Bond Wolfe":
                rows=_enrich_exact_rows(rows,"Bond Wolfe")
            if source=="Auction House Regional":
                # Preserve each regional branch as its own source.
                for r in rows:
                    current.setdefault(r["source"],[])
                    existing={x.get("url") for x in current[r["source"]]}
                    if r.get("url") not in existing:
                        current[r["source"]].append(r)
            else:
                current[source]=rows

    merged=[]
    for rows in current.values():
        merged.extend(rows)
    return _clean_rows(merged)


@st.cache_data(ttl=21600, show_spinner=False)
def _exact_property_image(url):
    if not url:
        return None
    try:
        s=BeautifulSoup(fetch(url),"lxml")
        og=s.find("meta",attrs={"property":"og:image"})
        if og and og.get("content"):
            cand=urljoin(url,og["content"])
            if not any(x in cand.lower() for x in ("logo","favicon","icon","placeholder","sprite","avatar")):
                return cand
        scored=[]
        for img in s.find_all("img"):
            raw=img.get("data-src") or img.get("data-lazy-src") or img.get("data-original") or img.get("src")
            if not raw:
                continue
            cand=urljoin(url,raw)
            lc=cand.lower()
            if any(x in lc for x in ("logo","favicon","icon","placeholder","sprite","avatar","tracking")):
                continue
            alt=norm(img.get("alt","")).lower()
            score=0
            if any(x in lc for x in ("/uploads/","/properties/","/property/","/lots/","/images/")):
                score+=3
            if any(x in alt for x in ("property","auction","front","external","exterior")):
                score+=2
            scored.append((score,cand))
        scored.sort(reverse=True,key=lambda x:x[0])
        return scored[0][1] if scored and scored[0][0]>0 else None
    except Exception:
        return None

def _best_exact_page_image(url):
    try:
        s=BeautifulSoup(fetch(url),"lxml")
        img=_property_image_from_soup(s,url)
        if "auctions.savills.co.uk" in (url or "") and _is_savills_brand_image(img):
            return None
        return img
    except Exception:
        return None


def _enrich_missing_images(rows,limit=220):
    out=[dict(r) for r in rows]
    missing=[i for i,r in enumerate(out) if not r.get("image") and r.get("url")]
    missing=missing[:limit]

    def get_one(i):
        r=out[i]
        src=(r.get("source") or "").lower()
        try:
            s=BeautifulSoup(fetch(r["url"]),"lxml")
            # source-specific gallery patterns
            candidates=_img_candidates(s,r["url"])
            preferred=[]
            for c in candidates:
                lc=c.lower()
                if "auctionhouse.co.uk" in r["url"] and "/lot-image/" in lc:
                    preferred.append(c)
                elif "bondwolfe.com" in r["url"] and "cdn.eigpropertyauctions.co.uk/ams/images/" in lc:
                    preferred.append(c)
                elif "barnardmarcusauctions.co.uk" in r["url"] and "/media/" in lc:
                    preferred.append(c)
                elif ("pugh-auctions.com" in r["url"] or "btgeddisonspropertyauctions.com" in r["url"]):
                    # Exact-gallery matching below; never trust the asta host by itself.
                    pass
                elif "auctionhouselondon.co.uk" in r["url"]:
                    preferred.append(c)
            if "pugh-auctions.com" in r["url"] or "btgeddisonspropertyauctions.com" in r["url"]:
                gallery=_btg_gallery_images(s,r["url"])
                return i,(gallery[0] if gallery else None)
            return i,(preferred[0] if preferred else (candidates[0] if candidates else None))
        except Exception:
            return i,None

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures=[ex.submit(get_one,i) for i in missing]
        for f in as_completed(futures):
            i,img=f.result()
            if img:
                out[i]["image"]=img

    # Savills verified map always wins for current lots.
    for i,r in enumerate(out):
        if r.get("source")=="Savills Auctions":
            try:
                out[i]=_apply_verified_savills_current(r)
            except Exception:
                pass
    return out


def _merge_property_rows(existing, incoming, seed_authoritative=False):
    """
    Merge two records for the same property without throwing away richer fields.

    If seed_authoritative=True, verified financial/tenure facts from the seed win,
    while richer cache/live metadata (especially images) can fill gaps.
    """
    if not existing:
        return dict(incoming or {})
    if not incoming:
        return dict(existing)

    out=dict(existing)

    # Fields where richer incoming data should fill a blank existing value.
    fill_fields=("image","area_sqft","area_sqm","tenant","lease_term","lease_start",
                 "lease_expiry","break_clause","rent_review","erv","fri","legal_pack",
                 "epc","rateable_value","service_charge","ground_rent")
    for k in fill_fields:
        if not out.get(k) and incoming.get(k):
            out[k]=incoming[k]

    # Prefer longer non-generic descriptions because they feed analysis.
    old_desc=str(out.get("desc") or "")
    new_desc=str(incoming.get("desc") or "")
    if len(new_desc) > len(old_desc):
        out["desc"]=incoming["desc"]

    # Exact URL can improve navigation if existing URL is blank/generic.
    old_url=out.get("url") or ""
    generic_url=(
        not old_url
        or old_url.endswith("/page-1/quantity-100/property_type-253/sort-by-0")
        or "/auction-commercial-property/for-sale" in old_url
        or "/find-a-property" in old_url
        or "/property-search" in old_url
        or "/auctions/live-stream/" in old_url
    )
    if incoming.get("url") and generic_url:
        out["url"]=incoming["url"]

    # For ordinary cache/live rows, fill/refresh core facts where incoming has evidence.
    if not seed_authoritative:
        for k in ("guide","rent","tenure","vat","date","lot","address"):
            if incoming.get(k) not in (None,"","UNKNOWN"):
                out[k]=incoming[k]
    else:
        # Seed verified facts remain authoritative, but fill genuine blanks.
        for k in ("guide","rent","tenure","vat","date","lot","address"):
            if out.get(k) in (None,"","UNKNOWN") and incoming.get(k) not in (None,"","UNKNOWN"):
                out[k]=incoming[k]

    return out

def _merge_property_universe(seed_rows, cached_rows):
    universe={}
    seed_keys=set()

    for row in seed_rows:
        if not _should_keep_commercial_row(row.get("source"),row.get("address"),row.get("desc")):
            continue
        r=dict(row)
        if r.get("source")=="Savills Auctions":
            r=_apply_verified_savills_current(r)
        k=_canonical_key(r)
        universe[k]=r
        seed_keys.add(k)

    for row in cached_rows:
        if not _should_keep_commercial_row(row.get("source"),row.get("address"),row.get("desc")):
            continue
        r=dict(row)
        if r.get("source")=="Savills Auctions":
            r=_apply_verified_savills_current(r)
        k=_canonical_key(r)
        if k in universe:
            universe[k]=_merge_property_rows(universe[k],r,seed_authoritative=(k in seed_keys))
            if universe[k].get("source")=="Savills Auctions":
                universe[k]=_apply_verified_savills_current(universe[k])
        else:
            universe[k]=r

    return _clean_rows(list(universe.values()))


def _hydrate_snapshot_images(rows):
    """
    Safe bounded image hydration for the already-loaded snapshot.
    Never blanks or blocks the board if a page fails.
    """
    out=[]
    targets=("auction house london","bond wolfe","barnard marcus","pugh","btg")
    for row in rows:
        r=dict(row)

        # Savills uses its verified image map.
        if r.get("source")=="Savills Auctions":
            try:
                r=_apply_verified_savills_current(r)
            except Exception:
                pass

        # For other known sources, attempt exact-page image only when missing.
        if not r.get("image") and any(t in (r.get("source") or "").lower() for t in targets):
            try:
                img=_exact_property_image(r.get("url"))
                if img:
                    r["image"]=img
            except Exception:
                pass

        out.append(r)
    return out

def _apply_seed_image_map(rows):
    out=[]
    for row in rows:
        r=dict(row)
        if not r.get("image") and r.get("url") in VERIFIED_SEED_IMAGES:
            r["image"]=VERIFIED_SEED_IMAGES[r["url"]]
        if r.get("source")=="Savills Auctions":
            try:
                r=_apply_verified_savills_current(r)
            except Exception:
                pass
        out.append(r)
    return out

@st.cache_data(ttl=21600, show_spinner=False)
def _pugh_seed_exact_rows(targets):
    """Hydrate only the known Pugh/BTG commercial seed lots from exact pages.

    This avoids crawling every residential lot at startup while ensuring that
    the verified Pugh/BTG cards do not boot with generic catalogue URLs and no images.
    """
    catalogue="https://www.btgeddisonspropertyauctions.com/auctions/live-stream/august-2026?auction_id=17&date_added=0&limit=0&radius=1&search_type=auction&view=grid"
    try:
        s=BeautifulSoup(fetch(catalogue),"lxml")
        # Cache exact lot links and labels once, then match each seed robustly.
        links=[]
        for a in s.find_all("a",href=True):
            href=urljoin(catalogue,a["href"])
            if "/properties/" not in href:
                continue
            label=norm(a.get_text(" ",strip=True)).lower()
            if label:
                links.append((label,href))

        def tokens(text):
            cleaned=re.sub(r"[^a-z0-9]+"," ",(text or "").lower())
            stop={"the","and","of","at","in","on","greater","county"}
            return {x for x in cleaned.split() if x not in stop and (len(x)>2 or x.isdigit())}

        wanted=[]
        used=set()
        for lot,address in targets:
            addr=norm(address).lower()
            best_url=None
            best_score=0.0
            target=tokens(addr)
            for label,href in links:
                if href in used:
                    continue
                if label==addr or label in addr or addr in label:
                    best_url=href; best_score=1.0; break
                candidate=tokens(label)
                common=len(target & candidate)
                # Coverage against the shorter target is deliberately used because
                # BTG often adds street, county and postcode detail to the seed label.
                score=(common/max(1,len(target)))
                if common>=3 and score>best_score:
                    best_score=score; best_url=href
            if best_url and best_score>=0.55:
                wanted.append((lot,best_url))
                used.add(best_url)

        hydrated=[]
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures={ex.submit(_exact_page_card,u,"Pugh / BTG Eddisons","2026-08-27",True):(lot,u) for lot,u in wanted}
            for f in as_completed(futures):
                lot,u=futures[f]
                try:
                    r=f.result()
                    if r:
                        r["lot"]=lot
                        r["url"]=u
                        hydrated.append(r)
                except Exception:
                    pass
        return hydrated
    except Exception:
        return []

def _hydrate_pugh_seed_rows(rows):
    missing=[r for r in rows if r.get("source")=="Pugh / BTG Eddisons" and (not r.get("image") or "/auctions/live-stream/" in (r.get("url") or "") or "pugh-auctions.com/property/" in (r.get("url") or ""))]
    if not missing:
        return rows

    # Never rediscover an exact current BTG URL we already know. Percy Street is
    # a useful example: its catalogue card has partner-agent markup around the
    # link, but the exact property URL itself is stable and fully verifiable.
    direct=[]
    discover=[]
    for r in missing:
        u=r.get("url") or ""
        if "btgeddisonspropertyauctions.com/properties/" in u:
            direct.append((r.get("lot") or "Lot TBC",u))
        elif r.get("address"):
            discover.append((r.get("lot") or "Lot TBC",r.get("address") or ""))

    live=[]
    if direct:
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures={ex.submit(_exact_page_card,u,"Pugh / BTG Eddisons","2026-08-27",True):(lot,u) for lot,u in direct}
            for f in as_completed(futures):
                lot,u=futures[f]
                try:
                    rec=f.result()
                    if rec:
                        rec["lot"]=lot
                        rec["url"]=u
                        live.append(rec)
                except Exception:
                    pass
    if discover:
        live.extend(_pugh_seed_exact_rows(tuple(discover)))

    if not live:
        return rows
    return _merge_property_universe(rows,live)

@st.cache_data(ttl=21600, show_spinner=False)
def _strettons_seed_exact_rows(target_lots):
    """Resolve known Strettons seed lots to exact current property pages."""
    listing="https://www.strettons.co.uk/auction-commercial-property/for-sale/"
    wanted=set(target_lots)
    if not wanted:
        return []
    try:
        soup=BeautifulSoup(fetch(listing),"lxml")
        links={}
        for a in soup.find_all("a",href=True):
            href=urljoin(listing,a["href"])
            if "/auction-commercial-property-for-sale/" not in href:
                continue
            node=a; card=""
            for _ in range(9):
                node=getattr(node,"parent",None)
                if node is None: break
                t=norm(node.get_text(" ",strip=True))
                if re.search(r"10 Sep 26\s*-\s*Lot\s+\d+",t,re.I) and len(t)<5000:
                    card=t; break
            if not card: continue
            m=re.search(r"10 Sep 26\s*-\s*Lot\s+(\d+[A-Z]?)",card,re.I)
            if not m: continue
            lot="Lot "+m.group(1)
            if lot in wanted:
                links[lot]=href

        live=[]
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures={ex.submit(_exact_page_card,u,"Strettons","2026-09-10",True):(lot,u) for lot,u in links.items()}
            for f in as_completed(futures):
                lot,u=futures[f]
                try:
                    rec=f.result()
                    if rec:
                        rec["lot"]=lot
                        rec["url"]=u
                        live.append(rec)
                except Exception:
                    pass
        return live
    except Exception:
        return []

def _hydrate_strettons_seed_rows(rows):
    missing=[r for r in rows if r.get("source")=="Strettons" and (not r.get("image") or "/auction-commercial-property/for-sale" in (r.get("url") or ""))]
    if not missing:
        return rows

    live=[]
    discover=[]
    direct=[]
    for r in missing:
        u=r.get("url") or ""
        if "/auction-commercial-property-for-sale/" in u:
            direct.append((r.get("lot") or "Lot TBC",u))
        elif r.get("lot"):
            discover.append(r.get("lot"))

    def hydrate_exact(item):
        lot,u=item
        try:
            ds=BeautifulSoup(fetch(u),"lxml")
            img=_strettons_exact_image(ds,u)
            main=ds.find("main") or ds
            text=norm(main.get_text(" ",strip=True))
            h=ds.find("h1")
            address=norm(h.get_text(" ",strip=True)) if h else ""
            gm=re.search(r"Guide Price\s*£?\s*([\d,]+)",text,re.I)
            guide=float(gm.group(1).replace(',','')) if gm else None
            low=text.lower()
            return dict(source="Strettons",lot=lot,date="2026-09-10",address=address,
                        guide=guide,rent=parse_rent(text),
                        tenure=("Freehold" if "freehold" in low[:2200] else "Leasehold" if "leasehold" in low[:2200] else None),
                        vat="UNKNOWN",url=u,desc=text[:1800],image=img)
        except Exception:
            return None

    if direct:
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures=[ex.submit(hydrate_exact,x) for x in direct]
            for f in as_completed(futures):
                rec=f.result()
                if rec and rec.get("image"):
                    live.append(rec)
    if discover:
        live.extend(_strettons_seed_exact_rows(tuple(discover)))
    if not live:
        return rows
    return _merge_property_universe(rows,live)


def _hydrate_acuitus_images(rows):
    """Hydrate missing Acuitus previews from exact /property/<id>/ pages."""
    out=[dict(r) for r in rows]
    targets=[i for i,r in enumerate(out) if r.get("source")=="Acuitus" and not r.get("image") and "/property/" in (r.get("url") or "").lower()]
    if not targets:
        return out
    def one(i):
        try:
            u=out[i].get("url")
            ds=BeautifulSoup(fetch(u),"lxml")
            return i,_property_image_from_soup(ds,u)
        except Exception:
            return i,None
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs=[ex.submit(one,i) for i in targets]
        for f in as_completed(futs):
            i,img=f.result()
            if img:
                out[i]["image"]=img
    return out

def load_rows():
    """
    Fast, non-destructive boot.

    Fresh deployments use the full verified snapshot.
    Existing deployments use the stable cache.
    Legacy versioned caches are consulted only once, and only when no stable
    cache exists, preventing old/stale rows from being resurrected forever.
    """
    stable=Path("auction_sniper_cache.json")
    candidates=[]
    if stable.exists():
        candidates=[stable]
    else:
        legacy=sorted(Path(".").glob("auction_sniper_cache_v*.json"),
                      key=lambda p:p.stat().st_mtime if p.exists() else 0,
                      reverse=True)
        if legacy:
            candidates=[legacy[0]]

    cached_rows=[]
    health=SOURCE_HEALTH
    updated="Verified snapshot · 26 Aug 2026"

    for path in candidates:
        try:
            cached=json.loads(path.read_text(encoding="utf-8"))
            props=cached.get("properties") or []
            if props:
                cached_rows.extend(props)
                if cached.get("health"):
                    health=cached["health"]
                if cached.get("updated"):
                    updated=cached["updated"]
        except Exception:
            pass

    # Merge the scheduled production snapshot generated by GitHub Actions.
    snapshot_path=Path("data/properties.json")
    if snapshot_path.exists():
        try:
            snap=json.loads(snapshot_path.read_text(encoding="utf-8"))
            live_rows=[]
            for x in snap.get("properties") or []:
                live_rows.append(dict(
                    source=x.get("source"),
                    lot=x.get("lot_number") or "Lot TBC",
                    date=x.get("auction_date"),
                    address=x.get("address") or "",
                    guide=x.get("guide_price"),
                    rent=x.get("annual_rent"),
                    tenure=x.get("tenure") or "UNKNOWN",
                    vat=x.get("vat_status") or "UNKNOWN",
                    url=x.get("url") or "",
                    desc=x.get("description") or "",
                    image=x.get("image_url"),
                    legal_pack_status=x.get("legal_pack_status") or "UNKNOWN",
                    legal_pack_url=x.get("legal_pack_url"),
                    status=x.get("status") or "Live",
                ))
            if live_rows:
                cached_rows.extend(live_rows)
                generated=snap.get("generated_at")
                if generated:
                    updated=f"Collector snapshot · {generated[:16].replace('T',' ')} UTC"
        except Exception:
            pass

    rows=_merge_property_universe(SEED,cached_rows)
    rows=_apply_seed_image_map(rows)
    # Pugh/BTG seed records historically used a generic catalogue URL, so no
    # property image could render until a manual full refresh. Hydrate just the
    # known commercial Pugh/BTG cards from their exact current lot pages.
    rows=_hydrate_pugh_seed_rows(rows)
    # Strettons seed rows also begin with the generic commercial catalogue URL.
    # Resolve the current lot cards to exact property pages at boot so preview
    # images and exact navigation work before a manual full refresh.
    rows=_hydrate_strettons_seed_rows(rows)
    rows=_hydrate_acuitus_images(rows)
    return rows,health,updated


RESIDENTIAL_EXACT_TYPES = {
    "detached house","semi-detached house","semi detached house","terraced house",
    "end of terrace house","end terrace house","bungalow","flat","apartment",
    "maisonette","residential property"
}
COMMERCIAL_EXACT_TYPES = {
    "commercial property","mixed use","mixed-use","commercial investment",
    "commercial vacant","retail","retail property","office","offices",
    "industrial","industrial property","warehouse","care home","public house",
    "restaurant","business premises"
}

def _structured_property_type(soup):
    """Read the actual auctioneer property-type label, not marketing prose."""
    # Prefer short list/badge-like elements.
    candidates=[]
    for tag in soup.find_all(["li","span","div","p","strong"]):
        t=norm(tag.get_text(" ",strip=True))
        if 2 <= len(t) <= 60:
            candidates.append(t)
    for t in candidates:
        low=t.lower().strip(" :|")
        if low in RESIDENTIAL_EXACT_TYPES or low in COMMERCIAL_EXACT_TYPES:
            return low
    # BTG exposes 'Property Type Commercial Property' in plain text.
    text=norm(soup.get_text(" ",strip=True))
    m=re.search(r"Property Type\s+(Commercial Property|Mixed[- ]Use|Retail Property|Office|Industrial Property|Warehouse|Care Home|Public House|Restaurant)",text,re.I)
    return m.group(1).lower() if m else None

def _commercial_admission(source, soup, text):
    """
    Fail closed for residential-heavy sources.
    Ordinary houses/flats do not enter merely because the prose says investment.
    """
    ptype=_structured_property_type(soup)
    sl=(source or "").lower()
    low=(text or "").lower()

    if ptype in RESIDENTIAL_EXACT_TYPES:
        return False
    if ptype in COMMERCIAL_EXACT_TYPES:
        return True

    # Barnard Marcus and regional Auction House: require explicit mixed/commercial
    # evidence if no structured badge was found.
    if "barnard marcus" in sl or (sl.startswith("auction house ") and "london" not in sl):
        positive=("mixed-use","mixed use","ground floor retail","commercial unit",
                  "commercial property","retail premises","office building",
                  "industrial property","warehouse","care home","public house")
        residential=(" bedroom house"," bedroom flat","bungalow","terraced house",
                     "semi-detached house","detached house","apartment","maisonette")
        return any(x in low for x in positive) and not any(x in low for x in residential)

    return True

# ---------------- expanded source coverage ----------------
@st.cache_data(ttl=21600, show_spinner=False)
def _exact_page_card(url, source, auction_date, force_commercial=False):
    try:
        s=BeautifulSoup(fetch(url),"lxml")
        h1=s.find("h1")
        address=norm(h1.get_text(" ",strip=True)) if h1 else url
        main=s.find("main") or s
        text=norm(main.get_text(" ",strip=True))
        low=text.lower()

        if "sold prior" in low or "withdrawn prior" in low or "withdrawn from auction" in low:
            return None

        # Bond Wolfe exposes explicit categories such as Commercial Investment,
        # Commercial Vacant, Mixed Use and Residential Investment.
        if not force_commercial:
            if "bond wolfe" in source.lower():
                if "residential investment" in low or "residential vacant" in low:
                    if not any(x in low for x in ("mixed use","commercial investment","commercial vacant")):
                        return None
                if not any(x in low for x in ("commercial investment","commercial vacant","mixed use","commercial property")):
                    return None
            elif not _commercial_admission(source,s,text):
                return None

        image=None
        candidates=_img_candidates(s,url)

        # Strettons property photos are embedded in page data rather than ordinary <img> tags.
        # Use the verified api_sources extractor before generic image selection.
        if "strettons.co.uk" in (url or "").lower():
            image=_strettons_exact_image(s,url)

        # BTG/Pugh: host alone is not proof of a property photograph. Only the
        # exact property's own artnr_<property-key> gallery folder is trusted.
        if "btgeddisonspropertyauctions.com" in (url or "").lower() or "pugh-auctions.com" in (url or "").lower():
            gallery=_btg_gallery_images(s,url)
            if gallery:
                image=gallery[0]
            elif "pugh-auctions.com" in (url or "").lower():
                # Legacy Pugh page -> exact BTG lot page -> exact gallery.
                for a in s.find_all("a",href=True):
                    exact=urljoin(url,a["href"])
                    if "btgeddisonspropertyauctions.com/properties/" not in exact.lower():
                        continue
                    try:
                        bs=BeautifulSoup(fetch(exact),"lxml")
                        g=_btg_gallery_images(bs,exact)
                        if g:
                            image=g[0]
                            break
                    except Exception:
                        pass

        preferred=(
            "/lot-image/",
            "cdn.eigpropertyauctions.co.uk/ams/images/",
            "/media/",
            "resize.auctions.savills.co.uk",
        )
        if not image:
            for cand in candidates:
                if any(x in cand.lower() for x in preferred):
                    image=cand
                    break

        # BTG can serve property photographs from changing CDN hosts. The old
        # whitelist silently threw those photographs away. Fall back to the
        # first credible image from the exact property page.
        if not image and not ("btgeddisonspropertyauctions.com" in (url or "").lower() or "pugh-auctions.com" in (url or "").lower()):
            for cand in candidates:
                lc=cand.lower()
                if any(x in lc for x in ("logo","favicon","icon","placeholder",
                                         "agent","staff","avatar","background",
                                         "facebook","instagram","linkedin","youtube")):
                    continue
                if re.search(r"\.(?:jpe?g|png|webp)(?:\?|$)",lc) or "image" in lc or "upload" in lc:
                    image=cand
                    break

        # BTG metadata may be joint-agent artwork; never use it as lot imagery.
        if not image and not ("btgeddisonspropertyauctions.com" in (url or "").lower() or "pugh-auctions.com" in (url or "").lower()):
            for attrs in (
                {"property":"og:image"},
                {"name":"twitter:image"},
                {"property":"twitter:image"},
            ):
                meta=s.find("meta",attrs=attrs)
                if meta and meta.get("content"):
                    cand=urljoin(url,meta["content"])
                    if not any(x in cand.lower() for x in ("logo","favicon","icon","placeholder")):
                        image=cand
                        break

        gm=re.search(r"Guide price\*?\s*(?:£)?\s*([\d,]+)",text,re.I)
        if not gm:
            gm=re.search(r"Guide(?: Price)?\s*[:|]?\s*£\s*([\d,]+)",text,re.I)
        guide=float(gm.group(1).replace(",","")) if gm else None
        rent=parse_rent(text)
        lm=re.search(r"\bLot\s+(\d+[A-Z]?)\b",text,re.I)
        lot="Lot "+lm.group(1) if lm else "Lot TBC"
        tenure=("Freehold" if "freehold" in low else "Leasehold" if "leasehold" in low else None)

        return dict(source=source,lot=lot,date=auction_date,address=address,
                    guide=guide,rent=rent,tenure=tenure,vat="UNKNOWN",
                    url=url,desc=text[:900],image=image)
    except Exception:
        return None


@st.cache_data(ttl=21600, show_spinner=False)
def _bond_wolfe_current():
    order="https://www.bondwolfe.com/order-of-sale/"
    try:
        soup=BeautifulSoup(fetch(order),"lxml")
        links=[]
        for a in soup.find_all("a",href=True):
            txt=norm(a.get_text(" ",strip=True))
            low=txt.lower()
            if not re.search(r"\bLot\s+\d+",txt,re.I):
                continue
            if any(x in low for x in ("sold prior","withdrawn")):
                continue
            if not any(x in low for x in ("commercial investment","commercial vacant","mixed use")):
                continue
            href=urljoin(order,a["href"])
            if "/auctions/properties/" in href and href not in links:
                links.append(href)
        rows=[]
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs=[ex.submit(_exact_page_card,u,"Bond Wolfe","2026-09-10",True) for u in links]
            for f in as_completed(futs):
                r=f.result()
                if r: rows.append(r)
        return _clean_rows(rows)
    except Exception:
        return []


@st.cache_data(ttl=21600, show_spinner=False)
def _strettons_current():
    """
    Current 10 Sep commercial catalogue only.
    Follow exact /auction-commercial-property-for-sale/ pages so images,
    size, tenure, rent and legal-document evidence come from the lot itself.
    """
    listing="https://www.strettons.co.uk/auction-commercial-property/for-sale/"
    try:
        soup=BeautifulSoup(fetch(listing),"lxml")
        links={}
        for a in soup.find_all("a",href=True):
            href=urljoin(listing,a["href"])
            if "/auction-commercial-property-for-sale/" not in href:
                continue

            # Associate exact link with closest current September lot card.
            node=a
            card=""
            for _ in range(9):
                node=getattr(node,"parent",None)
                if node is None:
                    break
                t=norm(node.get_text(" ",strip=True))
                if re.search(r"10 Sep 26\s*-\s*Lot\s+\d+",t,re.I) and len(t)<5000:
                    card=t
                    break
            if not card:
                continue
            m=re.search(r"10 Sep 26\s*-\s*Lot\s+(\d+[A-Z]?)",card,re.I)
            if not m:
                continue
            links["Lot "+m.group(1)]=href

        def build(item):
            lot,href=item
            try:
                s=BeautifulSoup(fetch(href),"lxml")
                main=s.find("main") or s
                text=norm(main.get_text(" ",strip=True))
                low=text.lower()

                if "sold prior" in low or "withdrawn" in low:
                    return None

                h=s.find("h1")
                address=norm(h.get_text(" ",strip=True)) if h else ""
                if not address:
                    return None

                gm=re.search(r"Guide Price\s*£?\s*([\d,]+)",text,re.I)
                guide=float(gm.group(1).replace(",","")) if gm else None
                rent=parse_rent(text)

                # Strettons: choose the image from the exact property page, not
                # the catalogue card. This catches lazy/srcset/OG gallery images.
                image=_strettons_exact_image(s,href) or _property_image_from_soup(s,href)
                if not image:
                    imgs=_img_candidates(s,href)
                    for cand in imgs:
                        lc=cand.lower()
                        if any(x in lc for x in ("logo","agent","staff","avatar","icon","social")):
                            continue
                        image=cand
                        break

                # Preserve the rich exact-page text; this feeds lease/size analysis.
                tenure=("Freehold" if re.search(r"\bFREEHOLD\b",text,re.I)
                        else "Leasehold" if re.search(r"\bLEASEHOLD\b",text,re.I)
                        else None)

                return dict(
                    source="Strettons",lot=lot,date="2026-09-10",
                    address=address,guide=guide,rent=rent,tenure=tenure,
                    vat="UNKNOWN",url=href,desc=text[:1800],image=image
                )
            except Exception:
                return None

        rows=[]
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures=[ex.submit(build,item) for item in links.items()]
            for f in as_completed(futures):
                r=f.result()
                if r:
                    rows.append(r)

        return _clean_rows(rows)
    except Exception:
        return []


@st.cache_data(ttl=21600, show_spinner=False)
def _acuitus_current():
    """Current Acuitus catalogue enriched from each exact property page.

    Acuitus publishes materially richer particulars on the detail page than on
    the search card: rent, VAT, EPC bands and tenancy/accommodation tables. We
    parse those exact pages and keep their structured facts rather than reducing
    them to the thin catalogue card.
    """
    listing="https://www.acuitus.co.uk/find-a-property/?clear=y"

    def num(v):
        try:return float(re.sub(r"[^0-9.]","",str(v)))
        except Exception:return None

    def exact_row(href,card=""):
        try:
            raw=fetch(href)
            ds=BeautifulSoup(raw,"lxml")
            main=ds.find("main") or ds
            text=norm(main.get_text(" ",strip=True))
            h=ds.find("h1")
            address=norm(h.get_text(" ",strip=True)) if h else ""
            if not address:return None

            lm=re.search(r"\bLot\s*(\d+[A-Z]?)\b",text,re.I)
            lot="Lot "+lm.group(1).upper() if lm else "Lot TBC"
            gm=re.search(r"\bGuide\*?\s*£\s*([\d,]+(?:\.\d+)?)",text,re.I)
            guide=float(gm.group(1).replace(',','')) if gm else None
            rm=re.search(r"\bRent\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:per\s+annum|p\.?a\.?|pa)\b",text,re.I)
            rent=float(rm.group(1).replace(',','')) if rm else None

            tenure=("Freehold" if re.search(r"\bFreehold\b",text,re.I)
                    else "Leasehold" if re.search(r"\bLeasehold\b",text,re.I) else None)
            vat=("NOT APPLICABLE" if re.search(r"VAT\s+(?:is\s+)?not\s+(?:applicable|payable)",text,re.I)
                 else "APPLICABLE" if re.search(r"VAT\s+(?:is\s+)?applicable|VAT\s+is\s+payable",text,re.I)
                 else "UNKNOWN")

            epc=None
            epc_section=re.search(r"\bEPC\b(.{0,180})",text,re.I)
            if epc_section:
                part=epc_section.group(1)
                bands=[]
                bm=re.search(r"Band\s+([A-G](?:\s*(?:,|and|&)\s*[A-G])+)",part,re.I)
                if bm:
                    bands=re.findall(r"[A-G]",bm.group(1).upper())
                if not bands:
                    bands=re.findall(r"\b([A-G])\b",part[:100].upper())
                bands=list(dict.fromkeys(bands))
                if bands:epc=" / ".join(bands)

            total_sqm=None;total_sqft=None;accommodation=[]
            for table in ds.find_all("table"):
                rows=[]
                for tr in table.find_all("tr"):
                    cells=[norm(c.get_text(" ",strip=True)) for c in tr.find_all(["th","td"])]
                    if cells:rows.append(cells)
                if not rows:continue
                header=" | ".join(rows[0]).lower()
                looks_accom=("floor" in header and ("sq m" in header or "sqm" in header or "sq ft" in header or "sqft" in header))
                if not looks_accom and "accommodation" not in norm(table.get_text(" ",strip=True)).lower():
                    continue
                sqm_idx=next((i for i,x in enumerate(rows[0]) if re.search(r"sq\s*m|sqm",x,re.I)),None)
                sqft_idx=next((i for i,x in enumerate(rows[0]) if re.search(r"sq\s*ft|sqft",x,re.I)),None)
                for cells in rows[1:]:
                    label=" / ".join(cells[:2]).strip(" /")
                    is_total=bool(cells and re.search(r"\btotal\b",cells[0],re.I))
                    sqm=num(cells[sqm_idx]) if sqm_idx is not None and sqm_idx<len(cells) else None
                    sqft=num(cells[sqft_idx]) if sqft_idx is not None and sqft_idx<len(cells) else None
                    if is_total:
                        if sqm:total_sqm=sqm
                        if sqft:total_sqft=sqft
                    elif label and (sqm or sqft):
                        bits=[label]
                        if sqm:bits.append(f"{sqm:,.2f} sq m")
                        if sqft:bits.append(f"{sqft:,.0f} sq ft")
                        accommodation.append(" · ".join(bits))
                if total_sqm or total_sqft or accommodation:
                    break

            if not total_sqm:
                tm=re.search(r"\bTotal\b[^0-9]{0,40}([\d,.]+)\s*(?:sq\.?\s*m|sqm|m²)",text,re.I)
                if tm:total_sqm=float(tm.group(1).replace(',',''))
            if not total_sqft:
                tf=re.search(r"\bTotal\b.{0,90}?([\d,]+)\s*(?:sq\.?\s*ft|sqft|ft²)",text,re.I)
                if tf:total_sqft=float(tf.group(1).replace(',',''))
            if total_sqm and not total_sqft:total_sqft=round(total_sqm*10.7639)
            if total_sqft and not total_sqm:total_sqm=round(total_sqft/10.7639,2)

            facts=extract_particulars(raw,"Acuitus",href)
            row=dict(source="Acuitus",lot=lot,date="2026-09-17",address=address,
                     guide=guide,rent=rent,tenure=tenure,vat=vat,url=href,
                     desc=text[:3500],image=_property_image_from_soup(ds,href),
                     epc=epc,area_sqm=total_sqm,area_sqft=total_sqft,
                     accommodation_summary=" | ".join(accommodation[:8]) or None)
            row=merge_enrichment(row,facts)
            if epc:row["epc"]=epc
            if total_sqm:row["area_sqm"]=total_sqm
            if total_sqft:row["area_sqft"]=total_sqft
            if accommodation:row["accommodation_summary"]=" | ".join(accommodation[:8])
            if guide is not None:row["guide"]=guide
            if rent is not None:row["rent"]=rent
            if tenure:row["tenure"]=tenure
            if vat!="UNKNOWN":row["vat"]=vat
            return row
        except Exception:
            return None

    try:
        soup=BeautifulSoup(fetch(listing),"lxml")
        links=[];cards={}
        for a in soup.find_all("a",href=True):
            href=urljoin(listing,a["href"]).split('#')[0]
            if not re.search(r"https?://(?:www\.)?acuitus\.co\.uk/property/\d+/?$",href,re.I):continue
            if href not in links:links.append(href)
            node=a;card=""
            for _ in range(7):
                node=getattr(node,"parent",None)
                if node is None:break
                t=norm(node.get_text(" ",strip=True))
                if len(t)<5000 and ("Guide" in t or "17/09/2026" in t):card=t
            cards[href]=card
        rows=[]
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures={ex.submit(exact_row,u,cards.get(u,"")):u for u in links[:80]}
            for f in as_completed(futures):
                r=f.result()
                if r:rows.append(r)
        return _clean_rows(rows)
    except Exception:
        return []

# ---------------- live refresh (non-blocking until user asks) ----------------
MONEY_RE=re.compile(r"£\s*([\d,]+(?:\.\d{1,2})?)")

def norm(s):
    return re.sub(r"\s+"," ",s or "").strip()

def fetch(url):
    r=requests.get(url,headers=HEADERS,timeout=TIMEOUT)
    r.raise_for_status()
    return r.text

def parse_money(text):
    m=MONEY_RE.search(text or "")
    return float(m.group(1).replace(",","")) if m else None

def parse_rent(text):
    vals=[]
    for m in re.finditer(r"£\s*([\d,]+(?:\.\d+)?)\s*(?:per annum|p\.?a\.?|pa)\b",text or "",re.I):
        v=float(m.group(1).replace(",",""))
        if 500<=v<=5_000_000: vals.append(v)
    return max(vals) if vals else None

def _exact_preview(url):
    s=BeautifulSoup(fetch(url),"lxml")
    h1=s.find("h1")
    title=norm(h1.get_text(" ",strip=True)) if h1 else None
    img=_property_image_from_soup(s,url)
    main=s.find("main") or s.find("article")
    text=norm(main.get_text(" ",strip=True)) if main else norm(s.get_text(" ",strip=True))
    return title,img,text


def refresh_ahl():
    url="https://auctionhouselondon.co.uk/commercial-property-for-sale"
    s=BeautifulSoup(fetch(url),"lxml")
    candidates=[];seen=set()

    for a in s.find_all("a",href=True):
        href=urljoin(url,a["href"])
        if "/lot/" not in href or href in seen:
            continue
        card=""
        node=a
        for _ in range(8):
            node=getattr(node,"parent",None)
            if node is None:
                break
            txt=norm(node.get_text(" ",strip=True))
            if 40<len(txt)<2600:
                card=txt
        m=re.search(r"\bLOT\s+(\d+[A-Z]?)\b",card,re.I)
        if not m or "sold prior" in card.lower() or "withdrawn" in card.lower():
            continue
        # Dedicated commercial page; lot page is still used as the source of truth.
        seen.add(href)
        candidates.append((href,f"Lot {m.group(1)}",card))

    rows=[]
    def build(c):
        href,lotno,card=c
        try:
            title,img,text=_exact_preview(href)
            combined=card+" "+text
            guide=None
            gm=re.search(r"Guide Price(?:\\s*[:*])?\\s*(£[\\d,]+)",combined,re.I)
            if gm:
                guide=parse_money(gm.group(1))
            rent=parse_rent(combined)
            return dict(
                source="Auction House London",lot=lotno,date="2026-09-02",
                address=title or norm(card)[:180],guide=guide,rent=rent,
                tenure=("Freehold" if "freehold" in combined.lower() else
                        "Leasehold" if "leasehold" in combined.lower() else None),
                vat="UNKNOWN",url=href,desc=card[:300],image=img
            )
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures=[ex.submit(build,c) for c in candidates]
        for f in as_completed(futures):
            row=f.result()
            if row:
                rows.append(row)

    if len(rows)<5:
        raise ValueError("Auction House London sanity check failed")
    return rows

def refresh_savills():
    url="https://auctions.savills.co.uk/auctions/2-september-2026-241/page-1/quantity-100/property_type-253/sort-by-0"
    s=BeautifulSoup(fetch(url),"lxml")
    rows_by_lot={}

    generic={"full details","view details","details","previous lot","next lot","return to catalogue"}

    for a in s.find_all("a",href=True):
        addr=norm(a.get_text(" ",strip=True))
        if not addr or addr.lower() in generic:
            continue
        if len(addr)<8:
            continue

        href=urljoin(url,a["href"])
        # Ignore links which are clearly not a property detail destination.
        if "2-september-2026-241" not in href and "option=com_bidding" not in href:
            continue

        # Walk backwards only to the current lot marker.
        before=[]
        for t in a.find_all_previous(string=True,limit=50):
            tt=norm(str(t))
            if tt:
                before.append(tt)
        before.reverse()

        idx=None; lotno=None
        for i in range(len(before)-1,-1,-1):
            m=re.fullmatch(r"Lot\\s+(\\d+[A-Z]?)",before[i],re.I)
            if m:
                idx=i
                lotno="Lot "+m.group(1)
                break
        if idx is None:
            continue

        pre=" ".join(before[idx:])
        if "sold prior" in pre.lower() or "withdrawn prior" in pre.lower():
            continue

        # Read only this lot's following text, stopping at the next lot.
        after=[]
        for t in a.find_all_next(string=True,limit=70):
            tt=norm(str(t))
            if not tt:
                continue
            if after and re.fullmatch(r"Lot\\s+\\d+[A-Z]?",tt,re.I):
                break
            after.append(tt)
        card=pre+" "+" ".join(after)

        gm=re.search(r"Guide Price\\s*(£[\\d,]+)",pre,re.I)
        guide=parse_money(gm.group(1)) if gm else None
        rent=parse_rent(card)

        # Find image within the lot container first.
        img=None
        node=a
        for _ in range(8):
            node=getattr(node,"parent",None)
            if node is None:
                break
            tag=node.find("img")
            if tag:
                raw=tag.get("src") or tag.get("data-src") or tag.get("data-lazy-src")
                if raw:
                    img=urljoin(url,raw)
                    break

        row=dict(
            source="Savills Auctions",lot=lotno,date="2026-09-02",
            address=addr,guide=guide,rent=rent,tenure=None,vat="UNKNOWN",
            url=href,desc=card[:300],image=img
        )

        # One record per lot. Prefer the row with a real image and fuller address.
        existing=rows_by_lot.get(lotno)
        if existing is None:
            rows_by_lot[lotno]=row
        else:
            score=lambda r: (1 if r.get("image") else 0, len(r.get("address","")))
            if score(row)>score(existing):
                rows_by_lot[lotno]=row

    rows=list(rows_by_lot.values())
    known={x["lot"] for x in rows}
    if len(rows)<8 or "Lot 73" not in known or "Lot 86" not in known:
        raise ValueError("Savills sanity check failed")
    return rows

@st.cache_data(ttl=21600, show_spinner=False)
def _pugh_current_commercial():
    """Current 27 Aug BTG/Pugh commercial + mixed-use only."""
    url="https://www.btgeddisonspropertyauctions.com/auctions/live-stream/august-2026?auction_id=17&date_added=0&limit=0&radius=1&search_type=auction&view=grid"
    try:
        soup=BeautifulSoup(fetch(url),"lxml")
        links=[]
        for a in soup.find_all("a",href=True):
            href=urljoin(url,a["href"])
            if "/properties/" in href and href not in links:
                links.append(href)
        rows=[]
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs=[ex.submit(_exact_page_card,u,"Pugh / BTG Eddisons","2026-08-27",False) for u in links]
            for f in as_completed(futs):
                r=f.result()
                if not r:
                    continue
                low=(r.get("desc") or "").lower()
                positive=("property type commercial","property type mixed use","commercial property",
                          "commercial development","mixed use","retail property","property type hotel")
                negative=("property type house","property type flat","property type bungalow",
                          "residential development")
                if any(x in low for x in positive) and not any(x in low for x in negative):
                    rows.append(r)
        return _clean_rows(rows)
    except Exception:
        return []



def _v652_money(text):
    m=re.search(r"£\s*([\d,]+(?:\.\d+)?)",text or "")
    return float(m.group(1).replace(",","")) if m else None


def _v652_data_image(image_url, referer=None):
    if not image_url: return None
    if str(image_url).startswith("data:image/"): return image_url
    try:
        h=dict(HEADERS)
        if referer: h["Referer"]=referer
        r=requests.get(image_url,headers=h,timeout=10)
        ct=(r.headers.get("content-type") or "").split(";")[0].lower()
        if r.ok and ct.startswith("image/") and 500 < len(r.content) < 1800000:
            return f"data:{ct};base64,"+base64.b64encode(r.content).decode("ascii")
    except Exception:
        pass
    return image_url


def _v652_hero(url, source=""):
    try:
        raw=fetch(url)
        soup=BeautifulSoup(raw,"lxml")
        candidates=[]
        for sel,attr in [
            ('meta[property="og:image"]','content'),('meta[name="twitter:image"]','content'),
            ('meta[property="twitter:image"]','content')]:
            t=soup.select_one(sel)
            if t and t.get(attr): candidates.append(urljoin(url,t.get(attr)))
        for img in soup.find_all("img"):
            for attr in ("data-src","data-lazy-src","data-original","src"):
                v=img.get(attr)
                if v: candidates.append(urljoin(url,v))
            ss=img.get("srcset") or img.get("data-srcset")
            if ss:
                for part in ss.split(","):
                    v=part.strip().split(" ")[0]
                    if v: candidates.append(urljoin(url,v))
        # Strettons embeds gallery URLs in JSON/script rather than ordinary img tags.
        for m in re.findall(r'https?:\\?/\\?/[^"\'<> ]+?(?:jpg|jpeg|png|webp)(?:\?[^"\'<> ]*)?',raw,re.I):
            candidates.append(m.replace('\\/','/'))
        clean=[]
        for c in candidates:
            lc=c.lower()
            if any(x in lc for x in ("logo","favicon","avatar","staff","agent","icon","sprite","placeholder","google")):
                continue
            if c not in clean: clean.append(c)
        src=(source or "").lower()
        if "strettons" in src:
            clean.sort(key=lambda u:(0 if ("amazonaws.com/i/api_sources" in u.lower() or "_web_" in u.lower()) else 1, len(u)))
        elif "acuitus" in src:
            clean.sort(key=lambda u:(0 if any(x in u.lower() for x in ("property","upload","media","image")) else 1, len(u)))
        return clean[0] if clean else None
    except Exception:
        return None


def _v652_exact_row(url, source, date=None, fallback_text=""):
    try:
        raw=fetch(url); soup=BeautifulSoup(raw,"lxml"); text=norm(soup.get_text(" ",strip=True))
        h1=soup.find("h1")
        title=norm(h1.get_text(" ",strip=True)) if h1 else ""
        if source=="Pattinson":
            tt=norm(soup.title.get_text(" ",strip=True)) if soup.title else ""
            if " | Auction Property" in tt: title=tt.split(" | Auction Property",1)[0]
            if not re.search(r"Starting\s+bid|Auction Property|online auction",text,re.I): return None
        if source=="Clive Emson" and not re.search(r"LOT\s*\d+|AVAILABLE AT|GUIDE PRICE|auction",text,re.I): return None
        if not title: title=fallback_text[:180] or "Property"
        gm=re.search(r"(?:Starting\s+bid|Guide(?:\s+Price)?\*?|AVAILABLE AT)\s*£?\s*([\d,]+)",text,re.I)
        guide=float(gm.group(1).replace(",","")) if gm else _v652_money(fallback_text)
        rm=re.search(r"(?:Rent|producing|rental income|let at|at a rent of)\s*£?\s*([\d,]+)\s*(?:p\.?a\.?|per annum|pa)",text,re.I)
        rent=float(rm.group(1).replace(",","")) if rm else None
        tenure="Freehold" if re.search(r"\bFreehold\b",text,re.I) else "Leasehold" if re.search(r"\bLeasehold\b",text,re.I) else None
        lm=re.search(r"\bLot\s*(\d+[A-Z]?)\b",text,re.I)
        lot=("Lot "+lm.group(1).upper()) if lm else ("Online auction" if source=="Pattinson" else "Lot TBC")
        img=_v652_hero(url,source)
        if img and source in ("Strettons","Acuitus"):
            img=_v652_data_image(img,url)
        return dict(source=source,lot=lot,date=date,address=title,guide=guide,rent=rent,tenure=tenure,vat="UNKNOWN",url=url,desc=text[:900],image=img)
    except Exception:
        return None


def _pattinson_current():
    base="https://www.pattinson.co.uk/commercial/property-search?searchType=CommercialSale"
    links=[]
    for page in range(1,7):
        try:
            u=base+(f"&page={page}" if page>1 else "")
            soup=BeautifulSoup(fetch(u),"lxml")
            before=len(links)
            for a in soup.find_all("a",href=True):
                href=urljoin(u,a["href"])
                if re.search(r"pattinson\.co\.uk/property/\d+",href) and href not in links:
                    node=a
                    for _ in range(4):
                        if node.parent: node=node.parent
                    card=norm(node.get_text(" ",strip=True))
                    if re.search(r"Starting\s+Bid|Current\s+Bid",card,re.I): links.append(href)
            if page>1 and len(links)==before: break
        except Exception:
            continue
    rows=[]
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs=[ex.submit(_v652_exact_row,u,"Pattinson",None,"") for u in links[:120]]
        for f in as_completed(futs):
            r=f.result()
            if r: rows.append(r)
    return _clean_rows(rows)


def _clive_emson_current():
    url="https://www.cliveemson.co.uk/properties/commerical-property-auctions"
    try:
        soup=BeautifulSoup(fetch(url),"lxml"); links=[]
        for a in soup.find_all("a",href=True):
            href=urljoin(url,a["href"])
            node=a
            for _ in range(5):
                if node.parent: node=node.parent
            card=norm(node.get_text(" ",strip=True))
            if re.search(r"\bLOT\s*\d+\b",card,re.I) and "cliveemson.co.uk" in href and href not in links:
                if href.rstrip('/') not in (url.rstrip('/'),"https://www.cliveemson.co.uk/properties"):
                    links.append(href)
        rows=[]
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs=[ex.submit(_v652_exact_row,u,"Clive Emson",None,"") for u in links[:40]]
            for f in as_completed(futs):
                r=f.result()
                if r: rows.append(r)
        return _clean_rows(rows)
    except Exception:
        return []


def _strettons_current():
    url="https://www.strettons.co.uk/auction-commercial-property/for-sale/"
    try:
        soup=BeautifulSoup(fetch(url),"lxml"); links=[]
        for a in soup.find_all("a",href=True):
            href=urljoin(url,a["href"])
            if "/auction-commercial-property-for-sale/" in href and href not in links: links.append(href)
        rows=[]
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs=[ex.submit(_v652_exact_row,u,"Strettons","2026-09-10","") for u in links[:40]]
            for f in as_completed(futs):
                r=f.result()
                if r: rows.append(r)
        return _clean_rows(rows)
    except Exception:
        return []


def _acuitus_current():
    url="https://www.acuitus.co.uk/find-a-property/?clear=y"
    try:
        soup=BeautifulSoup(fetch(url),"lxml"); links=[]
        for a in soup.find_all("a",href=True):
            href=urljoin(url,a["href"])
            if re.search(r"acuitus\.co\.uk/property/\d+/?",href) and href not in links: links.append(href)
        rows=[]
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs=[ex.submit(_v652_exact_row,u,"Acuitus","2026-09-17","") for u in links[:20]]
            for f in as_completed(futs):
                r=f.result()
                if r: rows.append(r)
        return _clean_rows(rows)
    except Exception:
        return []


@st.cache_data(ttl=21600,show_spinner=False)
def _v652_repair_priority_images(rows_tuple):
    rows=[dict(x) for x in rows_tuple]
    targets=[i for i,r in enumerate(rows) if r.get("source") in ("Strettons","Acuitus")]
    def one(i):
        r=rows[i]; img=r.get("image")
        if not img or not str(img).startswith("data:image/"):
            if not img: img=_v652_hero(r.get("url") or "",r.get("source") or "")
            if img: img=_v652_data_image(img,r.get("url"))
        return i,img
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs=[ex.submit(one,i) for i in targets]
        for f in as_completed(futs):
            i,img=f.result()
            if img: rows[i]["image"]=img
    return rows


# V6.54 source-specific collectors override the broader V6.52 versions.
def _v652_hero(url, source=""):
    if not url:
        return None
    try:
        raw=fetch(url)
        soup=BeautifulSoup(raw,"lxml")
        src=(source or "").lower()
        candidates=[]

        def add(v):
            if not v: return
            v=html.unescape(str(v)).replace('\\/','/')
            v=urljoin(url,v)
            if v not in candidates: candidates.append(v)

        # Source-specific high confidence first.
        if "clive emson" in src:
            for img in soup.find_all("img"):
                alt=norm(img.get("alt") or "")
                if re.search(r"\bLot\s*:\s*\d+|External image|Internal image",alt,re.I):
                    for a in ("data-src","data-lazy-src","data-original","src"):
                        add(img.get(a))
                    ss=img.get("srcset") or img.get("data-srcset")
                    if ss:
                        for part in ss.split(','): add(part.strip().split(' ')[0])
        elif "acuitus" in src:
            h1=norm(soup.find('h1').get_text(' ',strip=True)) if soup.find('h1') else ''
            for img in soup.find_all('img'):
                alt=norm(img.get('alt') or '')
                if h1 and (alt.lower() in h1.lower() or h1.lower() in alt.lower()):
                    for a in ("data-src","data-lazy-src","data-original","src"): add(img.get(a))
                elif re.search(r"property|auction|building|street|road|house|park",alt,re.I):
                    for a in ("data-src","data-lazy-src","data-original","src"): add(img.get(a))
        elif "strettons" in src:
            decoded=html.unescape(raw).replace('\\/','/')
            for m in re.findall(r'https?://[^"\'<>\s]+?\.(?:jpe?g|png|webp)(?:\?[^"\'<>\s]*)?',decoded,re.I):
                add(m)

        # Standard metadata / lazy images.
        for sel,attr in [('meta[property="og:image"]','content'),('meta[name="twitter:image"]','content'),('meta[property="twitter:image"]','content')]:
            t=soup.select_one(sel)
            if t: add(t.get(attr))
        for img in soup.find_all('img'):
            for a in ("data-src","data-lazy-src","data-original","data-image","src"): add(img.get(a))
            ss=img.get('srcset') or img.get('data-srcset')
            if ss:
                for part in ss.split(','): add(part.strip().split(' ')[0])
        for tag in soup.find_all(style=True):
            for m in re.findall(r'url\(["\']?([^"\')]+)',tag.get('style') or '',re.I): add(m)

        filtered=[]
        for c in candidates:
            lc=c.lower()
            if not re.search(r'\.(?:jpe?g|png|webp)(?:\?|$)',lc):
                continue
            if any(x in lc for x in ('logo','favicon','avatar','staff','agent','icon','sprite','placeholder','no-image','noimage','sorry','award','ombudsman','rics','zoopla','onthemarket','social')):
                continue
            if c not in filtered: filtered.append(c)

        if "strettons" in src:
            filtered.sort(key=lambda u:(0 if 'amazonaws.com/i/api_sources/' in u.lower() else 1,0 if '_web_' in u.lower() else 1,len(u)))
        elif "acuitus" in src:
            filtered.sort(key=lambda u:(0 if '/uploads/' in u.lower() or '/images/' in u.lower() else 1,len(u)))
        elif "clive emson" in src:
            filtered.sort(key=lambda u:(0 if any(x in u.lower() for x in ('property','lot','gallery')) else 1,len(u)))
        return filtered[0] if filtered else None
    except Exception:
        return None


def _v654_data_image(image_url, referer=None):
    if not image_url: return None
    if str(image_url).startswith('data:image/'): return image_url
    try:
        h=dict(HEADERS)
        h['Accept']='image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'
        if referer: h['Referer']=referer
        r=requests.get(image_url,headers=h,timeout=12,allow_redirects=True)
        ct=(r.headers.get('content-type') or '').split(';')[0].lower()
        if r.ok and ct.startswith('image/') and 800 < len(r.content) < 2500000:
            return f'data:{ct};base64,'+base64.b64encode(r.content).decode('ascii')
    except Exception:
        pass
    return None


def _v654_exact_row(url, source, date=None):
    try:
        raw=fetch(url); soup=BeautifulSoup(raw,'lxml'); text=norm(soup.get_text(' ',strip=True))
        lot='Lot TBC'; address=''; guide=None; rent=None; tenure=None
        if source=='Clive Emson':
            if not re.search(r'/properties/\d+/\d+/?$',url): return None
            h1=norm(soup.find('h1').get_text(' ',strip=True)) if soup.find('h1') else ''
            lm=re.search(r'\bLot\s*(\d+[A-Z]?)\b',h1,re.I)
            if not lm: return None
            lot='Lot '+lm.group(1).upper()
            for h in soup.find_all(['h2','h3']):
                t=norm(h.get_text(' ',strip=True))
                if re.search(r'\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b',t,re.I):
                    address=t; break
            if not address:
                address=re.sub(r'^Lot\s*\d+\s*','',h1,flags=re.I).strip()
        elif source=='Acuitus':
            h1=soup.find('h1'); address=norm(h1.get_text(' ',strip=True)) if h1 else ''
            lm=re.search(r'\bLot\s*(\d+[A-Z]?)\b',text,re.I)
            if lm: lot='Lot '+lm.group(1).upper()
        elif source=='Strettons':
            h1=soup.find('h1'); address=norm(h1.get_text(' ',strip=True)) if h1 else ''
            lm=re.search(r'\bLot\s*(\d+[A-Z]?)\b',text,re.I)
            if lm: lot='Lot '+lm.group(1).upper()
        else:
            h1=soup.find('h1'); address=norm(h1.get_text(' ',strip=True)) if h1 else ''

        gm=re.search(r'(?:Guide(?:\s+Price)?\*?|AVAILABLE AT)\s*£?\s*([\d,]+)',text,re.I)
        if gm: guide=float(gm.group(1).replace(',',''))
        rm=re.search(r'(?:Currently\s+let\s+at|Rent|producing|rental income|let at|at a rent of)\s*£?\s*([\d,]+)\s*(?:p\.?a\.?|per annum|pa)',text,re.I)
        if rm: rent=float(rm.group(1).replace(',',''))
        tenure='Freehold' if re.search(r'\bFreehold\b',text,re.I) else 'Leasehold' if re.search(r'\bLeasehold\b',text,re.I) else None
        img=_v652_hero(url,source)
        if img:
            proxied=_v654_data_image(img,url)
            if proxied: img=proxied
        return dict(source=source,lot=lot,date=date,address=address or 'Property',guide=guide,rent=rent,tenure=tenure,vat='UNKNOWN',url=url,desc=text[:1000],image=img)
    except Exception:
        return None


def _clive_emson_current():
    listing='https://www.cliveemson.co.uk/properties/commerical-property-auctions'
    try:
        soup=BeautifulSoup(fetch(listing),'lxml')
        links=[]
        for a in soup.find_all('a',href=True):
            href=urljoin(listing,a['href']).split('#')[0]
            if re.search(r'https?://(?:www\.)?cliveemson\.co\.uk/properties/\d+/\d+/?$',href,re.I) and href not in links:
                links.append(href)
        rows=[]
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs=[ex.submit(_v654_exact_row,u,'Clive Emson',None) for u in links[:80]]
            for f in as_completed(futs):
                r=f.result()
                if r: rows.append(r)
        return _clean_rows(rows)
    except Exception:
        return []


def _strettons_current():
    listing='https://www.strettons.co.uk/auction-commercial-property/for-sale/'
    try:
        soup=BeautifulSoup(fetch(listing),'lxml'); links=[]
        for a in soup.find_all('a',href=True):
            href=urljoin(listing,a['href']).split('#')[0]
            if '/auction-commercial-property-for-sale/' in href and href not in links: links.append(href)
        rows=[]
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs=[ex.submit(_v654_exact_row,u,'Strettons','2026-09-10') for u in links[:50]]
            for f in as_completed(futs):
                r=f.result()
                if r: rows.append(r)
        return _clean_rows(rows)
    except Exception:
        return []


@st.cache_data(ttl=21600, show_spinner=False)
def _acuitus_current():
    """Current Acuitus catalogue enriched from each exact property page.

    Acuitus publishes materially richer particulars on the detail page than on
    the search card: rent, VAT, EPC bands and tenancy/accommodation tables. We
    parse those exact pages and keep their structured facts rather than reducing
    them to the thin catalogue card.
    """
    listing="https://www.acuitus.co.uk/find-a-property/?clear=y"

    def num(v):
        try:return float(re.sub(r"[^0-9.]","",str(v)))
        except Exception:return None

    def exact_row(href,card=""):
        try:
            raw=fetch(href)
            ds=BeautifulSoup(raw,"lxml")
            main=ds.find("main") or ds
            text=norm(main.get_text(" ",strip=True))
            h=ds.find("h1")
            address=norm(h.get_text(" ",strip=True)) if h else ""
            if not address:return None

            lm=re.search(r"\bLot\s*(\d+[A-Z]?)\b",text,re.I)
            lot="Lot "+lm.group(1).upper() if lm else "Lot TBC"
            gm=re.search(r"\bGuide\*?\s*£\s*([\d,]+(?:\.\d+)?)",text,re.I)
            guide=float(gm.group(1).replace(',','')) if gm else None
            rm=re.search(r"\bRent\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:per\s+annum|p\.?a\.?|pa)\b",text,re.I)
            rent=float(rm.group(1).replace(',','')) if rm else None

            tenure=("Freehold" if re.search(r"\bFreehold\b",text,re.I)
                    else "Leasehold" if re.search(r"\bLeasehold\b",text,re.I) else None)
            vat=("NOT APPLICABLE" if re.search(r"VAT\s+(?:is\s+)?not\s+(?:applicable|payable)",text,re.I)
                 else "APPLICABLE" if re.search(r"VAT\s+(?:is\s+)?applicable|VAT\s+is\s+payable",text,re.I)
                 else "UNKNOWN")

            epc=None
            epc_section=re.search(r"\bEPC\b(.{0,180})",text,re.I)
            if epc_section:
                part=epc_section.group(1)
                bands=[]
                bm=re.search(r"Band\s+([A-G](?:\s*(?:,|and|&)\s*[A-G])+)",part,re.I)
                if bm:
                    bands=re.findall(r"[A-G]",bm.group(1).upper())
                if not bands:
                    bands=re.findall(r"\b([A-G])\b",part[:100].upper())
                bands=list(dict.fromkeys(bands))
                if bands:epc=" / ".join(bands)

            total_sqm=None;total_sqft=None;accommodation=[]
            for table in ds.find_all("table"):
                rows=[]
                for tr in table.find_all("tr"):
                    cells=[norm(c.get_text(" ",strip=True)) for c in tr.find_all(["th","td"])]
                    if cells:rows.append(cells)
                if not rows:continue
                header=" | ".join(rows[0]).lower()
                looks_accom=("floor" in header and ("sq m" in header or "sqm" in header or "sq ft" in header or "sqft" in header))
                if not looks_accom and "accommodation" not in norm(table.get_text(" ",strip=True)).lower():
                    continue
                sqm_idx=next((i for i,x in enumerate(rows[0]) if re.search(r"sq\s*m|sqm",x,re.I)),None)
                sqft_idx=next((i for i,x in enumerate(rows[0]) if re.search(r"sq\s*ft|sqft",x,re.I)),None)
                for cells in rows[1:]:
                    label=" / ".join(cells[:2]).strip(" /")
                    is_total=bool(cells and re.search(r"\btotal\b",cells[0],re.I))
                    sqm=num(cells[sqm_idx]) if sqm_idx is not None and sqm_idx<len(cells) else None
                    sqft=num(cells[sqft_idx]) if sqft_idx is not None and sqft_idx<len(cells) else None
                    if is_total:
                        if sqm:total_sqm=sqm
                        if sqft:total_sqft=sqft
                    elif label and (sqm or sqft):
                        bits=[label]
                        if sqm:bits.append(f"{sqm:,.2f} sq m")
                        if sqft:bits.append(f"{sqft:,.0f} sq ft")
                        accommodation.append(" · ".join(bits))
                if total_sqm or total_sqft or accommodation:
                    break

            if not total_sqm:
                tm=re.search(r"\bTotal\b[^0-9]{0,40}([\d,.]+)\s*(?:sq\.?\s*m|sqm|m²)",text,re.I)
                if tm:total_sqm=float(tm.group(1).replace(',',''))
            if not total_sqft:
                tf=re.search(r"\bTotal\b.{0,90}?([\d,]+)\s*(?:sq\.?\s*ft|sqft|ft²)",text,re.I)
                if tf:total_sqft=float(tf.group(1).replace(',',''))
            if total_sqm and not total_sqft:total_sqft=round(total_sqm*10.7639)
            if total_sqft and not total_sqm:total_sqm=round(total_sqft/10.7639,2)

            facts=extract_particulars(raw,"Acuitus",href)
            row=dict(source="Acuitus",lot=lot,date="2026-09-17",address=address,
                     guide=guide,rent=rent,tenure=tenure,vat=vat,url=href,
                     desc=text[:3500],image=_property_image_from_soup(ds,href),
                     epc=epc,area_sqm=total_sqm,area_sqft=total_sqft,
                     accommodation_summary=" | ".join(accommodation[:8]) or None)
            row=merge_enrichment(row,facts)
            if epc:row["epc"]=epc
            if total_sqm:row["area_sqm"]=total_sqm
            if total_sqft:row["area_sqft"]=total_sqft
            if accommodation:row["accommodation_summary"]=" | ".join(accommodation[:8])
            if guide is not None:row["guide"]=guide
            if rent is not None:row["rent"]=rent
            if tenure:row["tenure"]=tenure
            if vat!="UNKNOWN":row["vat"]=vat
            return row
        except Exception:
            return None

    try:
        soup=BeautifulSoup(fetch(listing),"lxml")
        links=[];cards={}
        for a in soup.find_all("a",href=True):
            href=urljoin(listing,a["href"]).split('#')[0]
            if not re.search(r"https?://(?:www\.)?acuitus\.co\.uk/property/\d+/?$",href,re.I):continue
            if href not in links:links.append(href)
            node=a;card=""
            for _ in range(7):
                node=getattr(node,"parent",None)
                if node is None:break
                t=norm(node.get_text(" ",strip=True))
                if len(t)<5000 and ("Guide" in t or "17/09/2026" in t):card=t
            cards[href]=card
        rows=[]
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures={ex.submit(exact_row,u,cards.get(u,"")):u for u in links[:80]}
            for f in as_completed(futures):
                r=f.result()
                if r:rows.append(r)
        return _clean_rows(rows)
    except Exception:
        return []


# V6.57: serve troublesome auction-house photos from Auction Sniper itself.
# Direct hotlinks and data: URIs have both proved unreliable in Streamlit Cloud.
STATIC_IMAGE_DIR=Path('static/property_images')
STATIC_IMAGE_DIR.mkdir(parents=True,exist_ok=True)


def _v657_candidate_images(property_url, source):
    if not property_url:
        return []
    try:
        raw=fetch(property_url)
    except Exception:
        return []
    soup=BeautifulSoup(raw,'lxml')
    out=[]
    def add(v):
        if not v: return
        v=html.unescape(str(v)).replace('\\/','/').strip(' "\'')
        if v.startswith('//'): v='https:'+v
        v=urljoin(property_url,v)
        if v not in out: out.append(v)

    # Clive Emson uses predictable /AucNNN/pics/... image URLs on genuine lot pages.
    if (source or '').lower()=='clive emson':
        decoded=html.unescape(raw).replace('\\/','/')
        exact=[]
        for tag in soup.find_all(['img','a']):
            for attr in ('src','data-src','data-lazy-src','data-original','href'):
                v=tag.get(attr)
                if not v: continue
                vv=html.unescape(str(v)).replace('\\/','/')
                if re.search(r'/Auc\d+/pics/.+?\.(?:jpe?g|png|webp)(?:\?.*)?$',vv,re.I):
                    exact.append(urljoin(property_url,vv))
        for m in re.findall(r'["\']([^"\']*/Auc\d+/pics/[^"\']+?\.(?:jpe?g|png|webp)(?:\?[^"\']*)?)["\']',decoded,re.I):
            exact.append(urljoin(property_url,m))
        for v in exact:
            if v not in out: out.append(v)

    # Structured metadata first.
    for sel,attr in [
        ('meta[property="og:image"]','content'),
        ('meta[name="twitter:image"]','content'),
        ('meta[itemprop="image"]','content'),
        ('link[rel="image_src"]','href'),
    ]:
        for tag in soup.select(sel): add(tag.get(attr))

    # Normal/lazy image elements and srcsets.
    for img in soup.find_all('img'):
        for a in ('data-src','data-lazy-src','data-original','data-image','data-large','data-full','src'):
            add(img.get(a))
        for a in ('srcset','data-srcset'):
            ss=img.get(a)
            if ss:
                parts=[x.strip().split(' ')[0] for x in ss.split(',') if x.strip()]
                for u in reversed(parts): add(u)

    # CSS and script/JSON galleries (important for Strettons and Clive Emson).
    decoded=html.unescape(raw).replace('\\/','/')
    for m in re.findall(r'(?:https?:)?//[^"\'<>\\s]+?\.(?:jpe?g|png|webp)(?:\?[^"\'<>\\s]*)?',decoded,re.I): add(m)
    for m in re.findall(r'["\']([^"\']+?\.(?:jpe?g|png|webp)(?:\?[^"\']*)?)["\']',decoded,re.I): add(m)
    for tag in soup.find_all(style=True):
        for m in re.findall(r'url\(["\']?([^"\')]+)',tag.get('style') or '',re.I): add(m)

    bad=('logo','favicon','avatar','staff','agent','icon','sprite','placeholder','no-image','noimage','sorry','award','ombudsman','rics','zoopla','onthemarket','social','spinner','loading','cookie')
    clean=[]
    for u in out:
        lu=u.lower()
        if not re.search(r'\.(?:jpe?g|png|webp)(?:\?|$)',lu): continue
        if any(x in lu for x in bad): continue
        if u not in clean: clean.append(u)

    src=(source or '').lower()
    def score(u):
        lu=u.lower(); sc=0
        if 'strettons' in src:
            if 'amazonaws.com/i/api_sources/' in lu: sc+=100
            if '_web_' in lu: sc+=70
            if 'property' in lu or 'auction' in lu: sc+=25
        elif 'acuitus' in src:
            if '/uploads/' in lu: sc+=100
            if re.search(r'/\d+-\d+/',lu): sc+=60
            if 'banner' in lu or 'property' in lu: sc+=30
        elif 'clive emson' in src:
            if re.search(r'/auc\d+/pics/',lu): sc+=500
            if 'property' in lu or 'properties' in lu: sc+=70
            if 'lot' in lu: sc+=55
            if any(x in lu for x in ('gallery','photo','image')): sc+=30
        # Prefer sizeable originals over tiny thumbnails when filename gives hints.
        if any(x in lu for x in ('160x','100x','thumb','thumbnail')): sc-=20
        return (-sc,len(u))
    clean.sort(key=score)
    return clean


def _v657_local_image(source, property_url, image_url=None):
    if source not in ('Strettons','Acuitus','Clive Emson'):
        return image_url
    candidates=[]
    if image_url and not str(image_url).startswith('data:'):
        candidates.append(str(image_url))
    for u in _v657_candidate_images(property_url,source):
        if u not in candidates: candidates.append(u)
    for u in candidates[:18]:
        try:
            h={
                'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0 Safari/537.36',
                'Accept':'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
                'Accept-Language':'en-GB,en;q=0.9',
                'Referer':property_url or '',
            }
            r=requests.get(u,headers=h,timeout=15,allow_redirects=True)
            ct=(r.headers.get('content-type') or '').split(';')[0].lower()
            if not r.ok or not ct.startswith('image/') or len(r.content)<2500 or len(r.content)>5000000:
                continue
            # Reject known placeholder artwork by URL and suspiciously tiny dimensions where Pillow is unavailable.
            lu=(r.url or u).lower()
            if any(x in lu for x in ('placeholder','no-image','noimage','sorry')): continue
            ext={
                'image/jpeg':'.jpg','image/jpg':'.jpg','image/png':'.png','image/webp':'.webp','image/gif':'.gif'
            }.get(ct,'.jpg')
            key=hashlib.sha1((source+'|'+property_url+'|'+u).encode('utf-8')).hexdigest()[:20]
            path=STATIC_IMAGE_DIR/(key+ext)
            if not path.exists(): path.write_bytes(r.content)
            return 'app/static/property_images/'+path.name
        except Exception:
            continue
    if source=='Clive Emson':
        exact=_v657_candidate_images(property_url,source)
        for u in exact:
            if re.search(r'/Auc\d+/pics/',u,re.I):
                return u
    return None


def _v657_localise_priority_rows(rows):
    targets=[(i,r) for i,r in enumerate(rows) if r.get('source') in ('Strettons','Acuitus','Clive Emson')]
    def one(i,r):
        return i,_v657_local_image(r.get('source'),r.get('url') or '',r.get('image'))
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs=[ex.submit(one,i,r) for i,r in targets]
        for f in as_completed(futs):
            try:
                i,src=f.result()
                if src: rows[i]['image']=src
            except Exception:
                pass
    return rows

def refresh_market():
    # Begin with the full current board, not the smaller seed.
    current_rows,old_health,_updated=load_rows()
    current_by_source={}
    for p in current_rows:
        current_by_source.setdefault(p["source"],[]).append(dict(p))
    health=[dict(h) for h in SOURCE_HEALTH]

    jobs={
        "Auction House London": refresh_ahl,
        "Savills Auctions": refresh_savills,
        "Barnard Marcus": _catalogue_barnard_marcus,
        "Auction House Regional": _catalogue_auctionhouse_regional,
        "Bond Wolfe": _bond_wolfe_current,
        "Strettons": _strettons_current,
        "Acuitus": _acuitus_current,
        "Pattinson": _pattinson_current,
        "Clive Emson": _clive_emson_current,
        "Pugh / BTG Eddisons": _pugh_current_commercial,
    }
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures={ex.submit(fn):src for src,fn in jobs.items()}
        for f in as_completed(futures):
            src=futures[f]
            try:
                rows=f.result() or []
                rows=_clean_rows(rows)
                if not rows:
                    continue
                if src=="Auction House Regional":
                    # FIX: merge EVERY returned regional row, not only the final loop item.
                    grouped={}
                    for r in rows:
                        grouped.setdefault(r["source"],[]).append(r)
                    for branch,newrows in grouped.items():
                        by_key={_canonical_key(x):dict(x) for x in current_by_source.get(branch,[])}
                        for r in newrows:
                            k=_canonical_key(r)
                            by_key[k]=_merge_property_rows(by_key.get(k),r,seed_authoritative=False) if k in by_key else dict(r)
                        current_by_source[branch]=list(by_key.values())
                else:
                    by_key={_canonical_key(x):dict(x) for x in current_by_source.get(src,[])}
                    for r in rows:
                        k=_canonical_key(r)
                        by_key[k]=_merge_property_rows(by_key.get(k),r,seed_authoritative=False) if k in by_key else dict(r)
                    current_by_source[src]=list(by_key.values())
            except Exception:
                pass

    refreshed=[]
    for source_rows in current_by_source.values():
        refreshed.extend(source_rows)
    refreshed=_clean_rows(refreshed)

    # Exact property-page photo enrichment for ALL missing non-Savills cards,
    # including AHL, Bond Wolfe, Barnard Marcus and cached BTG/Pugh rows.
    refreshed=_enrich_missing_images(refreshed,limit=220)
    refreshed=_deep_enrich_rows(refreshed,limit=70)

    # Non-shrink guard after residential cleanup: only compare allowed current rows.
    allowed_current=_clean_rows(current_rows)
    if len(refreshed) < len(allowed_current):
        refreshed=_merge_property_universe(allowed_current,refreshed)

    payload={"updated":time.strftime("%Y-%m-%d %H:%M"),"properties":refreshed,"health":health}
    CACHE.write_text(json.dumps(payload,indent=2),encoding="utf-8")
    return payload



# ---------------- DEEP EVIDENCE / SEMANTIC NORMALISATION ----------------
def _money_mentions(text):
    out=[]
    for m in re.finditer(r"£\s*([\d,]+(?:\.\d+)?)",text or "",re.I):
        try:
            v=float(m.group(1).replace(',',''))
            if 250 <= v <= 10_000_000:
                out.append((v,m.start(),m.end()))
        except Exception:
            pass
    return out


def _classify_rental_evidence(text):
    """Separate current passing rent from historic rent, ERV and asking/proposed rents."""
    text=norm(text or '')
    evidence={"current":[],"historical":[],"erv":[],"other":[]}
    hist_words=r"previous(?:ly)?|former(?:ly)?|historic(?:al|ally)?|last\s+let|was\s+let|had\s+been\s+let|prior\s+rent"
    erv_words=r"\bERV\b|estimated\s+rental\s+value|market\s+rent|asking\s+rent|quoting\s+rent|proposed\s+rent|regear\s+rent|new\s+rent|rising\s+to|reviewed\s+to"
    current_words=r"passing\s+rent|currently\s+let|fully\s+let|let\s+to|producing|rental\s+income|current\s+rent|income\s+of|rent\s+receivable|annual\s+rent"
    for value,start,end in _money_mentions(text):
        left=max(0,start-150); right=min(len(text),end+150)
        ctx=text[left:right]
        if re.search(hist_words,ctx,re.I): kind='historical'
        elif re.search(erv_words,ctx,re.I): kind='erv'
        elif re.search(current_words,ctx,re.I) and not re.search(r"under\s+offer|subject\s+to\s+contract",ctx,re.I): kind='current'
        else: kind='other'
        evidence[kind].append({"value":value,"context":ctx[:300]})
    return evidence


def _normalise_rent_semantics(row):
    r=dict(row)
    text=norm(' '.join(str(r.get(k) or '') for k in ('desc','legal_text','summary','notes')))
    ev=_classify_rental_evidence(text)
    old=r.get('rent')
    current_vals=[x['value'] for x in ev['current']]
    hist_vals=[x['value'] for x in ev['historical']]
    erv_vals=[x['value'] for x in ev['erv']]
    if current_vals:
        current=min(current_vals,key=lambda v:abs(v-float(old))) if old else max(current_vals)
        r['rent']=current
        r['rent_status']='CURRENT / PASSING'
        r['rent_evidence']=next((x['context'] for x in ev['current'] if x['value']==current),'')
    else:
        old_is_historic=bool(old and any(abs(x['value']-float(old)) < 1 for x in ev['historical']))
        old_is_erv=bool(old and any(abs(x['value']-float(old)) < 1 for x in ev['erv']))
        vacancy=bool(re.search(r"vacant(?:\s+possession)?|currently\s+vacant|former\s+tenant|lease\s+expired",text,re.I))
        if old_is_historic or old_is_erv or (vacancy and not re.search(r"part(?:ly)?\s+let|income\s+producing",text,re.I)):
            r['rent']=None
            r['rent_status']='NO CONFIRMED CURRENT RENT'
            r['rent_evidence']='Historical/ERV evidence was found, but no explicit current passing rent was confirmed.'
        elif old:
            r['rent_status']='COLLECTOR VALUE — VERIFY'
            r['rent_evidence']='Collector supplied a rent figure, but the captured text does not yet positively identify it as current passing rent.'
    if hist_vals:
        r['previous_rent']=hist_vals[0]
        r['previous_rent_evidence']=ev['historical'][0]['context']
    if erv_vals:
        r['erv']=erv_vals[0]
        r['erv_evidence']=ev['erv'][0]['context']
    r['yield']=100*float(r['rent'])/float(r['guide']) if r.get('guide') and r.get('rent') else None
    return r


def _legal_links(page_url,soup):
    scored=[]
    for a in soup.find_all('a',href=True):
        href=urljoin(page_url,a.get('href')).split('#')[0]
        label=norm(a.get_text(' ',strip=True)+' '+href).lower()
        score=0
        if 'legal pack' in label: score+=10
        if 'special condition' in label: score+=8
        if re.search(r'\blease\b|tenancy|occupational lease',label): score+=6
        if 'epc' in label or 'energy performance' in label: score+=7
        if href.lower().split('?')[0].endswith('.pdf'): score+=4
        if score and href.startswith('http'): scored.append((score,href))
    out=[]
    for _score,u in sorted(scored,key=lambda x:-x[0]):
        if u not in out: out.append(u)
    return out[:8]


def _pdf_text(url,referer=None,max_pages=25):
    if PdfReader is None: return ''
    try:
        h=dict(HEADERS)
        if referer: h['Referer']=referer
        resp=requests.get(url,headers=h,timeout=16,allow_redirects=True)
        ct=(resp.headers.get('content-type') or '').lower()
        if not resp.ok or ('pdf' not in ct and not url.lower().split('?')[0].endswith('.pdf')) or len(resp.content)>10_000_000:
            return ''
        reader=PdfReader(BytesIO(resp.content))
        chunks=[]
        for page in reader.pages[:max_pages]:
            try:
                t=page.extract_text() or ''
                if t: chunks.append(t)
            except Exception: pass
            if sum(map(len,chunks))>30000: break
        return norm(' '.join(chunks))[:30000]
    except Exception:
        return ''


@st.cache_data(ttl=21600,show_spinner=False)
def _deep_page_evidence(url):
    if not url: return {"page_text":"","legal_text":"","legal_links":[]}
    try:
        raw=fetch(url); soup=BeautifulSoup(raw,'lxml')
        main=soup.find('main') or soup
        for tag in main.find_all(['script','style','nav','footer','header']): tag.decompose()
        page_text=norm(main.get_text(' ',strip=True))[:18000]
        links=_legal_links(url,soup)
        legal=[]
        for link in links[:3]:
            if link.lower().split('?')[0].endswith('.pdf'):
                t=_pdf_text(link,url)
                if t: legal.append(t)
        return {"page_text":page_text,"legal_text":norm(' '.join(legal))[:40000],"legal_links":links}
    except Exception:
        return {"page_text":"","legal_text":"","legal_links":[]}


def _deep_enrich_rows(rows,limit=70):
    rows=[dict(x) for x in rows]
    idx=[]
    for i,r in enumerate(rows):
        u=r.get('url') or ''
        if not u: continue
        txt=(str(r.get('desc') or '')).lower()
        score=(5 if r.get('rent') else 0)+(3 if 'legal' in txt else 0)+(2 if not r.get('epc') and not r.get('epc_rating') else 0)
        idx.append((score,i))
    idx=[i for _s,i in sorted(idx,reverse=True)[:limit]]
    def one(i):
        r=rows[i]; ev=_deep_page_evidence(r.get('url'))
        if ev.get('page_text'): r['desc']=norm((r.get('desc') or '')+' '+ev['page_text'])[:22000]
        if ev.get('legal_text'): r['legal_text']=ev['legal_text']
        if ev.get('legal_links'):
            r['legal_links']=ev['legal_links']; r['legal_pack_url']=ev['legal_links'][0]
        return i,_normalise_rent_semantics(r)
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs=[ex.submit(one,i) for i in idx]
        for f in as_completed(futs):
            try:
                i,r=f.result(); rows[i]=r
            except Exception: pass
    return [_normalise_rent_semantics(r) for r in rows]

# ---------------- UI ----------------
if "light_mode" not in st.session_state:
    st.session_state["light_mode"]=False
LIGHT_MODE=bool(st.session_state.get("light_mode",False))
st.markdown("""
<style>
header[data-testid="stHeader"],div[data-testid="stToolbar"],#MainMenu{display:none!important}
.block-container{max-width:1560px;padding:.7rem 1rem 2rem!important}
.stApp{background:radial-gradient(circle at 15% -10%,#172236 0,#0b111b 35%,#080d14 72%);color:#f5f7fb}
.hero{display:flex;justify-content:space-between;align-items:center;gap:10px;background:#101a27;border:1px solid #34465e;border-radius:10px;padding:8px 12px;margin-bottom:5px;box-shadow:0 4px 14px rgba(0,0,0,.22)}
.brand{font-size:1.62rem;font-weight:1000;letter-spacing:-.045em;line-height:1}.brand b{color:#f4cf50}.sub{font-size:.62rem;color:#b3c0d0;margin-top:3px}.tagline{font-size:.72rem;color:#eef3f8;font-weight:750;margin-top:3px}
.badge{font-size:.64rem;border:1px solid #347d58;color:#b8f1cd;background:#10261c;border-radius:999px;padding:6px 9px;white-space:nowrap;font-weight:800}
.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.card{background:linear-gradient(180deg,#131d2b,#101824);border:1px solid #273950;border-radius:11px;overflow:hidden;box-shadow:0 5px 16px rgba(0,0,0,.16);transition:transform .14s ease,border-color .14s ease,box-shadow .14s ease}
.card:hover{transform:translateY(-2px);border-color:#526a8b;box-shadow:0 10px 22px rgba(0,0,0,.23)}
.preview{display:block;width:100%;height:162px;object-fit:cover;background:linear-gradient(135deg,#192638,#111925)}
.noimg{display:grid;place-items:center;color:#73839a;font-size:.66rem;letter-spacing:.03em}
.cb{padding:10px 11px 11px}.src{font-size:.66rem;color:#f5d45e;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-transform:none;letter-spacing:.01em}
.addr{font-size:.90rem;font-weight:850;line-height:1.28;min-height:2.45em;margin:5px 0 9px;color:#ffffff}
.metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:4px}.sizeMetric{grid-column:span 2}.metric{background:#162130;border:1px solid #223047;border-radius:7px;padding:5px 7px;min-height:40px;display:flex;flex-direction:column;justify-content:center}
.metric span{display:block;color:#aebbd0;font-size:.61rem;margin-bottom:2px;line-height:1.15;font-weight:650}.metric b{font-size:.86rem;line-height:1.16;color:#fff;font-weight:850}
.meta{font-size:.68rem;color:#b0bdd0;margin-top:8px;line-height:1.35;min-height:0}
.chips{display:flex;gap:4px;flex-wrap:wrap;margin-top:7px}.chip{font-size:.66rem;font-weight:800;padding:4px 7px;border-radius:999px;background:#223047;border:1px solid #405674;color:#e7eef8}.analysis{margin-top:7px;border-top:1px solid #26354a;padding-top:6px}.research{display:flex;gap:6px;flex-wrap:wrap;margin-top:9px}.research a{text-decoration:none!important;color:#cfe0f5!important;background:#172638;border:1px solid #314761;border-radius:6px;padding:6px 8px;font-size:.62rem;font-weight:800}.research a:hover{border-color:#f2c94c;color:#f2c94c!important}.iread{margin-top:8px;background:#111d2b;border-left:3px solid #f2c94c;border-radius:6px;padding:8px 10px}.iread span{font-size:.62rem;color:#f2c94c;font-weight:900}.iread p{font-size:.68rem;color:#d8e1ed;margin:4px 0;line-height:1.35}.analysis summary{cursor:pointer;color:#dbe5f2;font-size:.72rem;font-weight:850}.factgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;margin-top:8px}.fact{background:#0f1723;border:1px solid #233149;border-radius:7px;padding:7px 8px}.fact span{display:block;color:#8fa0b5;font-size:.57rem;margin-bottom:2px}.fact b{display:block;color:#f4f7fb;font-size:.70rem;line-height:1.3}
.action{display:block;text-align:center;text-decoration:none!important;background:#f2c94c;color:#171208!important;border-radius:8px;padding:9px 8px;margin-top:9px;font-size:.77rem;font-weight:950}
.statusrow{padding:12px 14px;border:1px solid #29354b;background:#111824;border-radius:10px;margin-bottom:8px;font-size:.84rem}
div[data-testid="stExpander"]{border:1px solid #25344a!important;border-radius:11px!important;background:#0e1621!important;margin-bottom:10px}
button[data-baseweb="tab"]{font-size:.9rem!important}
@media(min-width:1700px){.block-container{max-width:1640px}.cards{grid-template-columns:repeat(5,minmax(0,1fr));gap:11px}.preview{height:160px}}
@media(max-width:1180px){.cards{grid-template-columns:repeat(3,minmax(0,1fr))}.preview{height:165px}}@media(max-width:820px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))}.preview{height:155px}.addr{font-size:.9rem}}
@media(max-width:650px){.block-container{padding:.34rem .38rem 1.15rem!important}.hero{padding:9px 10px;margin-bottom:6px}.brand{font-size:1.05rem}.sub{font-size:.56rem}.badge{font-size:.54rem;padding:4px 6px}.cards{grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}.card{display:block}.preview{height:112px;min-height:0;border-radius:0;object-fit:cover}.cb{padding:7px 7px 8px}.src{font-size:.52rem}.addr{font-size:.70rem;line-height:1.23;min-height:3.35em;margin:4px 0 6px}.metrics{gap:3px}.metric{padding:4px 5px;min-height:38px;border-radius:6px}.metric span{font-size:.44rem;margin-bottom:1px}.metric b{font-size:.62rem;line-height:1.12}.meta{font-size:.47rem;margin-top:5px;line-height:1.25}.chips{margin-top:5px;gap:3px}.chip{font-size:.47rem;padding:3px 5px}.analysis{margin-top:5px;padding-top:5px}.analysis summary{font-size:.56rem}.action{font-size:.55rem;padding:6px 4px;margin-top:6px;border-radius:6px}.factgrid{grid-template-columns:1fr}.research{gap:4px}.iread{padding:6px 7px}}
.yieldMetric{background:#14271f;border-color:#2e5a45}.yieldMetric b{color:#b9f3cf}
.previewLink{display:block;text-decoration:none!important;cursor:pointer}

/* V6.35 polished top bar */
.hero{padding:9px 13px!important;border-radius:11px!important;background:linear-gradient(115deg,#111b28 0%,#0d1621 100%)!important;border:1px solid #3a4d67!important;margin-bottom:7px!important}
.brand{font-size:1.78rem!important;letter-spacing:-.05em!important;text-shadow:0 1px 0 rgba(255,255,255,.04)}
.tagline{font-size:.70rem!important;color:#e8eef6!important;font-weight:800!important;letter-spacing:.01em}
.sub{font-size:.55rem!important;color:#8798ad!important;margin-top:2px!important}
.badge{font-size:.60rem!important;padding:5px 8px!important;border-color:#3d795b!important;background:#10251b!important}
div[data-testid="stHorizontalBlock"]:has(button[kind="primary"]){margin-top:-1px;margin-bottom:4px}
div[data-testid="stButton"]>button{border-radius:8px!important;font-weight:850!important;min-height:38px!important}
div[data-testid="stPopover"] button{border-radius:8px!important;font-weight:850!important;min-height:38px!important;border-color:#3a4b62!important;background:#131e2c!important;color:#eef4fb!important}
div[data-testid="stPopover"] button:hover{border-color:#6d87aa!important;background:#172538!important}
@media(max-width:650px){.hero{padding:8px 9px!important}.brand{font-size:1.38rem!important}.tagline{font-size:.59rem!important}.sub{font-size:.46rem!important}.badge{font-size:.50rem!important;padding:4px 6px!important}div[data-testid="stButton"]>button,div[data-testid="stPopover"] button{min-height:34px!important;font-size:.70rem!important}}

/* V6.37 target yield toolbar */
div[data-testid="stNumberInput"] label p{font-size:.67rem!important;font-weight:850!important;color:#dfe8f3!important}
div[data-testid="stNumberInput"] input{font-weight:900!important}
@media(max-width:650px){div[data-testid="stNumberInput"] label p{font-size:.56rem!important}}

.cardActions{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:9px}.cardActions .action{margin-top:0}.mapAction{display:block;text-align:center;text-decoration:none!important;background:#172638;color:#d9e7f7!important;border:1px solid #3b5470;border-radius:8px;padding:9px 7px;font-size:.70rem;font-weight:900}.mapAction:hover{border-color:#f2c94c;color:#f2c94c!important}.cardActions .action{padding:9px 7px;font-size:.70rem}@media(max-width:650px){.cardActions{gap:4px;margin-top:6px}.mapAction,.cardActions .action{font-size:.49rem;padding:6px 3px;border-radius:6px}}

/* V6.40 inline yield control */
.yieldInlineLabel{height:38px;display:flex;align-items:center;justify-content:center;padding:0 10px;border:1px solid #3a4b62;border-radius:8px;background:#131e2c;color:#eef4fb;font-size:.68rem;font-weight:850;white-space:nowrap;box-sizing:border-box}
div[data-testid="stNumberInput"]{margin:0!important}
div[data-testid="stNumberInput"]>div{margin:0!important}
@media(max-width:650px){.yieldInlineLabel{height:34px;font-size:.55rem;padding:0 6px}}

.yieldCaption{font-size:.60rem;font-weight:800;color:#aebed1;margin-top:3px;padding-left:2px;line-height:1.05;text-align:left;white-space:nowrap}
div[data-testid="stNumberInput"]{max-width:100%!important;margin:0!important}
div[data-testid="stNumberInput"]>div{margin:0!important}
div[data-testid="stNumberInput"] input{min-width:0!important}
@media(max-width:650px){.yieldCaption{font-size:.49rem;margin-top:2px;padding-left:1px}}

/* V6.44 harmonise card bottoms */
.card{display:flex!important;flex-direction:column!important;height:100%!important}
.cb{display:flex!important;flex-direction:column!important;flex:1 1 auto!important}
.analysis{margin-top:auto!important}
.cardActions{margin-top:9px!important}
@media(max-width:650px){.card{display:flex!important;flex-direction:column!important}.cb{display:flex!important;flex-direction:column!important;flex:1 1 auto!important}.analysis{margin-top:auto!important}}

/* V6.42 wider property photography */
.previewLink{display:block!important;width:100%!important;margin:0!important;padding:0!important;overflow:hidden!important}
.preview{display:block!important;width:100%!important;max-width:none!important;margin:0!important;padding:0!important;height:178px!important;object-fit:cover!important}
@media(min-width:1700px){.preview{height:176px!important}}
@media(max-width:1180px){.preview{height:174px!important}}
@media(max-width:820px){.preview{height:162px!important}}
@media(max-width:650px){.preview{height:122px!important}}

/* V6.47 product masthead + right-side yield label */
.hero{min-height:92px!important;padding:16px 20px!important;border-radius:14px!important;background:linear-gradient(105deg,#121f30 0%,#0d1724 58%,#101b29 100%)!important;border:1px solid #405673!important;box-shadow:0 10px 28px rgba(0,0,0,.24)!important;position:relative!important;overflow:hidden!important}
.hero:before{content:"";position:absolute;left:0;top:0;bottom:0;width:5px;background:#f2c94c}
.brand{font-size:2.55rem!important;font-weight:1000!important;letter-spacing:-.055em!important;line-height:.92!important;color:#f7f9fc!important;text-shadow:0 2px 12px rgba(0,0,0,.28)!important}
.brand b{color:#f2c94c!important}
.tagline{font-size:.82rem!important;margin-top:9px!important;color:#e5edf7!important;font-weight:800!important;letter-spacing:.015em!important}
.sub{font-size:.53rem!important;margin-top:5px!important;color:#7f91a8!important}
.badge{font-size:.66rem!important;padding:7px 11px!important}
.yieldCaption{display:none!important}
.yieldSideLabel{height:38px;display:flex;flex-direction:column;justify-content:center;align-items:flex-start;color:#c4d0df;font-size:.58rem;font-weight:850;line-height:1.02;letter-spacing:.01em;white-space:nowrap}
.yieldSideLabel span{font-size:.46rem;color:#8393a7;font-weight:750;margin-top:1px}
@media(max-width:650px){.hero{min-height:70px!important;padding:12px 13px 11px 16px!important}.hero:before{width:4px}.brand{font-size:1.62rem!important}.tagline{font-size:.61rem!important;margin-top:6px!important}.sub{font-size:.42rem!important}.badge{font-size:.50rem!important;padding:5px 7px!important}.yieldSideLabel{height:34px;font-size:.47rem}.yieldSideLabel span{font-size:.39rem}}

/* V6.48 integrated two-tone target-yield control */
.yieldCaption,.yieldSideLabel{display:none!important}
.yieldIntegratedLabel{height:38px;box-sizing:border-box;display:flex;flex-direction:column;justify-content:center;align-items:center;background:linear-gradient(180deg,#24354a,#1b293a);border:1px solid #52657c;border-left:0;border-radius:0 9px 9px 0;color:#dbe6f2;margin-left:-1px;padding:0 10px;line-height:1.02;box-shadow:inset 1px 0 0 rgba(255,255,255,.04)}
.yieldIntegratedLabel span{font-size:.54rem;font-weight:750;color:#9fb0c3;letter-spacing:.02em}.yieldIntegratedLabel b{font-size:.64rem;font-weight:950;color:#f2c94c;margin-top:2px;white-space:nowrap}
div[data-testid="stNumberInput"]{height:38px!important;margin:0!important}
div[data-testid="stNumberInput"]>div{height:38px!important;margin:0!important}
div[data-testid="stNumberInput"] input{height:38px!important;border-radius:9px 0 0 9px!important;font-weight:950!important}
div[data-testid="stNumberInput"] button{height:38px!important;border-radius:0!important}
@media(max-width:650px){.yieldIntegratedLabel{height:34px;padding:0 6px}.yieldIntegratedLabel span{font-size:.45rem}.yieldIntegratedLabel b{font-size:.52rem}div[data-testid="stNumberInput"],div[data-testid="stNumberInput"]>div,div[data-testid="stNumberInput"] input,div[data-testid="stNumberInput"] button{height:34px!important}}

/* V6.49 stronger title + joined left-side yield label */
.brand{font-size:3.05rem!important;line-height:.88!important;letter-spacing:-.06em!important;text-shadow:0 3px 18px rgba(0,0,0,.34)!important}
.hero{min-height:104px!important;padding:19px 23px!important}
.tagline{font-size:.88rem!important;margin-top:10px!important}
.yieldIntegratedLabel.left{border:1px solid #52657c!important;border-right:0!important;border-radius:9px 0 0 9px!important;margin-left:0!important;margin-right:-1px!important;background:linear-gradient(180deg,#263a52,#1b2a3d)!important;align-items:flex-start!important;padding-left:12px!important}
.yieldIntegratedLabel.left span{color:#b7c5d6!important}.yieldIntegratedLabel.left b{color:#f2c94c!important}
div[data-testid="stNumberInput"] input{border-radius:0!important}
div[data-testid="stNumberInput"] button:last-child{border-radius:0 9px 9px 0!important}
@media(max-width:650px){.hero{min-height:76px!important;padding:13px 14px 12px 17px!important}.brand{font-size:1.85rem!important}.tagline{font-size:.64rem!important}.yieldIntegratedLabel.left{padding-left:7px!important}}

/* V6.51 make Target Yield read as one continuous control */
.yieldIntegratedLabel.left{
  height:38px!important;
  margin:0!important;
  padding:0 10px!important;
  border:1px solid #52657c!important;
  border-right:0!important;
  border-radius:9px 0 0 9px!important;
  background:#203147!important;
  display:flex!important;
  flex-direction:column!important;
  justify-content:center!important;
  align-items:center!important;
  line-height:1!important;
  box-sizing:border-box!important;
}
.yieldIntegratedLabel.left span{font-size:.50rem!important;line-height:1!important;margin:0 0 2px!important;color:#b7c5d6!important;font-weight:800!important}
.yieldIntegratedLabel.left b{font-size:.59rem!important;line-height:1!important;margin:0!important;color:#f2c94c!important;font-weight:950!important;white-space:nowrap!important}
div[data-testid="stNumberInput"]{height:38px!important;margin:0 0 0 -1px!important;padding:0!important}
div[data-testid="stNumberInput"]>div{height:38px!important;margin:0!important;padding:0!important;border-radius:0 9px 9px 0!important;overflow:hidden!important;box-shadow:0 0 0 1px #52657c!important;background:#f4f6f8!important}
div[data-testid="stNumberInput"] input{height:38px!important;border:0!important;border-radius:0!important;background:#f4f6f8!important;font-weight:950!important;padding-left:12px!important}
div[data-testid="stNumberInput"] button{height:38px!important;border-radius:0!important;border-top:0!important;border-bottom:0!important}
div[data-testid="stNumberInput"] button:last-child{border-radius:0 9px 9px 0!important}
@media(max-width:650px){
  .yieldIntegratedLabel.left{height:34px!important;padding:0 7px!important}
  .yieldIntegratedLabel.left span{font-size:.43rem!important}
  .yieldIntegratedLabel.left b{font-size:.50rem!important}
  div[data-testid="stNumberInput"],div[data-testid="stNumberInput"]>div,div[data-testid="stNumberInput"] input,div[data-testid="stNumberInput"] button{height:34px!important}
}

/* V6.52 refinement polish */
.yieldIntegratedLabel.left span{font-size:.60rem!important;font-weight:900!important;letter-spacing:.01em!important}
.yieldIntegratedLabel.left b{font-size:.70rem!important;font-weight:1000!important;margin-top:2px!important}
.filterSection{font-size:.60rem;font-weight:950;letter-spacing:.10em;color:#66778c;margin:12px 0 5px;border-top:1px solid #dce2e9;padding-top:10px}
div[data-testid="stPopoverBody"]{min-width:360px!important;padding:16px 18px!important}
div[data-testid="stPopoverBody"] label p{font-size:.78rem!important;line-height:1.25!important}
div[data-testid="stPopoverBody"] div[data-testid="stNumberInput"]{height:auto!important;margin:0 0 8px!important}
div[data-testid="stPopoverBody"] div[data-testid="stNumberInput"]>div{height:38px!important;border-radius:7px!important;box-shadow:none!important}
div[data-testid="stPopoverBody"] div[data-testid="stNumberInput"] input{height:38px!important;border-radius:7px 0 0 7px!important}
@media(max-width:650px){div[data-testid="stPopoverBody"]{min-width:300px!important;padding:13px!important}.yieldIntegratedLabel.left span{font-size:.50rem!important}.yieldIntegratedLabel.left b{font-size:.58rem!important}}

/* V6.55 usable filter panel */
div[data-testid="stPopoverBody"]{min-width:390px!important;max-width:430px!important;padding:15px 17px!important}
div[data-testid="stPopoverBody"] .filterSection{margin:10px 0 5px!important;padding-top:8px!important}
div[data-testid="stPopoverBody"] [data-testid="stTextInput"] input,
div[data-testid="stPopoverBody"] [data-testid="stNumberInput"] input{font-size:.82rem!important}
div[data-testid="stPopoverBody"] [data-testid="stMultiSelect"]{margin-bottom:4px!important}
div[data-testid="stPopoverBody"] label p{color:#334155!important;font-weight:750!important}
div[data-testid="stPopoverBody"] input:disabled{opacity:1!important}
@media(max-width:650px){div[data-testid="stPopoverBody"]{min-width:310px!important;max-width:94vw!important;padding:12px!important}}

/* V6.58 visible historical-sale research */
.historyAction{margin-top:7px}
.historyAction a{display:block;text-align:center;text-decoration:none!important;background:#101b28;color:#cbd8e8!important;border:1px solid #334862;border-radius:7px;padding:7px 7px;font-size:.63rem;font-weight:850}
.historyAction a:hover{border-color:#f2c94c;color:#f2c94c!important}
@media(max-width:650px){.historyAction{margin-top:5px}.historyAction a{font-size:.46rem;padding:5px 3px}}

/* V6.67 nonblocking inline filters */
.filterToolbarLabel{height:38px;display:flex;align-items:center;justify-content:center;border:1px solid #3a4b62;border-radius:8px;background:#131e2c;color:#dce7f4;font-size:.68rem;font-weight:850}
.filterClearSpacer{height:28px}
div[data-testid="stExpander"]:has(input[aria-label="Area / town / postcode"]){background:#0f1824!important;border-color:#344861!important}
@media(max-width:650px){.filterToolbarLabel{height:34px;font-size:.54rem}.filterClearSpacer{height:0}}
</style>
""",unsafe_allow_html=True)

if LIGHT_MODE:
    st.markdown("""
    <style>
    /* V6.68 complete light palette */
    .stApp{background:#f5f7fa!important;color:#182230!important}
    .block-container{background:transparent!important}
    .hero{background:linear-gradient(105deg,#ffffff 0%,#f7f9fc 100%)!important;border-color:#c9d2df!important;box-shadow:0 8px 22px rgba(26,43,63,.10)!important}
    .hero:before{background:#e7b928!important}
    .brand{color:#17202b!important;text-shadow:none!important}.brand b{color:#c89400!important}
    .tagline{color:#314153!important}.sub{color:#748397!important}.badge{background:#edf8f0!important;border-color:#83b894!important;color:#23613a!important}
    .card{background:#ffffff!important;border-color:#ccd5e1!important;box-shadow:0 4px 14px rgba(26,43,63,.09)!important}
    .card:hover{border-color:#8fa1b8!important;box-shadow:0 9px 22px rgba(26,43,63,.13)!important}
    .noimg{background:#eef2f6!important;color:#68788c!important}
    .src{color:#9a6a00!important}.addr{color:#17202b!important}
    .metric{background:#f7f9fc!important;border-color:#d5dde7!important}.metric span{color:#68778a!important}.metric b{color:#17202b!important}
    .yieldMetric{background:#edf8f0!important;border-color:#b5d8bf!important}.yieldMetric b{color:#23613a!important}
    .meta{color:#68778a!important}.chip{background:#f2f5f9!important;border-color:#cbd5e1!important;color:#2b394a!important}
    .analysis{border-color:#d4dbe5!important}.analysis summary{color:#2b394a!important}
    .fact{background:#f7f9fc!important;border-color:#d6dee8!important}.fact span{color:#728195!important}.fact b{color:#17202b!important}
    .iread{background:#fff9e8!important;border-left-color:#d8a400!important}.iread span{color:#9a6a00!important}.iread p{color:#344255!important}
    .research a,.mapAction{background:#f5f7fa!important;border-color:#c7d1de!important;color:#31455c!important}
    .research a:hover,.mapAction:hover{border-color:#b48700!important;color:#8a6500!important}
    .action{background:#d99a00!important;color:#ffffff!important}
    .statusrow{background:#ffffff!important;border-color:#ced7e2!important;color:#243246!important}
    div[data-testid="stExpander"]{background:#ffffff!important;border-color:#ccd6e2!important;color:#1f2b3a!important}
    div[data-testid="stExpander"] *{color:inherit}
    .filterToolbarLabel,.yieldIntegratedLabel{background:#ffffff!important;border-color:#c9d3df!important;color:#27364a!important}
    .yieldIntegratedLabel span{color:#718094!important}
    div[data-testid="stButton"]>button{background:#ffffff!important;border-color:#c5cfdb!important;color:#243246!important}
    div[data-testid="stButton"]>button[kind="primary"]{background:#d99a00!important;border-color:#c68d00!important;color:#ffffff!important}
    div[data-testid="stNumberInput"] input,div[data-testid="stTextInput"] input{background:#ffffff!important;color:#17202b!important;border-color:#c9d3df!important}
    div[data-baseweb="select"]>div{background:#ffffff!important;color:#17202b!important;border-color:#c9d3df!important}
    div[data-testid="stMultiSelect"] span{color:#17202b!important}
    div[data-baseweb="tab-list"]{background:transparent!important}
    button[data-baseweb="tab"]{color:#435267!important}
    button[data-baseweb="tab"][aria-selected="true"]{color:#17202b!important}
    div[data-testid="stDataFrame"]{background:#ffffff!important}
    p,small,label{color:inherit}
    @media(max-width:650px){.stApp{background:#f3f5f8!important}.card{box-shadow:0 2px 8px rgba(26,43,63,.08)!important}}
    </style>
    """,unsafe_allow_html=True)


@st.cache_data(ttl=1800,show_spinner=False)
def _v654_priority_boot_rows():
    jobs={
        "Pattinson":_pattinson_current,
        "Clive Emson":_clive_emson_current,
        "Strettons":_strettons_current,
        "Acuitus":_acuitus_current,
    }
    out=[]
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs={ex.submit(fn):src for src,fn in jobs.items()}
        for f in as_completed(futs):
            try:
                out.extend(f.result() or [])
            except Exception:
                pass
    return _clean_rows(out)

rows,health,updated=load_rows()
try:
    priority=_v654_priority_boot_rows()
    if priority:
        rows=_merge_property_universe(rows,priority)
    rows=[r for r in rows if r.get("source")!="Clive Emson" or re.search(r"/properties/\d+/\d+/?$",r.get("url") or "",re.I)]
    rows=_v657_localise_priority_rows(rows)
    rows=[_normalise_rent_semantics(r) for r in rows]
except Exception:
    pass
st.markdown(
    '<div class="hero"><div><div class="brand">AUCTION <b>SNIPER</b></div>'
    '<div class="tagline">UK commercial auction deal scanner</div>'
    f'<div class="sub">{BUILD} · {html.escape(updated or "")}</div></div>'
    f'<div class="badge">{len(rows)} verified lots</div></div>',
    unsafe_allow_html=True
)

# Compact utility strip: actions stay visible without consuming the page.
tool_a,tool_b,tool_theme,tool_yield_label,tool_yield,tool_space=st.columns([1.05,1.15,1.00,.38,.58,2.80],gap=None)
with tool_a:
    if st.button("↻ Update listings",type="primary",use_container_width=True,help="Refresh current auction lots and property photos"):
        with st.spinner("Updating current commercial auction listings and photos…"):
            refresh_market()
        st.rerun()
with tool_b:
    st.markdown('<div class="filterToolbarLabel">Filters below ↓</div>',unsafe_allow_html=True)
with tool_theme:
    st.toggle("☀️ Light background",key="light_mode",help="Switch between the dark board and a white/light interface")

with tool_yield_label:
    st.markdown('<div class="yieldIntegratedLabel left"><span>Target</span><b>Yield (%)</b></div>',unsafe_allow_html=True)
with tool_yield:
    target_yield=st.number_input(
        "Target yield (%)",
        min_value=1.0,max_value=30.0,value=10.0,step=.5,format="%.1f",
        help="Target yield — changes the max purchase price on every rented property",
        label_visibility="collapsed"
    )


# Nonblocking full-width filter panel. Unlike a popover it never overlays or dims the board.
with st.expander("🔎 Refine properties",expanded=False):
    st.caption("Use any combination. Leave blank / zero to show the full board.")
    f1,f2,f3,f4=st.columns([2.0,2.0,1.15,1.15])
    with f1:
        area_query=st.text_input(
            "Area / town / postcode",value="",placeholder="e.g. Stoke, London, ST1, Wales",
            help="Matches the property address and captured listing description.",key="filter_area_query")
    with f2:
        source_options=sorted({x["source"] for x in rows})
        chosen=st.multiselect("Auction house",source_options,default=[],placeholder="All auction houses",key="filter_sources")
    with f3:
        max_price=st.number_input("Maximum guide (£)",min_value=0,value=0,step=5000,format="%d",help="0 means no maximum.",key="filter_max_price")
    with f4:
        min_yield=st.number_input("Minimum GIY (%)",min_value=0.0,max_value=100.0,value=0.0,step=.5,format="%.1f",help="0 means no minimum.",key="filter_min_yield")
    f5,f6,f7=st.columns([2.0,2.0,1.0])
    with f5:
        tenure_choice=st.multiselect("Tenure",["Freehold","Leasehold"],default=[],placeholder="Any tenure",key="filter_tenure")
    with f6:
        include_unknown=st.toggle("Keep properties where price / yield is unknown",value=True,key="filter_include_unknown")
    with f7:
        st.markdown('<div class="filterClearSpacer"></div>',unsafe_allow_html=True)
        clear_filters=st.button("Clear filters",use_container_width=True,key="clear_property_filters")
    apply_filters=bool((area_query or "").strip() or chosen or max_price>0 or min_yield>0 or tenure_choice)
    active_count=sum([bool((area_query or "").strip()),bool(chosen),max_price>0,min_yield>0,bool(tenure_choice)])
    if active_count:
        st.caption(f"{active_count} filter{'s' if active_count != 1 else ''} active")
    if clear_filters:
        for k,v in {
            "filter_area_query":"","filter_sources":[],"filter_max_price":0,
            "filter_min_yield":0.0,"filter_include_unknown":True,"filter_tenure":[],
        }.items():
            st.session_state[k]=v
        st.rerun()

lots_tab,sources_tab=st.tabs(["🎯 All properties","📡 Source health"])

EXPECTED_CURRENT_COUNTS = {
    "Savills Auctions": 23,
    "Auction House London": 28,  # verified commercial floor; live collector may exceed this
    "Bond Wolfe": 20,
    "Barnard Marcus": 4,
    "Auction House East Anglia": 7,
    "Auction House West Yorkshire": 4,
    "Auction House Sussex & Hampshire": 1,
    "Auction House South West": 1,
    "Pugh / BTG Eddisons": 19,
    "Strettons": 19,
    "Acuitus": 7,
    "Pattinson": 1,
    "Clive Emson": 1,
    "Auction House Wales": 6,
    "Auction House Cumbria": 5,
    "Auction House North East": 4,
    "Auction House North West": 16,
}

with sources_tab:
    # Self-audit: this should make regressions visible without waiting for manual checking.
    source_audit={}
    for p in rows:
        src=p.get("source","Unknown")
        a=source_audit.setdefault(src,{"properties":0,"images":0,"commercial_flags":0,"exact_pages":0})
        a["properties"]+=1
        _u=p.get("url") or ""
        if _u and not any(x in _u for x in ("/for-sale/","/find-a-property","/property-search","/auctions/live-stream/")):
            a["exact_pages"]+=1
        if p.get("image"): a["images"]+=1
        txt=(str(p.get("address") or "")+" "+str(p.get("desc") or "")).lower()
        if any(x in txt for x in ("terraced house","semi-detached house","detached house","bungalow"," bedroom flat","apartment")):
            if not any(x in txt for x in ("mixed-use","mixed use","commercial unit","retail","shop","office","industrial","warehouse","care home")):
                a["commercial_flags"]+=1

    st.info("INTERMEDIATE BUILD — live catalogue enrichment is enabled; source audit below should be checked after Refresh market.")
    st.markdown("#### Capture audit")
    st.caption("Expected counts are minimum independently verified current commercial/mixed-use lots. Falling below them is a release failure.")
    audit_rows=[]
    for src,a in sorted(source_audit.items()):
        image_pct=(100*a["images"]/a["properties"]) if a["properties"] else 0
        audit_status=("❌ CHECK" if a["commercial_flags"]>0 or image_pct<70
                      else "⚠️ PARTIAL" if image_pct<100
                      else "✅ GOOD")
        audit_rows.append({
            "Source":src,
            "Lots":a["properties"],
            "Images":a["images"],
            "Image coverage":f"{image_pct:.0f}%",
            "Exact pages":f'{a["exact_pages"]}/{a["properties"]}', 
            "Residential flags":a["commercial_flags"],
            "Expected min":EXPECTED_CURRENT_COUNTS.get(src,"—"),
            "Coverage":(f'{100*a["properties"]/EXPECTED_CURRENT_COUNTS[src]:.0f}%' if src in EXPECTED_CURRENT_COUNTS and EXPECTED_CURRENT_COUNTS[src] else "—"),
            "Audit":("❌ MISSING LOTS" if src in EXPECTED_CURRENT_COUNTS and a["properties"] < EXPECTED_CURRENT_COUNTS[src] else audit_status),
        })
    if audit_rows:
        st.dataframe(audit_rows,use_container_width=True,hide_index=True)

    actual_counts={}
    for p in rows:
        actual_counts[p["source"]]=actual_counts.get(p["source"],0)+1
    for h in health:
        if actual_counts.get(h["source"]):
            h=dict(h)
            h["note"]=f'{actual_counts[h["source"]]} properties loaded · '+h["note"]
        icon="✅" if "VERIFIED" in h["status"] or "REFRESHED" in h["status"] else ("⏳" if "PENDING" in h["status"] or "EARLY" in h["status"] else "⚠️")
        st.markdown(f'<div class="statusrow">{icon} <b>{html.escape(h["source"])}</b> — {html.escape(h["status"])}<br><small>{html.escape(h["note"])}</small></div>',unsafe_allow_html=True)


@st.cache_data(ttl=21600, show_spinner=False)
def _property_detail_text(url):
    if not url: return ""
    try:
        s=BeautifulSoup(fetch(url),"lxml")
        main=s.find("main") or s
        for tag in main.find_all(["script","style","nav","footer","header"]): tag.decompose()
        return norm(main.get_text(" ",strip=True))
    except Exception: return ""

def _source_text(p):
    """
    Render-path safe: use only data already captured for the property.
    Never fetch exact property pages while building the board.
    """
    parts=[
        p.get("desc"),
        p.get("address"),
        p.get("tenure"),
        p.get("vat"),
        p.get("legal_text"),
        p.get("rent_evidence"),
        p.get("previous_rent_evidence"),
        p.get("erv_evidence"),
    ]
    return norm(" ".join(str(x or "") for x in parts))

def _parse_date_any(s):
    from datetime import datetime
    for fmt in ("%d.%m.%Y","%d/%m/%Y","%d-%m-%Y","%d %B %Y","%d %b %Y"):
        try: return datetime.strptime(norm(s),fmt).date()
        except Exception: pass
    return None

def _remaining_years(s):
    from datetime import date
    d=_parse_date_any(s)
    return None if not d else max(0,(d-date.today()).days/365.2425)

SAVILLS_VERIFIED_AREAS = {
    "Lot 73": (None,None),
    "Lot 75": (8912,827.92),
    "Lot 76": (2809,260.94),
    "Lot 77": (1103,102.47),
    "Lot 78": (7749,719.88),
    "Lot 79": (7715,716.74),
    "Lot 81": (1862,172.98),
    "Lot 83": (1356,125.98),
    "Lot 84": (11634,1080.90),
    "Lot 87": (2551,236.99),
    "Lot 96": (3553,330.10),
    "Lot 98": (3423,318.00),
}

TOWN_RELETTING_BASE = {
    # Town/catchment is intentionally only 10% of the final reletting score.
    "bath":7.5, "beaconsfield":7.3, "west malling":6.5, "petworth":6.2,
    "enfield":6.3, "northampton":5.6, "hythe":5.3, "crewe":5.0,
    "hull":4.8, "barnsley":4.5, "carmarthen":4.4, "wallasey":4.3,
    "liscard":4.3, "alfreton":4.3, "mexborough":3.8, "haverfordwest":4.2,
}

# Verified address-level evidence. These are micro-market facts, not covenant scores.
# They are deliberately source/address-specific and never keyed by lot number alone.
RELETTING_EVIDENCE = {
    "tutt antiques, angel street, petworth": {
        "micro_pitch":3.2,
        "occupier_depth":3.4,
        "vacancy_evidence":3.0,
        "note":"Commercial use on a predominantly residential/period street; vacant and reliant on a relatively narrow independent/specialist occupier pool.",
        "hard_cap":4.4,
    },
    "unit 5b, 10-18 queen street, barnsley": {
        "micro_pitch":7.4,
        "occupier_depth":4.2,
        "vacancy_evidence":5.0,
        "note":"Prime pedestrianised pitch, but 7,749 sq ft is a large retail quantum for the Barnsley occupier market.",
        "hard_cap":5.5,
    },
    "unit 5a, 10-18 queen street, barnsley": {
        "micro_pitch":7.4,
        "occupier_depth":5.5,
        "vacancy_evidence":5.2,
        "note":"Prime pedestrianised pitch and materially smaller 1,862 sq ft unit, giving better occupier depth than Unit 5B.",
        "hard_cap":6.2,
    },
    "54-56 wallasey road, wallasey": {
        "micro_pitch":6.3,
        "occupier_depth":4.8,
        "vacancy_evidence":5.4,
        "note":"Established Liscard retail parade with national nearby occupiers, but weaker wider catchment and a double-width unit limit depth.",
        "hard_cap":5.8,
    },
    "unit 3, 15 john street, carmarthen": {
        "micro_pitch":6.0,
        "occupier_depth":4.5,
        "vacancy_evidence":4.8,
        "market_rent":45000,
        "market_rent_source":"proposed regear rent",
        "note":"Established retail pitch, but current £65,000 passing rent is materially above the £45,000 proposed regear evidence.",
        "hard_cap":5.2,
    },
    "15 red street, carmarthen": {
        "micro_pitch":5.8,
        "occupier_depth":4.2,
        "vacancy_evidence":4.6,
        "note":"Town-centre retail location, but 3,553 sq ft is a sizeable unit for Carmarthen and replacement demand is likely narrower.",
        "hard_cap":5.1,
    },
    "unit 5, the marsh, hythe": {
        "micro_pitch":5.8,
        "occupier_depth":5.0,
        "vacancy_evidence":5.0,
        "note":"Established local parade, but Hythe is a smaller occupier market; covenant strength is excluded from reletting.",
        "hard_cap":5.8,
    },
}

def _address_evidence(address):
    a=(address or "").lower().strip()
    for key,data in RELETTING_EVIDENCE.items():
        if key in a:
            return data
    return {}


def _town_base(address):
    a=(address or "").lower()
    for town,score in TOWN_RELETTING_BASE.items():
        if town in a:
            return score,town.title()
    return 5.0,"Neutral / unclassified town"

def _property_area(p,text):
    lot=p.get("lot")
    source=(p.get("source") or "").lower()
    if p.get("area_sqft"):
        try:
            sqft=float(p["area_sqft"])
            return sqft,sqft/10.7639
        except Exception:
            pass
    # Verified lookup is Savills-only: never leak a Savills Lot 78 size onto another auctioneer's Lot 78.
    if "savills" in source and lot in SAVILLS_VERIFIED_AREAS and SAVILLS_VERIFIED_AREAS[lot][0]:
        return SAVILLS_VERIFIED_AREAS[lot]
    return _extract_floor_area(text)

def _extract_floor_area(text):
    """Return (sqft, sqm), normalised from either unit. Never returns a scalar."""
    sqft_vals=[]; sqm_vals=[]
    for m in re.finditer(r"([\d,]+(?:\.\d+)?)\s*(?:sq\s*ft|sqft|square feet)",text or "",re.I):
        try:
            v=float(m.group(1).replace(",",""))
            if 50<=v<=1_000_000: sqft_vals.append(v)
        except Exception: pass
    for m in re.finditer(r"([\d,]+(?:\.\d+)?)\s*(?:sq\s*m|sqm|m²|square metres|square meters)",text or "",re.I):
        try:
            v=float(m.group(1).replace(",",""))
            if 5<=v<=100_000: sqm_vals.append(v)
        except Exception: pass
    sqft=max(sqft_vals) if sqft_vals else None
    sqm=max(sqm_vals) if sqm_vals else None
    if sqft is None and sqm is not None: sqft=sqm*10.7639
    if sqm is None and sqft is not None: sqm=sqft/10.7639
    return sqft,sqm


def _unit_liquidity(p,facts,text):
    low=(text or "").lower(); score=5.0; pos=[]; risk=[]
    area,_sqm=_property_area(p,text)
    if area:
        if area<=1000: score+=1.2; pos.append(f"Small unit ({area:,.0f} sq ft) gives a broader occupier pool.")
        elif area<=2500: score+=0.6; pos.append(f"Manageable unit size ({area:,.0f} sq ft).")
        elif area<=5000: score-=0.2; risk.append(f"Mid-large unit ({area:,.0f} sq ft) narrows occupier depth.")
        elif area<=10000: score-=1.2; risk.append(f"Large unit ({area:,.0f} sq ft) materially narrows occupier demand.")
        else: score-=2.0; risk.append(f"Very large unit ({area:,.0f} sq ft) has limited occupier depth.")
    if any(x in low for x in ("care home","cinema","church","nightclub","petrol station","department store")):
        score-=1.0; risk.append("Specialist configuration reduces replacement-tenant flexibility.")
    if any(x in low for x in ("parking","car park","service yard","loading bay")):
        score+=0.4; pos.append("Parking/loading improves usability.")
    return max(1.0,min(10.0,score)),area,pos[:3],risk[:3]


def _pitch_evidence(text):
    low=text.lower(); score=5.0; pos=[]; risk=[]; evidence=0
    if any(x in low for x in ("prime retail pitch","principal pedestrianised","busy high street","prominent corner","town centre","city centre","high footfall")):
        score+=0.7; evidence+=1; pos.append("Particulars indicate a stronger/prominent pitch.")
    if any(x in low for x in ("secondary pitch","secondary parade","tertiary","edge of town","limited footfall","secondary retail")):
        score-=0.9; evidence+=1; risk.append("Particulars indicate a secondary/weaker pitch.")
    return max(1.0,min(10.0,score)),pos,risk,evidence

def _rental_stress(p,text):
    rent=p.get("rent"); vals=[]
    for label,pat in [("Proposed rent",r"(?:proposed rent|new rent|regear rent)\s*(?:of|at)?\s*£([\d,]+)"),("ERV",r"\bERV\b\s*(?:of|at)?\s*£([\d,]+)"),("Market rent",r"(?:estimated rental value|market rent)\s*(?:of|at)?\s*£([\d,]+)")]:
        for m in re.finditer(pat,text,re.I):
            try:
                v=float(m.group(1).replace(",",""))
                if 500<=v<=5_000_000: vals.append((v,label))
            except: pass
    if not rent or not vals: return None,None,None
    mr,label=min(vals,key=lambda x:x[0]); return mr,(rent-mr)/rent*100,label

def _reletting_assessment(p,facts,text):
    """
    Reletting means: existing tenant disappears tomorrow.

    Score components:
      25% immediate commercial pitch
      20% local occupier depth
      20% unit size/configuration liquidity
      15% vacancy/letting evidence
      10% rent sustainability
      10% town/catchment strength

    Covenant strength is deliberately excluded.
    """
    address=p.get("address") or ""
    low=(text or "").lower()
    ev=_address_evidence(address)
    town_score,town_name=_town_base(address)
    sqft,sqm=_property_area(p,text)

    # 1) Immediate pitch.
    pitch=5.0
    pitch_reason="No strong micro-pitch evidence captured."
    if any(x in low for x in ("prime retail pitch","principal pedestrianised","prime pedestrianised","high footfall","main shopping")):
        pitch=7.2; pitch_reason="Particulars support a strong established commercial pitch."
    elif any(x in low for x in ("popular parade","prominent pitch","town centre","city centre","prominent corner")):
        pitch=6.0; pitch_reason="Established/prominent commercial pitch."
    if any(x in low for x in ("secondary pitch","secondary parade","tertiary","limited footfall")):
        pitch=3.8; pitch_reason="Secondary/weaker commercial pitch."
    if ev.get("micro_pitch") is not None:
        pitch=ev["micro_pitch"]; pitch_reason=ev.get("note",pitch_reason)

    # Residential/isolation signals create a genuine micro-pitch penalty.
    residential_context=any(x in low for x in (
        "predominantly residential","mainly residential","residential street",
        "surrounded by residential","amongst residential"
    ))
    if residential_context:
        pitch=min(pitch,3.5)
        pitch_reason="Commercial premises within a substantially residential context."

    # 2) Occupier depth.
    occupier=5.0
    if any(x in low for x in ("national retailers","range of national retailers","principal retail amenity","main shopping")):
        occupier=6.1
    if any(x in low for x in ("small market town","village","rural location")):
        occupier=4.0
    if ev.get("occupier_depth") is not None:
        occupier=ev["occupier_depth"]

    # 3) Unit liquidity: size is a major input.
    unit=5.0
    unit_reason="Size/configuration not sufficiently evidenced."
    if sqft:
        if sqft<=750:
            unit=7.8; unit_reason=f"Very small unit ({sqft:,.0f} sq ft): broad potential occupier pool."
        elif sqft<=1500:
            unit=7.0; unit_reason=f"Small unit ({sqft:,.0f} sq ft): comparatively flexible."
        elif sqft<=3000:
            unit=6.0; unit_reason=f"Manageable unit ({sqft:,.0f} sq ft)."
        elif sqft<=5000:
            unit=4.8; unit_reason=f"Larger unit ({sqft:,.0f} sq ft): narrower replacement pool."
        elif sqft<=10000:
            unit=3.4; unit_reason=f"Large unit ({sqft:,.0f} sq ft): materially narrower occupier pool."
        else:
            unit=2.5; unit_reason=f"Very large unit ({sqft:,.0f} sq ft): specialist/deep occupier demand required."
    if any(x in low for x in ("care home","cinema","church","nightclub","petrol station","department store")):
        unit=max(1.0,unit-1.0)
        unit_reason+=" Specialist configuration adds friction."
    if any(x in low for x in ("parking","car park","service yard","loading bay","rear loading")):
        unit=min(10.0,unit+0.4)

    # 4) Vacancy / letting evidence.
    vacancy=5.0
    vacancy_reason="No strong local letting/vacancy evidence captured."
    if "vacant" in low or "vacant possession" in low:
        vacancy=4.2
        vacancy_reason="Currently vacant: no existing occupation evidence supporting immediate demand."
    if any(x in low for x in ("long standing occupier","tenant in occupation","occupation for 10+ years","occupation 20+ years")):
        vacancy=5.5
        vacancy_reason="Long occupation provides some evidence that the unit can sustain commercial use."
    if ev.get("vacancy_evidence") is not None:
        vacancy=ev["vacancy_evidence"]

    # 5) Rent sustainability.
    market_rent,stress,stress_source=_rental_stress(p,text)
    if ev.get("market_rent") is not None:
        market_rent=float(ev["market_rent"])
        stress_source=ev.get("market_rent_source","market evidence")
        stress=((p.get("rent")-market_rent)/p.get("rent")*100) if p.get("rent") else None

    rent_support=5.0
    rent_reason="No independent/regear rental evidence captured; neutral assumption."
    if market_rent is not None and p.get("rent"):
        if stress>=30:
            rent_support=2.0
        elif stress>=20:
            rent_support=3.0
        elif stress>=10:
            rent_support=4.0
        elif stress>=-10:
            rent_support=6.0
        else:
            rent_support=6.5
        rent_reason=f"{stress_source.title()} £{market_rent:,.0f} versus passing rent £{p['rent']:,.0f} ({stress:.0f}% stress)."

    # 6) Town/catchment.
    # Only 10%: an affluent town cannot rescue a poor unit/pitch.
    score=(0.25*pitch + 0.20*occupier + 0.20*unit +
           0.15*vacancy + 0.10*rent_support + 0.10*town_score)

    # Hard caps: these are deliberately non-linear.
    caps=[]
    if residential_context:
        caps.append((4.4,"Predominantly residential micro-location caps reletting at DIFFICULT."))
    if sqft and sqft>10000 and occupier<6.0:
        caps.append((4.5,"Very large unit in a limited occupier market caps reletting at DIFFICULT."))
    elif sqft and sqft>7500 and town_score<5.5:
        caps.append((5.2,"Large unit in a weaker regional market prevents a GOOD reletting rating."))
    if ("vacant" in low or "vacant possession" in low) and pitch<4.5:
        caps.append((4.3,"Vacant property on a weak/non-core pitch has prolonged-void risk."))
    if stress is not None and stress>=30:
        caps.append((4.8,"Passing rent is >30% above evidenced alternative rent."))
    if ev.get("hard_cap") is not None:
        caps.append((float(ev["hard_cap"]),ev.get("note","Address-level market evidence imposes a cap.")))

    for cap,_reason in caps:
        score=min(score,cap)

    score=max(1.0,min(10.0,score))
    label=("VERY STRONG" if score>=8.0 else
           "GOOD" if score>=6.5 else
           "MODERATE" if score>=5.0 else
           "DIFFICULT" if score>=3.5 else
           "HIGH RISK")

    evidence_points=sum([
        1 if sqft else 0,
        1 if ev else 0,
        1 if market_rent is not None else 0,
        1 if pitch_reason!="No strong micro-pitch evidence captured." else 0,
        1 if vacancy_reason!="No strong local letting/vacancy evidence captured." else 0,
    ])
    confidence="HIGH" if evidence_points>=4 else "MEDIUM" if evidence_points>=2 else "LOW"

    return {
        "score":score,"label":label,"confidence":confidence,
        "town_score":town_score,"town_name":town_name,
        "pitch_score":pitch,"occupier_score":occupier,"unit_score":unit,
        "vacancy_score":vacancy,"rent_score":rent_support,
        "sqft":sqft,"sqm":sqm,
        "market_rent":market_rent,"rent_stress":stress,"market_rent_source":stress_source,
        "pitch_reason":pitch_reason,"unit_reason":unit_reason,
        "vacancy_reason":vacancy_reason,"rent_reason":rent_reason,
        "caps":[r for _c,r in caps],
    }


def _investment_interpretation(f):
    notes=[]; yrs=f.get("_remaining_years")
    if "national" in f.get("Covenant","").lower(): notes.append("Recognised national/operator covenant.")
    elif f.get("Tenant"): notes.append("Tenant identified; financial covenant strength still needs verification.")
    if yrs is not None:
        if yrs<4: notes.append(f"Relatively short income: about {yrs:.1f} years to expiry.")
        elif yrs<7: notes.append(f"Medium-short income: about {yrs:.1f} years to expiry.")
        else: notes.append(f"About {yrs:.1f} years of contractual income, subject to any break.")
    if "outstanding" in f.get("Rent review / steps","").lower(): notes.append("Outstanding rent review may provide rental uplift; outcome is unproven.")
    if f.get("Break clause"): notes.append("Break clause may shorten the effective income term; exact date/party shown above.")
    if "Vacant" in f.get("Occupation",""): notes.append("No passing income: value depends on reletting/development prospects.")
    return notes[:4]

def _investment_facts(p):
    text=_source_text(p); low=text.lower(); f={}; chips=[]
    tenure=p.get("tenure") or ("Freehold" if "freehold" in low else "Leasehold" if "leasehold" in low else None)
    if tenure: f["Tenure"]=tenure

    tenant=p.get("tenant")
    if not tenant:
        for pat in [
            r"(?:fully\s+)?let to\s+([^.;\n]{2,100}?)(?=\s+on\s+(?:a\s+)?\d|\s+paying|\s+at\s+(?:a\s+)?rent|[.;])",
            r"leased to\s+([^.;\n]{2,100}?)(?=\s+on\s+(?:a\s+)?\d|\s+paying|[.;])",
            r"tenant[:\s]+([^.;\n]{2,90})"]:
            m=re.search(pat,text,re.I)
            if m:
                tenant=norm(m.group(1)).strip("'\"“”")[:90]
                if tenant: break
    if tenant: f["Tenant"]=tenant

    # Prefer structured exact-page collector facts over re-parsing prose.
    if p.get("lease_term"):
        f["Lease term"]=str(p["lease_term"])
    if p.get("lease_start"):
        f["Lease start"]=str(p["lease_start"])
    if p.get("lease_expiry"):
        f["Lease expiry"]=str(p["lease_expiry"])
    if p.get("break_clause"):
        f["Break clause"]=str(p["break_clause"])
    if p.get("rent_review"):
        f["Rent review / steps"]=str(p["rent_review"])
    if p.get("epc"):
        f["EPC"]=str(p["epc"])
    if p.get("rateable_value"):
        f["Rateable value"]=f'£{p["rateable_value"]:,.0f}'
    if p.get("fri") is True:
        f["Repairing"]="FRI"
    if p.get("rent"): f["Passing rent"]=f'£{p["rent"]:,.0f} p.a.'
    if p.get("rent_status"): f["Rent status"]=p["rent_status"]
    if p.get("previous_rent"):
        f["Previous / historic rent"]=f'£{p["previous_rent"]:,.0f} p.a. — NOT current income'
        chips.append("HISTORIC RENT")
    if p.get("erv"):
        f["ERV / market-rent evidence"]=f'£{p["erv"]:,.0f} p.a. — NOT passing rent'
        chips.append(f'ERV £{p["erv"]:,.0f} p.a.')
    if p.get("legal_text"):
        f["Legal documents scanned"]="Yes — extracted text used in analysis"
        chips.append("LEGAL TEXT SCANNED")
    elif p.get("legal_pack_url"):
        f["Legal pack"]="Link found — text not yet extractable"

    m=re.search(r"(\d+(?:\.\d+)?)\s*year\s+(?:full\s+repairing\s+and\s+insuring\s+|FRI\s+)?lease",text,re.I)
    if m: f["Original lease term"]=m.group(1)+" years"
    m=re.search(r"(?:lease\s+)?expir(?:y|ing|es)\s*(?:on\s*)?(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{1,2}\s+[A-Za-z]+\s+\d{4})",text,re.I)
    if m:
        expiry=m.group(1); f["Lease expiry"]=expiry; yrs=_remaining_years(expiry)
        if yrs is not None:
            f["Term remaining"]=f"{yrs:.1f} years"; f["_remaining_years"]=yrs
            if yrs<4: chips.append(f"{yrs:.1f} YRS LEFT")

    if re.search(r"\bFRI\b|full repairing and insuring",text,re.I): f["Repairing"]="FRI"; chips.append("FRI")
    elif re.search(r"\bIRI\b|internal repairing",text,re.I): f["Repairing"]="IRI"

    for pat in [r"((?:tenant|landlord)[^.;]{0,35}break[^.;]{0,100})",r"((?:break clause|option to determine)[^.;]{0,120})"]:
        m=re.search(pat,text,re.I)
        if m: f["Break clause"]=norm(m.group(1))[:140]; chips.append("BREAK"); break

    m=re.search(r"((?:\d{4}\s+)?rent review[^.;]{0,120}(?:outstanding)?|outstanding rent review[^.;]{0,120}|rising to\s+£?[\d,]+[^.;]{0,100})",text,re.I)
    if m:
        rr=norm(m.group(1)); f["Rent review / steps"]=rr[:140]
        if "outstanding" in rr.lower(): chips.append("RENT REVIEW OUTSTANDING")

    m=re.search(r"(\d+)\s*months?\s+deposit",text,re.I)
    if m: f["Rent deposit"]=m.group(1)+" months"
    m=re.search(r"(\d+)\s*months?\s+(?:initial\s+)?rent[- ]free",text,re.I)
    if m: f["Rent free"]=m.group(1)+" months"

    if re.search(r"VAT[- ]free|VAT\s+is\s+not\s+applicable|VAT\s+not\s+applicable|not subject to VAT",text,re.I): f["VAT"]="Not applicable / VAT-free"; chips.append("VAT-FREE")
    elif re.search(r"plus VAT|VAT applicable|subject to VAT|VAT will be payable",text,re.I): f["VAT"]="Applicable"; chips.append("VAT")
    elif re.search(r"option(?:ed)? to tax|opted for VAT",text,re.I): f["VAT"]="Option to tax mentioned"; chips.append("VAT VERIFY")
    if re.search(r"\bTOGC\b|transfer of a business as a going concern",text,re.I): f["TOGC"]="Mentioned"; chips.append("TOGC")

    if re.search(r"vacant possession|\bvacant\b",text,re.I): f["Occupation"]="Vacant / vacant possession"; chips.append("VACANT")
    elif tenant: f["Occupation"]="Tenanted"
    if re.search(r"download the legal pack|legal documents|legal pack",text,re.I): f["Legal pack"]="Available / referenced"; chips.append("LEGAL PACK")

    national=("domino","dp realty","tesco","sainsbury","boots","superdrug","co-op","nationwide","hsbc","barclays","lloyds","natwest","coral","william hill","greggs","subway","costa","starbucks","mcdonald","aldi","lidl","b&m","poundland","british red cross")
    if tenant:
        if any(n in tenant.lower() for n in national): f["Covenant"]="Recognised national operator / established organisation"; chips.append("STRONGER COVENANT")
        else: f["Covenant"]="Tenant identified — strength not yet verified"

    if p.get("guide") and p.get("rent"):
        y=100*p["rent"]/p["guide"]; f["GIY at guide"]=f"{y:.1f}%"; f["10% ceiling"]=f'£{p["rent"]/0.10:,.0f}'; chips.append(f"{y:.1f}% GIY")
    if tenure: chips.insert(0,tenure.upper())
    rel=_reletting_assessment(p,f,text)
    f["Reletting potential"]=f'{rel["score"]:.1f}/10 — {rel["label"]}'
    f["Reletting confidence"]=rel["confidence"]
    f["Immediate pitch"]=f'{rel["pitch_score"]:.1f}/10'
    f["Occupier depth"]=f'{rel["occupier_score"]:.1f}/10'
    f["Unit liquidity"]=f'{rel["unit_score"]:.1f}/10'
    f["Vacancy / letting evidence"]=f'{rel["vacancy_score"]:.1f}/10'
    f["Rent sustainability"]=f'{rel["rent_score"]:.1f}/10'
    f["Town / catchment"]=f'{rel["town_score"]:.1f}/10 — {rel["town_name"]}'
    chips.append(f'RELETTING {rel["label"]}')

    if rel.get("sqft"):
        f["Floor area"]=f'{rel["sqft"]:,.0f} sq ft / {rel["sqm"]:,.0f} sq m'
    if rel.get("market_rent") is not None:
        f["Evidenced re-letting rent"]=f'£{rel["market_rent"]:,.0f} p.a. ({rel["market_rent_source"]})'
        if rel.get("rent_stress") is not None:
            f["Passing-rent stress"]=f'{rel["rent_stress"]:.0f}%'
            f["10% value at re-letting rent"]=f'£{rel["market_rent"]/0.10:,.0f}'

    interpretation=_investment_interpretation(f)
    interpretation.append("Reletting: "+rel["unit_reason"])
    interpretation.append("Pitch: "+rel["pitch_reason"])
    if rel["caps"]:
        interpretation.append("Risk cap: "+rel["caps"][0])
    interpretation=interpretation[:7]
    f.pop("_remaining_years",None)
    return f,list(dict.fromkeys(chips)),interpretation

def _research_links(p):
    import urllib.parse
    address=str(p.get("address") or "").strip()
    if not address: return ""
    qh=urllib.parse.quote(f'"{address}" property auction sold previous listing')
    qp=urllib.parse.quote(f'"{address}" commercial property')
    legal=(f'<a target="_blank" href="{html.escape(str(p.get("legal_pack_url")),quote=True)}">Legal pack / document ↗</a>' if p.get("legal_pack_url") else "")
    return ('<div class="research">'+legal
            +f'<a target="_blank" href="https://www.google.com/search?q={qh}">Sales / auction history ↗</a>'
            f'<a target="_blank" href="https://www.google.com/search?q={qp}">Previous listings ↗</a>'
            f'<a target="_blank" href="https://www.gov.uk/search-house-prices">Land Registry search ↗</a>'
            '</div>')

def _legal_pack_identity(p):
    address=(p.get("address") or "").lower()
    pack_id=p.get("eig_pack_id")
    if not pack_id:
        for key,val in EIG_KNOWN_PACKS.items():
            if key in address:
                pack_id=val; break
    return pack_id

def _legal_pack_status(p):
    """Useful card-level status only: never claim analysis before documents were read."""
    if p.get("legal_analysis"):
        return "Legal Pack Analysis ✓"
    if _legal_pack_identity(p) or p.get("legal_pack_url"):
        return "Legal pack available · upload for analysis"
    return None

def _legal_pack_html(p):
    status=_legal_pack_status(p)
    if not status: return ""
    analysed=p.get("legal_analysis") or {}
    if analysed:
        rows=[]
        for k in ("Passing rent","Tenant","Lease","EPC","VAT","Title","Special conditions"):
            if analysed.get(k): rows.append(f'<div class="fact"><span>{html.escape(k)}</span><b>{html.escape(str(analysed[k]))}</b></div>')
        warnings=analysed.get("warnings") or []
        warn=''.join(f'<p>⚠ {html.escape(str(w))}</p>' for w in warnings)
        return '<details class="analysis legalIntel"><summary>Legal Pack Analysis ✓</summary><div class="factgrid">'+''.join(rows)+'</div><div class="iread">'+warn+'</div></details>'
    # Authentication/download is intentionally user-triggered/provider-independent.
    # HTML cards cannot safely post Streamlit actions, so expose the product state here;
    # interactive analyser is rendered separately below the board for selected/test packs.
    return '<div class="legalPackReady">🔎 '+html.escape(status)+'</div>'

def _facts_html(p):
    facts,chips,interpretation=_investment_facts(p)
    if not facts: return ""
    ch="".join(f'<span class="chip">{html.escape(str(x))}</span>' for x in chips[:7])
    rows="".join(f'<div class="fact"><span>{html.escape(str(k))}</span><b>{html.escape(str(v))}</b></div>' for k,v in facts.items())
    read=""
    if interpretation:
        read="<div class='iread'><span>Investment read</span>"+"".join(f"<p>• {html.escape(n)}</p>" for n in interpretation)+"</div>"
    return f'<div class="chips">{ch}</div><details class="analysis"><summary>Investment details</summary><div class="factgrid">{rows}</div>{read}{_research_links(p)}</details>'


def _safe_card_image_src(source,image_url):
    return image_url or None

def money(v): return "—" if v is None else f"£{v:,.0f}"
def pct(v): return "—" if v is None else f"{v:.1f}%"

with lots_tab:
    lots=list(rows)

    # Every filter works independently; no master switch is required.
    if chosen:
        lots=[x for x in lots if x.get("source") in chosen]

    q=(area_query or "").strip().lower()
    if q:
        terms=[t for t in re.split(r"[,;]+|\s+",q) if t]
        def _matches_area(x):
            hay=(str(x.get("address") or "")+" "+str(x.get("desc") or "")).lower()
            return all(t in hay for t in terms)
        lots=[x for x in lots if _matches_area(x)]

    if tenure_choice:
        wanted={t.lower() for t in tenure_choice}
        lots=[x for x in lots if str(x.get("tenure") or "").lower() in wanted]

    filtered=[]
    for x in lots:
        guide=x.get("guide")
        y=x.get("yield")
        if max_price>0:
            if guide is None:
                if not include_unknown: continue
            elif guide>max_price:
                continue
        if min_yield>0:
            if y is None:
                if not include_unknown: continue
            elif y<min_yield:
                continue
        filtered.append(x)
    lots=filtered

    st.caption(f"{len(lots)} properties shown" + (" · filters applied" if apply_filters else " · ALL verified current properties"))
    cards=[]
    for x in lots:
        y=x.get("yield")
        ceiling=x["rent"]/(target_yield/100.0) if x.get("rent") and target_yield else None
        _sqft,_sqm=_property_area(x,norm(str(x.get("desc") or "")+" "+str(x.get("address") or "")))
        _size_text=(f"{_sqft:,.0f} sq ft / {_sqm:,.0f} sq m" if _sqft else None)
        meta=" · ".join(v for v in [x.get("date"),x.get("tenure"),("VAT "+x["vat"]) if x.get("vat") and x["vat"]!="UNKNOWN" else None] if v)
        _property_url=html.escape(str(x.get("url") or ""),quote=True)
        _address=str(x.get("address") or "").strip()
        _map_query=urllib.parse.quote_plus(_address)
        _maps_url=f"https://www.google.com/maps/search/?api=1&query={_map_query}"
        _history_query=urllib.parse.quote_plus(f'"{_address}" (auction OR sold OR sale OR guide OR lot)')
        _history_url=f"https://www.google.com/search?q={_history_query}"
        _image_src=_safe_card_image_src(x.get("source"),x.get("image"))
        preview=(f'<a class="previewLink" href="{_property_url}" target="_blank" rel="noopener noreferrer"><img class="preview" src="{html.escape(_image_src,quote=True)}" loading="lazy" referrerpolicy="no-referrer"></a>' if _image_src and _property_url
                 else (f'<img class="preview" src="{html.escape(_image_src,quote=True)}" loading="lazy" referrerpolicy="no-referrer">' if _image_src else '<div class="preview noimg">Photo unavailable</div>'))
        cards.append(
            '<div class="card">'+preview+'<div class="cb">'
            +f'<div class="src">{html.escape(x["source"])} · {html.escape(x.get("lot") or "Lot TBC")}</div>'
            +f'<div class="addr">{html.escape(x["address"])}</div><div class="metrics">'
            +f'<div class="metric"><span>Guide</span><b>{money(x.get("guide"))}</b></div>'
            +f'<div class="metric"><span>Rent p.a.</span><b>{money(x.get("rent"))}</b></div>'
            +f'<div class="metric yieldMetric"><span>GIY</span><b>{pct(y)}</b></div>'
            +f'<div class="metric"><span>Max price @ {target_yield:g}% yield</span><b>{money(ceiling)}</b></div>'
            +(f'<div class="metric sizeMetric"><span>Size</span><b>{html.escape(_size_text)}</b></div>' if _size_text else '')
            +'</div>'
            +f'<div class="meta">{html.escape(meta)}</div>'
            +_facts_html(x)
            +_legal_pack_html(x)
            +f'<div class="historyAction"><a target="_blank" rel="noopener noreferrer" href="{html.escape(_history_url,quote=True)}">Previous auctions / sale history ↗</a></div>'
            +f'<div class="cardActions"><a class="mapAction" target="_blank" rel="noopener noreferrer" href="{html.escape(_maps_url,quote=True)}">Map / Street View ↗</a><a class="action" target="_blank" href="{html.escape(x["url"])}">Open property ↗</a></div>'
            +'</div></div>'
        )
    st.markdown('<div class="cards">'+"".join(cards)+'</div>',unsafe_allow_html=True)

    # Provider-independent Buyer Due Diligence. Files are supplied deliberately by the user;
    # authenticated auction-provider accounts are never crawled during catalogue refresh.
    with st.expander("Buyer Due Diligence · analyse a legal pack", expanded=False):
        st.caption("Upload the legal-pack files you want analysed. Mixed file types and ZIP bundles are supported; scanned images are retained for visual review rather than silently OCR-guessed.")
        property_ref=st.text_input("Property / lot reference",value="",placeholder="e.g. 8 Red Street, Carmarthen · Lot 71A",key="dd_property_ref")
        uploads=st.file_uploader("Legal-pack files",accept_multiple_files=True,key="dd_uploads")
        if uploads:
            total_bytes=sum(getattr(f,"size",0) or len(f.getvalue()) for f in uploads)
            st.caption(f"{len(uploads)} file(s) selected · {total_bytes/1024/1024:.1f} MB")
        if st.button("Run Buyer Due Diligence",type="primary",disabled=not bool(uploads),key="run_uploaded_due_diligence"):
            if not analyse_uploaded_pack:
                st.error("Buyer Due Diligence engine is unavailable in this build.")
            else:
                try:
                    supplied=[(f.name,f.getvalue()) for f in uploads]
                    ref=(property_ref or "Uploaded legal pack").strip()
                    with st.spinner("Reading documents, reconciling evidence and building the Investment Assessment…"):
                        result=analyse_uploaded_pack(ref,supplied)
                    cov=result.get("ingestion",{}).get("coverage",{})
                    st.success("Buyer Due Diligence completed" if result.get("status")=="completed" else "Buyer Due Diligence completed with items to verify")
                    c1,c2,c3,c4=st.columns(4)
                    c1.metric("Uploaded",cov.get("uploaded_files",0))
                    c2.metric("Machine-read",cov.get("machine_read_documents",0))
                    c3.metric("Visual review",cov.get("visual_review_required",0))
                    c4.metric("Conversion needed",cov.get("conversion_required",0))
                    st.markdown("### Investment Assessment")
                    st.text_area("Full Buyer Due Diligence report",value=result.get("report_text","") or "No report text produced.",height=620,key="dd_report_text")
                    issues=result.get("ingestion",{}).get("issues",[]) or []
                    if issues:
                        with st.expander("Processing issues / files needing attention"):
                            for issue in issues:
                                st.write(f"• {issue.get('name','File')}: {issue.get('message') or issue.get('reason') or issue.get('status','Review required')}")
                    st.caption("Investment due-diligence aid only — not a substitute for a solicitor or other professional advice.")
                except Exception as e:
                    st.error(f"Legal-pack analysis failed: {e}")

