"""Bank complete retained EIG white-label past-auction grids.

Several independent auctioneers publish flat, paginated past-auction grids
rather than event catalogues.  Every card carries a stable EIG lot UUID and an
individual outcome date; the detail page adds the guide price and richer
property text.  This collector reconciles every pagination page and card
before claiming the retained grid complete.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup, Tag

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCES = {
    "auction-works": {
        "auctioneer": "Auction Works",
        "base": "https://www.auctionworks.co.uk",
        "archive_path": "/search",
    },
    "bradley-hall": {
        "auctioneer": "Bradley Hall",
        "base": "https://auction.bradleyhall.co.uk",
        "archive_path": "/search",
    },
    "brown-co": {
        "auctioneer": "Brown&Co",
        "base": "https://brownandco.eigonlineauctions.com",
        "archive_path": "/search",
    },
    "clarke-simpson": {
        "auctioneer": "Clarke & Simpson",
        "base": "https://clarke-simpson.eigonlineauctions.com",
        "archive_path": "/search",
    },
    "higgins-drysdale": {
        "auctioneer": "Higgins Drysdale National Property Auctions",
        "base": "https://higginsdrysdale.eigonlineauctions.com",
        "archive_path": "/search",
    },
    "the-property-auction-house": {
        "auctioneer": "The Property Auction House",
        "base": "https://thepropertyauctionhouse.eigonlineauctions.com",
        "archive_path": "/search",
    },
    "property-auction-agent": {
        "auctioneer": "Property Auction Agent",
        "base": "https://propertyauctionagent.eigonlineauctions.com",
        "archive_path": "/search",
    },
    "lot9-auction-house": {
        "auctioneer": "Lot9 Auction House",
        "base": "https://lot9.eigonlineauctions.com",
        "archive_path": "/search",
        "operator_legal_name": "LOT9 AUCTION HOUSE LIMITED",
        "operator_company_number": "12953855",
        "partner_agents": ["Monopoly Buy Sell Rent"],
    },
    "auction-north": {
        "auctioneer": "Auction North",
        "base": "https://auction-north.eigonlineauctions.com",
        "archive_path": "/search",
        "operator_legal_name": "AUCTION NORTH LIMITED",
        "operator_company_number": "10762287",
        "partner_agents": ["Dynamic Property Group", "independent local property experts"],
    },
    "sage-co-auctions": {
        "auctioneer": "Sage & Co Auctions",
        "base": "https://sageandco.eigonlineauctions.com",
        "archive_path": "/search",
        "operator_legal_name": "SAGE & CO AUCTIONS LIMITED",
        "operator_company_number": "13328873",
    },
    "bowen": {
        "auctioneer": "Bowen",
        "base": "https://bowensonandwatson.eigonlineauctions.com",
        "archive_path": "/search",
        "historical_trading_names": [
            "Bowen Son and Watson",
            "Bowen Son and Watson with Kent Jones",
        ],
        "merged_firms": ["Kent Jones"],
    },
    "astleys": {
        "auctioneer": "Astleys",
        "base": "https://astleys.eigonlineauctions.com",
        "archive_path": "/search",
        "operator_legal_name": "ASTLEY SAMUEL LEEDER LTD",
        "operator_company_number": "03129558",
    },
    "opal-property": {
        "auctioneer": "Opal Property",
        "base": "https://opal-online.eigonlineauctions.com",
        "archive_path": "/search",
    },
    "newlands-property": {
        "auctioneer": "Newlands Property",
        "base": "https://newlands.eigonlineauctions.com",
        # The site root is only a meta-refresh landing page; request the
        # retained grid directly so zero rows remain a genuine failure.
        "archive_path": "/search",
    },
    "landmark-auctions": {
        "auctioneer": "Landmark Auctions",
        "base": "https://onlineauctions.landmarkauctions.co.uk",
        "archive_path": "/search",
        "operator_legal_name": "LANDMARK AUCTIONS LIMITED",
        "operator_company_number": "13592079",
        "partner_agents": [
            "Daniels Estate Agents",
            "The Landmark Consultancy",
        ],
    },
    "auction-house-online-2025-11": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/75792",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        # The national online catalogue is a shared first-party platform.  Its
        # detail pages publish the responsible regional Auction House branch;
        # retain that attribution instead of inventing a separate auctioneer.
        "auctioneer_from_detail": True,
        # This event route renders its complete 92-card inventory on one page
        # instead of the usual 50-card retained-grid pagination.
        "unpaginated_event": True,
        # Regional collectors can retain the same appearance under an older
        # numeric redirect ID.  A UUID mismatch alone is therefore not new
        # evidence: exclude only an unambiguous exact date/address overlap.
        "exclude_exact_cross_source_overlaps": True,
    },
    "auction-house-online-2025-10": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/74284",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
    },
    "auction-house-online-2025-03-25": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/67455",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
    },
    "auction-house-online-2025-04-15": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/67663",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
    },
    "auction-house-online-2025-05-27": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        # The bare event route repeatedly times out from GitHub's runner.  The
        # platform's explicit all-results query uses a distinct cached route
        # while preserving the same first-party 59-card event inventory.
        "archive_path": "/past-auctions/69595?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
    },
    "auction-house-online-2025-08-19": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/70923",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
    },
    "auction-house-online-2025-11-11": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/75000",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
    },
    "auction-house-online-2025-07-29": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/71414?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 70,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2025-07-22": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/71912?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 36,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2025-07-15": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/71367?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 38,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2025-07-08": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/71777?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 46,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2025-07-01": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/71014?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 37,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2025-05-20": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/69260",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
    },
    "auction-house-online-2025-06-24": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/70967?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 54,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2025-06-17": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/70557?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 40,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2025-06-10": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/70403?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 52,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2025-09-30": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/72575",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
    },
    "auction-house-online-2025-12-16": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/76336?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 87,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2025-12-09": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/75818?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 56,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2025-12-02": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/76033?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 39,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2025-11-18": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/75490?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 82,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2025-10-28": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/74541?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 85,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2025-10-21": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/74653?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 47,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2025-10-14": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/74284?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 44,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2025-10-07": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/74097?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 28,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2025-09-09": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/73292?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 52,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2025-09-23": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/73692?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 39,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2025-09-16": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/73419?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 39,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2025-09-02": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/72950?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 44,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2025-08-26": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/72901?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 34,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2025-08-12": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/72617?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 38,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2025-08-05": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/72017?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 33,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2025-11-04": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/75082?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 48,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-01-13": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/75333",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-06-30": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/82458",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-03-31": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/79607",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-04-14": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/79785?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-02-24": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/78487?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-03-17": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/79291?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-03-24": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/79158?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-04-21": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/80208?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-04-28": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/80207?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-06-09": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/82154?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-05-26": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/81218?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-06-02": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/81603?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-06-16": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/81697?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-06-23": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/82282?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-07-07": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/82831?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-07-14": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/82742?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-07-21": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/83233?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-07-28": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/82834?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 88,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-08-04": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/83949?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 45,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-08-11": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/83905?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 72,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-08-18": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/84252?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 59,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-08-25": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/84203?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 92,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-09-02": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/84329?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 17,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-09-08": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/84567?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 73,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-09-15": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/84412?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 71,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-09-22": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/84253?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 87,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-09-29": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/84327?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 98,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-10-06": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/85376?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 47,
        "allow_expected_visible_card_mismatch": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-10-20": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/85651?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 87,
        "allow_expected_visible_card_mismatch": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-10-13": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/85028?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 87,
        "allow_expected_visible_card_mismatch": True,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "auction-house-online-2026-10-27": {
        "auctioneer": "Auction House Online",
        "base": "https://online.auctionhouse.co.uk",
        "archive_path": "/past-auctions/85650?lotResultType=All",
        "operator_legal_name": "AUCTION HOUSE UK LIMITED",
        "operator_company_number": "06025583",
        "auctioneer_from_detail": True,
        "unpaginated_event": True,
        "expected_visible_cards": 125,
        "exclude_exact_cross_source_overlaps": True,
        "allow_incomplete_detail_recovery": True,
        "detail_attempts": 2,
        "detail_timeout": 45,
    },
    "boultons-harrisons": {
        "auctioneer": "Boultons Harrisons Ltd",
        "base": "https://www.boultonsauctions.co.uk",
    },
    "online-property-auction-group": {
        "auctioneer": "Online Property Auction Group",
        "base": "https://www.opagroup.co.uk",
    },
    "the-auction-company": {
        "auctioneer": "The Auction Company",
        "base": "https://auctions.theauctioncompany.co.uk",
    },
}
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
# EIG's newer white labels expose UUIDs while surviving older grids retain
# platform-wide numeric lot IDs.  Both are stable first-party identities.
LOT_ID_RE = re.compile(r"/lot/details/([0-9a-f-]{36}|\d+)(?:[/?#]|$)", re.I)
ISO_DATE_RE = re.compile(r"^(20\d{2}-\d{2}-\d{2})")
MONEY_RE = re.compile(r"£?\s*([\d,]+(?:\.\d+)?)\s*([MK])?", re.I)
GUIDE_RE = re.compile(r"Guide Price of\s*£?\s*([\d,]+(?:\.\d+)?)\s*([MK])?", re.I)
RENT_RE = re.compile(
    r"£\s*([\d,]+(?:\.\d+)?)\s*"
    r"(per\s+annum|annually|p\.?\s*a\.?|per\s+calendar\s+month|"
    r"per\s+month|monthly|p\.?\s*c\.?\s*m\.?)\b",
    re.I,
)
PARSER_VERSION = 8


def clean(value: str | None) -> str | None:
    value = re.sub(r"\s+", " ", value or "").strip(" ,\xa0")
    return value or None


def amount(match: re.Match | None) -> int | None:
    if not match:
        return None
    parsed = corpus.money(match.group(1) + (match.group(2) or ""))
    return int(parsed) if parsed else None


def exact_date(value: str | None) -> str | None:
    match = ISO_DATE_RE.match(value or "")
    return match.group(1) if match else None


def summary_date_range(rows) -> list[str | None]:
    dates = [row.get("auction_date") for row in rows if row.get("auction_date")]
    return [min(dates), max(dates)] if dates else [None, None]


def annual_rent(match: re.Match | None) -> int | None:
    if not match:
        return None
    value = corpus.money(match.group(1))
    if value is None:
        return None
    period = match.group(2)
    if re.search(r"month|p\.?\s*c\.?\s*m", period, re.I):
        value *= 12
    return int(value)


def get(
    url: str, *, attempts: int = 5, timeout: int = 120
) -> tuple[bytes, str]:
    error = None
    for attempt in range(attempts):
        try:
            response = requests.get(url, headers=HEADERS, timeout=timeout)
            response.raise_for_status()
            if len(response.content) < 1000:
                raise ValueError("response is unexpectedly short")
            return response.content, response.url
        except (requests.RequestException, ValueError) as exc:
            error = exc
            if attempt < attempts - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"failed to fetch {url}: {error}")


def status_and_price(value: str | None) -> tuple[str, int | None]:
    text = (clean(value) or "").casefold()
    if "sold prior" in text or "sale agreed prior" in text:
        status = "sold_prior"
    elif (
        "sold post" in text or "sold after" in text
        or "sale agreed post" in text or "sale agreed after" in text
    ):
        status = "sold_after"
    elif re.search(r"\bsold\b|\bsale agreed\b", text):
        status = "sold"
    elif "withdrawn" in text:
        status = "withdrawn"
    elif "postponed" in text:
        status = "postponed"
    elif "no bids" in text or "unsold" in text:
        status = "unsold"
    elif "available" in text:
        status = "available"
    else:
        status = "unknown"
    price_match = re.search(
        r"(?:sold(?:\s+(?:prior|post|after))?(?:\s+for)?|"
        r"sale agreed(?:\s+(?:prior|post|after))?(?:\s+for)?|for|price)\s+£\s*"
        r"([\d,]+(?:\.\d+)?)\s*([MK])?",
        value or "", re.I,
    )
    price = amount(price_match) if status in {"sold", "sold_prior", "sold_after"} else None
    return status, price


def classify_sector(address: str | None, text: str | None) -> str:
    """Prefer the described asset over speculative alternative-use wording."""
    address_text = (clean(address) or "").casefold()
    detail_text = (clean(text) or "").casefold()
    combined = f"{address_text} {detail_text}"
    if re.search(r"\b(land|plot|woodland|grazing|roadway)\b", address_text):
        return "land"
    if re.search(
        r"\b(mixed[ -]?use|commercial (?:and|with) residential|residential (?:and|with) commercial|"
        r"shop (?:and|with) (?:a )?flat|retail (?:and|with) (?:a )?flat)\b",
        combined,
    ):
        return "mixed-use"
    if re.search(
        r"\b(commercial unit|shop|retail|office|public house|pub|inn|church|chapel|theatre|"
        r"hospital|telephone exchange|ground rents?|warehouse|industrial)\b",
        address_text,
    ):
        return "commercial"
    if re.search(
        r"\b(flat|apartment|house|cottage|bungalow|terrace|bedroom|dwelling|maisonette)\b",
        combined,
    ):
        return "residential"
    return corpus.sector(" ".join(filter(None, [address, text])))


def page_count(html: str) -> int:
    soup = BeautifulSoup(html, "lxml")
    pages = {1}
    for link in soup.select('a[href*="page="]'):
        for value in parse_qs(urlsplit(link.get("href") or "").query).get("page", []):
            if value.isdigit():
                pages.add(int(value))
    return max(pages)


def published_denominator(html: str) -> int | None:
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    match = re.search(r"Showing results\s+\d+\s*-\s*\d+\s+of\s+([\d,]+)", text, re.I)
    return int(match.group(1).replace(",", "")) if match else None


def parse_grid(html: str, source: dict, evidence: dict) -> tuple[list[dict], list[dict], list[dict]]:
    soup = BeautifulSoup(html, "lxml")
    rows, malformed, excluded_non_auction = [], [], []
    for position, card in enumerate(soup.select(".lot-panel"), 1):
        detail = card.select_one('a[href*="/lot/details/"]')
        property_detail = card.select_one('a[href*="/property/details/"]')
        identity = LOT_ID_RE.search(detail.get("href") or "") if detail else None
        # Current EIG white-labels use ``list-*`` classes, while retained
        # older grids (including Landmark Auctions) use the equally
        # first-party ``grid-*`` markup.  Preserve both rather than treating
        # a valid archived card as malformed evidence.
        address_node = card.select_one(".list-address, .grid-address")
        time_node = card.select_one("time[datetime]")
        scheduled_end = card.get("data-end-date-utc")
        auction_date = exact_date(scheduled_end) or exact_date(time_node.get("datetime") if time_node else None)
        address = clean(address_node.get_text(" ", strip=True)) if address_node else None
        card_text = clean(card.get_text(" ", strip=True)) or ""
        committed_offer = bool(
            re.search(
                r"\b(?:property\s+)?for sale (?:by|via) committed offer\b",
                card_text,
                re.I,
            )
            or (
                re.search(r"\bcommitted offer\b", card_text, re.I)
                and re.search(r"\bonline sale\b", card_text, re.I)
            )
        )
        if committed_offer or (not detail and property_detail):
            non_auction_link = property_detail or detail
            excluded_non_auction.append({
                "position": position,
                "address": address,
                "detail_url": urljoin(source["base"], non_auction_link.get("href") or ""),
                "source_lot_id": identity.group(1).lower() if identity else None,
                "reason": "first-party property/committed-offer card, not an auction lot",
            })
            continue
        if not all((identity, address, auction_date)):
            malformed.append({"position": position, "address": address, "detail_url": detail.get("href") if detail else None})
            continue
        source_lot_id = identity.group(1).lower()
        original_url = urljoin(source["base"], detail.get("href") or "")
        result_node = card.select_one(".list-guideprice")
        if result_node is None:
            result_node = next(
                (
                    node
                    for node in card.select(".lot-info li")
                    if clean((node.select_one(".primary-text") or node).get_text(" ", strip=True))
                    == "Price"
                ),
                None,
            )
        result_text = clean(result_node.get_text(" ", strip=True)) if result_node else None
        status, sale_price = status_and_price(result_text)
        tagline_node = card.select_one(".lot-data-heading strong")
        summary_node = card.select_one(".list-info p")
        tagline = clean(tagline_node.get_text(" ", strip=True)) if tagline_node else None
        summary = clean(summary_node.get_text(" ", strip=True)) if summary_node else None
        description = clean(" ".join(dict.fromkeys(filter(None, [tagline, summary]))))
        image = card.select_one("img.list-image[src], img.grid-img[src]")
        postcode = corpus.PC.search(address)
        auction_id = f"{source['slug']}:{auction_date}"
        row = corpus.base_row(
            source["auctioneer"], auction_id, auction_date, None, source_lot_id, original_url
        )
        row.update(
            appearance_id=f"{source['auctioneer']}|eig-lot:{source_lot_id}",
            address=address,
            postcode=postcode.group().upper() if postcode else None,
            locality=address,
            sale_price=sale_price,
            status=status,
            description=description,
            sector=classify_sector(address, description),
            image_urls=[image.get("src")] if image and image.get("src") else [],
            property_id=source_lot_id,
            identity_method="first_party_published_eig_lot_id",
            record_quality="address_record",
            source_position=position,
            source_result_text=result_text,
            source_platform_lot_id=card.get("data-lot-id"),
            scheduled_auction_end=scheduled_end,
            published_outcome_time=time_node.get("datetime") if time_node else None,
            auction_date_basis=(
                "published scheduled auction end date" if scheduled_end
                else "published individual lot outcome/end date"
            ),
            source_evidence=evidence,
        )
        opening_match = re.search(
            r"Minimum Opening Bid:\s*£\s*([\d,]+(?:\.\d+)?)\s*([MK])?",
            result_text or "", re.I,
        )
        current_match = re.search(
            r"Current Bid:\s*£\s*([\d,]+(?:\.\d+)?)\s*([MK])?",
            result_text or "", re.I,
        )
        row["minimum_opening_bid"] = amount(opening_match)
        row["current_bid"] = amount(current_match)
        bid_match = re.search(r"\b(\d+)\s+bids?\b", result_text or "", re.I)
        if bid_match:
            row["bid_count"] = int(bid_match.group(1))
        rows.append(row)
    return rows, malformed, excluded_non_auction


def description_after_heading(soup: BeautifulSoup) -> str | None:
    heading = soup.find(["h2", "h3"], string=lambda value: value and clean(value) == "Description")
    if not heading:
        return None
    for sibling in heading.next_siblings:
        if isinstance(sibling, Tag):
            if sibling.name in {"h2", "h3"}:
                break
            text = clean(sibling.get_text(" ", strip=True))
            if text:
                return text
    return None


def published_auction_house(soup: BeautifulSoup) -> str | None:
    for link in soup.find_all("a"):
        value = clean(link.get_text(" ", strip=True))
        match = re.fullmatch(r"Auction House\s*/\s*(.+)", value or "", re.I)
        if match:
            branch = clean(match.group(1))
            return f"Auction House {branch}" if branch else None
    return None


def enrich_detail(html: str, row: dict, evidence: dict, source: dict | None = None) -> dict:
    soup = BeautifulSoup(html, "lxml")
    heading = soup.select_one("h1.h3")
    detail_address = clean(heading.get_text(" ", strip=True)) if heading else None
    if detail_address and detail_address.casefold() != clean(row["address"]).casefold():
        card_postcode = corpus.PC.search(row["address"] or "")
        detail_postcode = corpus.PC.search(detail_address)
        if not (card_postcode and detail_postcode and card_postcode.group().casefold() == detail_postcode.group().casefold()):
            raise ValueError("detail address does not reconcile to retained result card")
    meta = soup.select_one('meta[name="description"]') or soup.select_one('meta[property="og:description"]')
    meta_text = meta.get("content") if meta else None
    description = description_after_heading(soup)
    tagline_node = soup.select_one(".lot-details-tagline")
    tagline = clean(tagline_node.get_text(" ", strip=True)) if tagline_node else None
    combined = clean(" ".join(dict.fromkeys(filter(None, [tagline, description, row.get("description")]))))
    guide_match = GUIDE_RE.search(meta_text or "")
    rent_match = RENT_RE.search(combined or "")
    images = []
    for node in soup.select('.carousel-inner img[data-src], .carousel-inner img[src], meta[property="og:image"]'):
        candidate = node.get("data-src") or node.get("src") or node.get("content")
        if candidate and not candidate.startswith("data:") and candidate not in images:
            images.append(candidate)
    row.update(
        guide_price=amount(guide_match),
        guide_price_text=clean(guide_match.group(0)) if guide_match else None,
        description=combined,
        sector=classify_sector(row.get("address"), combined),
        annual_rent=annual_rent(rent_match),
        rent_text=clean(rent_match.group(0)) if rent_match else None,
        image_urls=images or row.get("image_urls") or [],
        detail_source_evidence=evidence,
    )
    if source and source.get("auctioneer_from_detail"):
        auctioneer = published_auction_house(soup)
        if not auctioneer:
            raise ValueError("detail page does not publish its Auction House branch")
        row.update(
            auctioneer=auctioneer,
            appearance_id=f"{auctioneer}|eig-lot:{row['source_lot_id']}",
            source_platform_auctioneer=source["auctioneer"],
            operator_legal_name=source.get("operator_legal_name"),
            operator_company_number=source.get("operator_company_number"),
        )
    return row


def snapshot(raw: bytes, resolved: str, source: dict, name: str, basis: str, **metadata) -> dict:
    sha = corpus.digest(raw)
    path = corpus.DATA / "sources" / source["slug"] / f"{name}-{sha[:16]}.json.gz"
    evidence = {
        "source_url": resolved,
        "retrieved_at": corpus.now(),
        "sha256": sha,
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
        "basis": basis,
        **metadata,
    }
    if not path.exists():
        corpus.save_gzip(path, {"evidence": evidence, "html": raw.decode("utf-8", "replace")})
    return evidence


def existing_global_ids(exclude_slug: str) -> set[str]:
    values = set()
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == exclude_slug:
            continue
        for row in corpus.iter_rows(path):
            value = clean(str(row.get("source_lot_id") or row.get("property_id") or ""))
            if value and LOT_ID_RE.fullmatch("/lot/details/" + value):
                values.add(value.casefold())
    return values


def exact_appearance_key(row: dict) -> tuple[str, str] | None:
    """Return a deliberately strict same-appearance key.

    EIG migrated some Brown&Co lots from numeric IDs to UUIDs.  We only join
    those identities when both the exact published auction date and a
    punctuation-insensitive full address agree.  Ambiguous repeated keys are
    left separate so related legal interests are never collapsed.
    """
    auction_date = clean(row.get("auction_date"))
    address = re.sub(r"[^a-z0-9]+", " ", clean(row.get("address")) or "", flags=re.I).strip().casefold()
    return (auction_date, address) if auction_date and address else None


def existing_global_exact_keys(exclude_slug: str) -> Counter:
    values = Counter()
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == exclude_slug:
            continue
        for row in corpus.iter_rows(path):
            key = exact_appearance_key(row)
            if key:
                values[key] += 1
    return values


def exclude_exact_cross_source_overlaps(
    rows: list[dict], existing_keys: Counter
) -> tuple[list[dict], list[dict]]:
    """Exclude only one-to-one exact date/address platform migrations.

    Repeated source keys are deliberately retained because separate flats,
    garages or other legal interests can share a displayed address and date.
    """
    source_keys = Counter(filter(None, (exact_appearance_key(row) for row in rows)))
    retained, overlaps = [], []
    for row in rows:
        key = exact_appearance_key(row)
        if key and source_keys[key] == 1 and existing_keys[key] >= 1:
            overlaps.append({
                "auction_date": row.get("auction_date"),
                "address": row.get("address"),
                "source_lot_id": row.get("source_lot_id"),
                "original_url": row.get("original_url"),
                "existing_match_count": existing_keys[key],
            })
        else:
            retained.append(row)
    return retained, overlaps


def pagination_reconciles(
    page_rows: list[list[dict]],
    malformed: list[dict],
    excluded_non_auction: list[dict],
    denominator: int | None,
    *,
    unpaginated_event: bool = False,
    expected_visible_cards: int | None = None,
) -> bool:
    ids = [row["source_lot_id"] for rows in page_rows for row in rows]
    page_visible_counts = [
        len(rows) + sum(value["page"] == page for value in excluded_non_auction)
        for page, rows in enumerate(page_rows, start=1)
    ]
    page_shape_complete = (
        len(page_rows) == 1
        if unpaginated_event
        else all(page_visible_counts[page - 1] == 50 for page in range(1, len(page_rows)))
        and page_visible_counts[-1] <= 50
    )
    return bool(
        page_rows and all(page_rows) and not malformed and len(ids) == len(set(ids))
        and page_shape_complete
        and (
            expected_visible_cards is None
            or sum(page_visible_counts) == expected_visible_cards
        )
        and (denominator is None or len(ids) + len(excluded_non_auction) == denominator)
    )


def reconcile_legacy_rolling_rows(
    archive_rows: list[dict], legacy_rows: list[dict]
) -> tuple[list[dict], dict]:
    """Consolidate only unambiguous exact Brown&Co rolling/archive overlaps."""
    keyed = defaultdict(list)
    for row in archive_rows:
        key = exact_appearance_key(row)
        if key:
            keyed[key].append(row)

    exact_overlaps, preserved = [], []
    for legacy in legacy_rows:
        key = exact_appearance_key(legacy)
        matches = keyed.get(key, []) if key else []
        if len(matches) != 1:
            preserved.append(legacy)
            continue
        archive = matches[0]
        evidence = {
            "basis": "first-party rolling result card retained under legacy numeric EIG identity",
            "source_lot_id": legacy.get("source_lot_id"),
            "original_url": legacy.get("original_url"),
            "source_result_text": legacy.get("source_result_text"),
            "status": legacy.get("status"),
            "sale_price": legacy.get("sale_price"),
            "source_evidence": legacy.get("source_evidence"),
        }
        retained = list(archive.get("additional_source_evidence") or [])
        fingerprint = json.dumps(evidence, sort_keys=True, default=str)
        if all(json.dumps(value, sort_keys=True, default=str) != fingerprint for value in retained):
            retained.append(evidence)
        archive["additional_source_evidence"] = retained
        for field in ("sale_price", "status", "source_result_text"):
            if archive.get(field) is None and legacy.get(field) is not None:
                archive[field] = legacy[field]
        exact_overlaps.append({
            "auction_date": legacy.get("auction_date"),
            "address": legacy.get("address"),
            "legacy_source_lot_id": legacy.get("source_lot_id"),
            "archive_source_lot_id": archive.get("source_lot_id"),
        })

    merged = {row["appearance_id"]: row for row in archive_rows}
    merged.update({row["appearance_id"]: row for row in preserved})
    return list(merged.values()), {
        "legacy_rows": len(legacy_rows),
        "exact_overlaps": exact_overlaps,
        "exact_overlap_count": len(exact_overlaps),
        "preserved_distinct_count": len(preserved),
    }


def harvest(slug: str, workers: int = 10) -> dict:
    if slug not in SOURCES:
        raise ValueError(f"unknown retained grid: {slug}")
    source = {"slug": slug, **SOURCES[slug]}
    archive_url = source["base"] + source.get("archive_path", "/past-auctions?lotResultType=All")
    first_raw, first_resolved = get(archive_url)
    first_html = first_raw.decode("utf-8", "replace")
    pages = page_count(first_html)
    fetched = {1: (first_raw, first_resolved)}
    with ThreadPoolExecutor(max_workers=min(workers, pages)) as pool:
        futures = {
            pool.submit(get, archive_url + ("&" if "?" in archive_url else "?") + f"page={page}"): page
            for page in range(2, pages + 1)
        }
        for future in as_completed(futures):
            fetched[futures[future]] = future.result()

    archive_evidence, page_rows, malformed, excluded_non_auction = [], [], [], []
    for page in range(1, pages + 1):
        raw, resolved = fetched[page]
        evidence = snapshot(
            raw, resolved, source, f"past-auctions-page-{page}",
            "first-party retained EIG white-label past-auction grid", page=page, page_count=pages,
        )
        archive_evidence.append(evidence)
        rows, bad, excluded = parse_grid(raw.decode("utf-8", "replace"), source, evidence)
        page_rows.append(rows)
        malformed.extend({"page": page, **value} for value in bad)
        excluded_non_auction.extend({"page": page, **value} for value in excluded)

    rows = [row for page in page_rows for row in page]
    ids = [row["source_lot_id"] for row in rows]
    denominator = published_denominator(first_html)
    page_visible_counts = [
        len(page_rows[page - 1])
        + sum(value["page"] == page for value in excluded_non_auction)
        for page in range(1, pages + 1)
    ]
    pagination_complete = pagination_reconciles(
        page_rows,
        malformed,
        excluded_non_auction,
        denominator,
        unpaginated_event=source.get("unpaginated_event", False),
        expected_visible_cards=source.get("expected_visible_cards"),
    )
    visible_inventory_reconciled = bool(
        not pagination_complete
        and source.get("allow_expected_visible_card_mismatch")
        and pagination_reconciles(
            page_rows,
            malformed,
            excluded_non_auction,
            denominator,
            unpaginated_event=source.get("unpaginated_event", False),
        )
    )
    if not pagination_complete and not visible_inventory_reconciled:
        raise RuntimeError(
            f"{slug} retained pagination did not reconcile: pages={list(map(len, page_rows))}, "
            f"malformed={len(malformed)}, distinct={len(set(ids))}/{len(ids)}, "
            f"excluded_non_auction={len(excluded_non_auction)}, published_denominator={denominator}"
            f", expected_visible_cards={source.get('expected_visible_cards')}"
        )

    summary_path = corpus.DATA / f"{slug.replace('-', '_')}_collection.json"
    legacy_path = corpus.DATA / "appearances" / slug / "results.jsonl.gz"
    prior = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    archive_sha = corpus.digest("".join(value["sha256"] for value in archive_evidence).encode())
    if (prior.get("archive_sha256") == archive_sha
            and prior.get("archive_pagination_complete") is True
            and prior.get("parser_version") == PARSER_VERSION
            and not prior.get("detail_recovery_failures")
            and not (slug == "brown-co" and legacy_path.exists())):
        checked = datetime.fromisoformat(prior["checked_at"])
        if 0 <= (datetime.now(timezone.utc) - checked).total_seconds() < 86400:
            print(json.dumps({"source": slug, "skipped": "complete unchanged grid checked within 24 hours"}))
            return prior

    detail_results, detail_failures = {}, []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                get,
                row["original_url"],
                attempts=source.get("detail_attempts", 5),
                timeout=source.get("detail_timeout", 120),
            ): row
            for row in rows
        }
        for future in as_completed(futures):
            row = futures[future]
            try:
                raw, resolved = future.result()
                evidence = snapshot(
                    raw, resolved, source, f"lot-{row['source_lot_id']}",
                    "first-party retained EIG property detail page",
                    source_lot_id=row["source_lot_id"],
                )
                detail_results[row["appearance_id"]] = enrich_detail(
                    raw.decode("utf-8", "replace"), row, evidence, source
                )
            except Exception as exc:
                detail_failures.append({
                    "source_lot_id": row["source_lot_id"], "url": row["original_url"],
                    "error": f"{type(exc).__name__}: {exc}",
                })
                detail_results[row["appearance_id"]] = row
    if (
        source.get("auctioneer_from_detail")
        and detail_failures
        and not source.get("allow_incomplete_detail_recovery")
    ):
        raise RuntimeError(
            f"{slug} branch attribution incomplete: {len(detail_failures)} detail pages failed"
        )
    rows = [detail_results[row["appearance_id"]] for row in rows]

    global_ids = existing_global_ids(slug)
    id_overlaps = [row for row in rows if row["source_lot_id"] in global_ids]
    admissible = [row for row in rows if row["source_lot_id"] not in global_ids]
    exact_overlaps = []
    if source.get("exclude_exact_cross_source_overlaps"):
        admissible, exact_overlaps = exclude_exact_cross_source_overlaps(
            admissible, existing_global_exact_keys(slug)
        )
    appearance_path = corpus.DATA / "appearances" / slug / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(appearance_path)) if appearance_path.exists() else []
    legacy = list(corpus.iter_rows(legacy_path)) if slug == "brown-co" and legacy_path.exists() else []
    legacy_ids = {row["appearance_id"] for row in legacy}
    existing_archive = [row for row in existing if row["appearance_id"] not in legacy_ids]
    existing_reconciled, _ = reconcile_legacy_rolling_rows(existing_archive, legacy)
    merged = {row["appearance_id"]: row for row in existing_archive}
    merged.update({row["appearance_id"]: row for row in admissible})
    reconciliation = {"legacy_rows": 0, "exact_overlaps": [], "exact_overlap_count": 0, "preserved_distinct_count": 0}
    if legacy:
        reconciled, reconciliation = reconcile_legacy_rolling_rows(list(merged.values()), legacy)
        merged = {row["appearance_id"]: row for row in reconciled}
    corpus.write_rows(f"{slug}/canonical", list(merged.values()), preserve_existing=False)
    persisted = list(corpus.iter_rows(appearance_path))
    if len(persisted) != len(merged) or {row["appearance_id"] for row in persisted} != set(merged):
        raise RuntimeError(f"{slug} canonical reconciliation did not persist exactly")
    if legacy:
        legacy_path.unlink()
    run_new_count = max(0, len(merged) - len(existing_reconciled))

    by_date = defaultdict(list)
    for row in admissible:
        by_date[row["auction_date"]].append(row)
    for auction_date, date_rows in by_date.items():
        corpus.save_json(corpus.DATA / "auctions" / slug / f"{auction_date}.json", {
            "auctioneer": source["auctioneer"],
            "source_auction_id": f"{slug}:{auction_date}",
            "auction_date": auction_date,
            "source_url": first_resolved,
            "catalogue_complete": pagination_complete,
            "source_rows_complete": pagination_complete or visible_inventory_reconciled,
            "pagination_reconciled": pagination_complete or visible_inventory_reconciled,
            "lots_captured": len(date_rows),
            "completion_scope": (
                "all rows for this date in the reconciled retained flat archive; "
                "not evidence of deleted rows or a separate event catalogue"
                if pagination_complete else
                "all internally reconciled visible rows for this date; the source "
                "event advertises more lots than its result inventory and remains incomplete"
            ),
            "source_evidence": archive_evidence,
            "errors": [],
            "checked_at": corpus.now(),
        })

    today_value = date.today()
    today = today_value.isoformat()
    cutoff = date(today_value.year - 20, today_value.month, today_value.day).isoformat()
    years_before = {int(row["auction_date"][:4]) for row in existing_reconciled if row.get("auction_date")}
    years_after = {int(row["auction_date"][:4]) for row in merged.values() if row.get("auction_date")}
    archive_baseline = legacy if legacy else []
    baseline_dates = {int(row["auction_date"][:4]) for row in archive_baseline if row.get("auction_date")}
    all_rows = list(merged.values())
    all_historical = [row for row in all_rows if row.get("auction_date") and cutoff <= row["auction_date"] <= today]
    baseline_historical = [row for row in archive_baseline if row.get("auction_date") and cutoff <= row["auction_date"] <= today]
    summary = {
        "checked_at": corpus.now(),
        "auctioneer": source["auctioneer"],
        "parser_version": PARSER_VERSION,
        "source_url": first_resolved,
        "archive_sha256": archive_sha,
        "archive_page_count": pages,
        "archive_page_rows": [len(value) for value in page_rows],
        "archive_page_visible_cards": page_visible_counts,
        "visible_source_rows": len(rows),
        "expected_visible_cards": source.get("expected_visible_cards"),
        "published_result_count": denominator,
        "distinct_source_identities": len(set(ids)),
        "non_auction_property_cards_excluded": len(excluded_non_auction),
        "non_auction_exclusions": excluded_non_auction,
        "archive_pagination_complete": pagination_complete,
        "archive_visible_inventory_reconciled": pagination_complete or visible_inventory_reconciled,
        "archive_reconciliation_note": ({
            "kind": "published_event_total_exceeds_visible_result_inventory",
            "expected_event_lots": source.get("expected_visible_cards"),
            "visible_result_rows": len(rows),
            "published_result_count": denominator,
            "missing_result_rows": max(0, (source.get("expected_visible_cards") or 0) - len(rows)),
            "banking_scope": "every internally reconciled visible result card; catalogue remains incomplete",
        } if visible_inventory_reconciled else None),
        "appearances_captured": len(merged),
        "run_new_appearances": run_new_count,
        "run_new_address_records": max(0, sum(bool(row.get("address")) for row in all_rows) - sum(bool(row.get("address")) for row in existing_reconciled)),
        "run_new_partial_lots": max(0, sum(not row.get("address") for row in all_rows) - sum(not row.get("address") for row in existing_reconciled)),
        "run_new_dated_twenty_year_address_records": max(0, sum(bool(row.get("address")) for row in all_historical) - sum(bool(row.get("address")) for row in existing_reconciled if row.get("auction_date") and cutoff <= row["auction_date"] <= today)),
        "run_new_commercial_mixed": max(0, sum(row.get("sector") in {"commercial", "mixed-use"} for row in all_rows) - sum(row.get("sector") in {"commercial", "mixed-use"} for row in existing_reconciled)),
        "run_new_guide_prices": max(0, sum(row.get("guide_price") is not None for row in all_rows) - sum(row.get("guide_price") is not None for row in existing_reconciled)),
        "run_new_sale_prices": max(0, sum(row.get("sale_price") is not None for row in all_rows) - sum(row.get("sale_price") is not None for row in existing_reconciled)),
        "run_new_rents": max(0, sum(row.get("annual_rent") is not None for row in all_rows) - sum(row.get("annual_rent") is not None for row in existing_reconciled)),
        "run_new_undated": max(0, sum(not row.get("auction_date") for row in all_rows) - sum(not row.get("auction_date") for row in existing_reconciled)),
        "run_new_future_dated": max(0, sum((row.get("auction_date") or "") > today for row in all_rows) - sum((row.get("auction_date") or "") > today for row in existing_reconciled)),
        "run_duplicate_source_evidence_excluded": len(id_overlaps) + len(exact_overlaps),
        "duplicate_source_identity_exclusions": len(id_overlaps),
        "exact_date_address_overlap_exclusions": len(exact_overlaps),
        "exact_overlap_reconciliation": exact_overlaps,
        "new_source_years": sorted(years_after - years_before),
        "date_range": summary_date_range(merged.values()),
        "by_status": dict(Counter(row.get("status") or "unknown" for row in merged.values())),
        "by_sector": dict(Counter(row.get("sector") or "unknown" for row in merged.values())),
        "by_attributed_auctioneer": dict(Counter(row.get("auctioneer") or "unknown" for row in merged.values())),
        "detail_pages_captured": len(rows) - len(detail_failures),
        "detail_recovery_complete": not detail_failures,
        "detail_recovery_failures": detail_failures,
        "completion_scope": (
            "every auction-lot card in every page of the surviving first-party grid; "
            "explicit /property/details/ committed-offer cards are reconciled but excluded, "
            "and deleted earlier lots are not claimed"
            + (
                f"; detail enrichment remains partial for {len(detail_failures)} failed pages, "
                "whose unknown guide, rent and branch values remain null"
                if detail_failures else ""
            )
        ),
        "failures": [],
    }
    if any(source.get(key) for key in (
        "operator_legal_name", "historical_trading_names", "merged_firms",
    )):
        summary.update({
            "operator_legal_name": source.get("operator_legal_name"),
            "operator_company_number": source.get("operator_company_number"),
            "historical_trading_names_not_counted_as_auctioneers": source.get(
                "historical_trading_names", []
            ),
            "merged_firms_not_counted_as_auctioneers": source.get("merged_firms", []),
            "partner_agents_not_counted_as_auctioneers": source.get("partner_agents", []),
        })
    if legacy:
        summary.update({
            "legacy_rolling_rows_reconciled": reconciliation["legacy_rows"],
            "legacy_exact_address_date_overlaps_consolidated": reconciliation["exact_overlap_count"],
            "legacy_distinct_appearances_preserved": reconciliation["preserved_distinct_count"],
            "legacy_overlap_reconciliation": reconciliation["exact_overlaps"],
            "archive_net_growth_against_pre_archive_rolling_corpus": len(all_rows) - len(archive_baseline),
            "archive_net_dated_twenty_year_address_growth": sum(bool(row.get("address")) for row in all_historical) - sum(bool(row.get("address")) for row in baseline_historical),
            "archive_net_commercial_mixed_growth": sum(row.get("sector") in {"commercial", "mixed-use"} for row in all_rows) - sum(row.get("sector") in {"commercial", "mixed-use"} for row in archive_baseline),
            "archive_net_guide_price_growth": sum(row.get("guide_price") is not None for row in all_rows) - sum(row.get("guide_price") is not None for row in archive_baseline),
            "archive_net_sale_price_growth": sum(row.get("sale_price") is not None for row in all_rows) - sum(row.get("sale_price") is not None for row in archive_baseline),
            "archive_net_rent_growth": sum(row.get("annual_rent") is not None for row in all_rows) - sum(row.get("annual_rent") is not None for row in archive_baseline),
            "archive_net_future_dated_growth": sum((row.get("auction_date") or "") > today for row in all_rows) - sum((row.get("auction_date") or "") > today for row in archive_baseline),
            "archive_new_source_years": sorted(years_after - baseline_dates),
        })
    corpus.save_json(summary_path, summary)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", choices=["all", *SOURCES], nargs="?", default="all")
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()
    targets = list(SOURCES) if args.source == "all" else [args.source]
    results = [harvest(slug, args.workers) for slug in targets]
    print(json.dumps({"sources": targets, "run_new_appearances": sum(value.get("run_new_appearances", 0) for value in results)}, indent=2))


if __name__ == "__main__":
    main()

