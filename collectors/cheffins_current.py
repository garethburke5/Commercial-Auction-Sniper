"""Cheffins timed/CPN and linked current rostrum catalogue adapter.

Each feed keeps separate reconciliation evidence. Neither is an authoritative
replacement scope. Past results never imply availability.
"""
import re
from datetime import date, datetime
from urllib.parse import urljoin, urlsplit, urlunsplit

from .core import Lot, SourceResult, norm, parse_tenure, parse_rent, parse_vat
from .current_property_catalogues import fetch, lifecycle
from .financials import guide_range
from .publication_quality import commercial_decision
from .utils import enrich_common_fields

SOURCE = 'Cheffins'
SEARCH = 'https://timedpropertyauctions.cheffins.co.uk/search'
HOSTS = {'timedpropertyauctions.cheffins.co.uk', 'auctions.thecpn.co.uk'}
LOT_PATH = re.compile(r'^/lot/details/[a-f0-9-]+/?$', re.I)


def lot_url(raw, base=SEARCH):
    p = urlsplit(urljoin(base, raw))
    if p.scheme != 'https' or p.hostname not in HOSTS or not LOT_PATH.fullmatch(p.path):
        return None
    return urlunsplit(('https', p.netloc, p.path.rstrip('/'), '', ''))


def cards(page):
    result = {}
    for card in page.select('.list-panel'):
        anchors = [a for a in card.select('a[href]') if lot_url(a['href'])]
        if not anchors:
            continue
        urls = {lot_url(a['href']) for a in anchors}
        if len(urls) != 1:
            raise ValueError('Ambiguous timed-auction card')
        text = norm(card.get_text(' ', strip=True))
        match = re.search(r'(?:End Time|Auction Ended)\s*-\s*(\d{2}/\d{2}/\d{4})', text, re.I)
        if not match:
            raise ValueError('Timed lot has no auction date')
        day = datetime.strptime(match[1], '%d/%m/%Y').date().isoformat()
        result[urls.pop()] = {'text': text, 'day': day}
    return result


def sections(page):
    result = {}
    for heading in page.select('h3.lot-details-heading'):
        label = norm(heading.text)
        content = []
        for sibling in heading.find_next_siblings():
            if sibling.name in ('h2', 'h3', 'h4') or sibling.select_one('h3.lot-details-heading'):
                break
            # Exact field siblings; never include the bidding help/footer.
            if sibling.name not in ('p', 'table', 'ul', 'ol') and not (sibling.name == 'div' and 'table-responsive' in sibling.get('class', [])):
                break
            content.append(norm(sibling.get_text(' ', strip=True)))
        if content:
            result[label] = ' '.join(content)
    return result


def detail(url, seed, page):
    heading = page.find('h1')
    fields = sections(page)
    if not heading or len(fields.get('Description', '')) < 40:
        raise ValueError('Missing address or readable property particulars')
    address = norm(heading.text)
    # Use factual property sections, excluding buyer-fee boilerplate/contact data.
    text = '\n'.join(k + ': ' + v for k, v in sorted(fields.items(), key=lambda kv: kv[0]=='Location')
                     if k.lower() not in {"auctioneer's note", 'viewing', 'legal packs'})
    low, high, price = guide_range(seed['text'])
    image = page.select_one('img[alt="Lot Image"][data-src], img[alt="Lot Image"][src]')
    images = list(dict.fromkeys(urljoin(url, i.get('data-src') or i.get('src'))
                  for i in page.select('img[alt="Lot Image"]') if i.get('data-src') or i.get('src')))
    legal = next((a for a in page.select('a[href]') if '/lot/legals/' in a['href']), None)
    number = re.search(r'\bLot\s+(\d+[A-Z]?)\b', seed['text'], re.I)
    lot = Lot(SOURCE, url, address, auction_date=seed['day'],
              auction_id='cheffins-timed:'+seed['day'],
              lot_number='Lot '+number[1] if number else None,
              description=text, guide_price=low, guide_price_upper=high, guide_price_text=price,
              annual_rent=parse_rent(fields.get('Description', '')),
              tenure=parse_tenure(fields.get('Tenure', '')), vat_status=parse_vat(fields.get('VAT', '')),
              image_url=images[0] if images else None, image_is_primary=bool(image), image_source_url=url,
              status=lifecycle(seed['text']),
              legal_pack_url=urljoin(url, legal['href']) if legal else None,
              legal_pack_status='LOGIN REQUIRED' if legal else 'UNKNOWN')
    enrich_common_fields(lot, text)
    # A business-rates assessment identifies the actual club premises, not a nearby venue.
    if re.search(r'club and premises assessment', fields.get('Outgoings', ''), re.I):
        lot.property_type = 'Leisure / Social club'
    # Preserve exact table totals; do not mistake rates payable for rental income.
    table = re.search(r'Total Floor Area\s+([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)', fields.get('Accommodation', ''))
    if table:
        lot.area_sqft, lot.area_sqm = (float(v.replace(',', '')) for v in table.groups())
    lot.annual_rent = parse_rent(fields.get('Description', ''))
    lot.vat_status = parse_vat(fields.get('VAT', ''))
    return lot.finalise()


def collect_cheffins(fetcher=None, today=None, include_rostrum=True):
    fetcher = fetcher or fetch
    today = today or date.today()
    targets = {}; seen = set(); pending = [SEARCH]; errors = []; totals = []
    try:
        while pending:
            url = pending.pop(0)
            if url in seen: continue
            if len(seen) >= 30: raise ValueError('Catalogue pagination safety limit')
            seen.add(url)
            page = fetcher(url)
            total = re.search(r'Showing results [\d,]+\s*[-–]\s*[\d,]+ of ([\d,]+)', norm(page.get_text(' ',strip=True)), re.I)
            if total: totals.append(int(total[1].replace(',', '')))
            targets.update(cards(page))
            for a in page.select('.pagination a[href]'):
                target = urljoin(url, a['href']); p = urlsplit(target)
                if p.scheme=='https' and p.hostname=='timedpropertyauctions.cheffins.co.uk' and p.path.rstrip('/')=='/search' and target not in seen and target not in pending:
                    pending.append(target)
        if not totals or len(set(totals))!=1 or len(targets)!=totals[0]:
            errors.append('Published catalogue denominator does not match discovered lots')
    except Exception as exc:
        errors.append(type(exc).__name__+': '+str(exc))
    lots=[]; outcomes=[]; past=0; parsed=0; excluded=0
    for url, seed in targets.items():
        # Retain explicit withdrawn lots even after the auction; other past results
        # are counted, not reclassified as presently available.
        if seed['day'] < today.isoformat() and lifecycle(seed['text'])!='WITHDRAWN':
            past+=1; continue
        try:
            lot=detail(url,seed,fetcher(url)); parsed+=1
            if commercial_decision(lot.to_dict()) is True:
                lots.append(lot); outcomes.append({'url':url,'outcome':'commercial/mixed-use'})
            else:
                excluded+=1; outcomes.append({'url':url,'outcome':'no verified commercial use'})
        except Exception as exc:
            errors.append(url+': '+type(exc).__name__);outcomes.append({'url':url,'outcome':'detail failure'})
    complete=not errors
    telemetry={'scope':'Cheffins timed/CPN catalogue only; rostrum catalogue remains separately unverified',
        'current_catalogue_detected':any(s['day']>=today.isoformat() for s in targets.values()),
        'source_lot_count':len(targets)-past if totals else None,
        'catalogue_total_lots':totals[0] if totals else None,'discovered_lot_urls':len(targets),
        'detail_pages_inspected':parsed,'past_auction_exclusions':past,'classification_rejections':excluded,
        'commercial_mixed_candidates':len(lots),'catalogue_complete':complete,
        'discovery_failures':errors,'lot_outcomes':outcomes,'catalogue_pages':sorted(seen)}
    result = SourceResult(SOURCE,'LIVE' if complete else 'DEGRADED',lots,
        f'Timed catalogue: {len(targets)} discovered, {past} past results, {parsed} details checked, {len(lots)} commercial/mixed-use. '+ '; '.join(errors),
        # The timed feed cannot retire rows from the separate rostrum catalogue.
        authoritative_snapshot=False, expected_count=len(lots) if complete else None,
        discovered_count=len(targets), scope_dates=tuple(sorted({l.auction_date for l in lots})),reconciliation=telemetry)
    if include_rostrum:
        from .cheffins_rostrum import collect_rostrum
        rostrum, evidence = collect_rostrum(fetcher,today)
        result.lots.extend(rostrum)
        result.reconciliation['timed_catalogue'] = dict(telemetry)
        result.reconciliation['rostrum_catalogue'] = evidence
        result.reconciliation['scope'] = 'Timed/CPN feed and linked current rostrum catalogue; no archive traversal'
        result.reconciliation['catalogue_complete'] = complete and evidence['catalogue_complete']
        result.reconciliation['current_catalogue_detected'] |= evidence['current_catalogue_detected']
        from board_presentation import current_board_row
        result.reconciliation['total_commercial_mixed_candidates'] = len(result.lots)
        result.reconciliation['commercial_mixed_candidates'] = sum(current_board_row(l.to_dict(),today) for l in result.lots)
        # Rostrum cards contain full descriptions; residential cards can be
        # classified without fetching their detail pages. Keep both counts.
        result.reconciliation['lots_parsed'] = parsed + evidence['discovered_lot_urls'] if evidence['catalogue_complete'] else parsed + evidence['detail_pages_inspected']
        for key in ('discovered_lot_urls','detail_pages_inspected','classification_rejections'):
            result.reconciliation[key] += evidence[key]
        for key in ('source_lot_count','catalogue_total_lots'):
            previous=result.reconciliation[key]
            result.reconciliation[key]=(previous+evidence['catalogue_total_lots']) if previous is not None and evidence['catalogue_total_lots'] is not None else None
        result.reconciliation['discovery_failures'] = errors + evidence['discovery_failures']
        result.discovered_count += evidence['discovered_lot_urls']
        result.expected_count = len(result.lots) if result.reconciliation['catalogue_complete'] else None
        result.scope_dates = tuple(sorted({l.auction_date for l in result.lots}))
        if not evidence['catalogue_complete']:result.status='DEGRADED'
        result.message += f" Rostrum: {evidence['discovered_lot_urls']} cards, {len(rostrum)} commercial/mixed-use; complete={evidence['catalogue_complete']}."
        # Scope-specific retirement is not yet supported; neither feed can erase
        # the other's previously banked records during a source outage.
    return result
