from pathlib import Path

p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=s.replace('BUILD = "V6.68-LIGHT-MODE"','BUILD = "V6.69-ACUITUS-STRUCTURED"',1)

start=s.find('@st.cache_data(ttl=21600, show_spinner=False)\ndef _acuitus_current():')
end=s.find('\n# ---------------- live refresh (non-blocking until user asks) ----------------',start)
if start==-1 or end==-1:
    raise SystemExit('Acuitus current collector block not found')

replacement=r'''@st.cache_data(ttl=21600, show_spinner=False)
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
            low=text.lower()
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

            # Preserve multiple EPCs where a lot contains more than one demise.
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

            # Read Acuitus' tenancy/accommodation tables as tables, not as one
            # flattened string. Prefer an explicit Total row; otherwise sum the
            # component rows where the column semantics are identifiable.
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

            if not total_sqm and accommodation:
                # Acuitus can put multiple sq m figures in one stacked cell. If
                # no Total row was machine-readable, use the published text total.
                tm=re.search(r"\bTotal\b[^0-9]{0,30}([\d,.]+)\s*(?:sq\.?\s*m|sqm|m²)",text,re.I)
                if tm:total_sqm=float(tm.group(1).replace(',',''))
            if total_sqm and not total_sqft:
                total_sqft=round(total_sqm*10.7639)
            if total_sqft and not total_sqm:
                total_sqm=round(total_sqft/10.7639,2)

            facts=extract_particulars(raw,"Acuitus",href)
            row=dict(source="Acuitus",lot=lot,date="2026-09-17",address=address,
                     guide=guide,rent=rent,tenure=tenure,vat=vat,url=href,
                     desc=text[:3500],image=_property_image_from_soup(ds,href),
                     epc=epc,area_sqm=total_sqm,area_sqft=total_sqft,
                     accommodation_summary=" | ".join(accommodation[:8]) or None)
            row=merge_enrichment(row,facts)
            # Source-specific exact-page values outrank generic first-match area/EPC.
            if epc:row["epc"]=epc
            if total_sqm:row["area_sqm"]=total_sqm
            if total_sqft:row["area_sqft"]=total_sqft
            if accommodation:row["accommodation_summary"]=" | ".join(accommodation[:8])
            if guide is not None:row["guide"]=guide
            if rent is not None:row["rent"]=rent
            if vat!="UNKNOWN":row["vat"]=vat
            return row
        except Exception:
            return None

    try:
        soup=BeautifulSoup(fetch(listing),"lxml")
        links=[];cards={}
        for a in soup.find_all("a",href=True):
            href=urljoin(listing,a["href"])
            if not re.search(r"acuitus\.co\.uk/property/\d+/?",href,re.I):continue
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
'''

s=s[:start]+replacement+s[end:]

# Surface the accommodation breakdown in Investment Details when captured.
needle='''        ("Rateable value",money_fmt(p.get("rateable_value"))) if p.get("rateable_value") else None,\n        ("Repairing basis","FRI") if p.get("fri") else None,\n'''
if needle in s:
    repl='''        ("Rateable value",money_fmt(p.get("rateable_value"))) if p.get("rateable_value") else None,\n        ("Accommodation",str(p.get("accommodation_summary"))) if p.get("accommodation_summary") else None,\n        ("Repairing basis","FRI") if p.get("fri") else None,\n'''
    s=s.replace(needle,repl,1)

p.write_text(s,encoding='utf-8')
