from pathlib import Path
import py_compile

p=Path('app.py')
c=p.read_text(encoding='utf-8')

# Correct the three abbreviated seed addresses using current BTG particulars.
c=c.replace("address='Grand Hotel, Radcliffe, Greater Manchester'","address='The Grand Hotel, 13 Market Street, Radcliffe, Manchester, Lancashire M26 1GF'",1)
c=c.replace("address='15-23 Percy Street, Stoke-On-Trent, Staffordshire'","address='15 - 23 Percy Street, Stoke-On-Trent, Staffordshire ST1 1NA'",1)
c=c.replace("address='Unit 4, Bansons Yard, Ongar, Essex'","address='Unit 4, Bansons Yard, High Street, Ongar, Essex CM5 9AA'",1)

# Percy Street exact link is independently verified; storing it means the card is useful
# even if catalogue discovery changes later.
c=c.replace("url='https://www.btgeddisonspropertyauctions.com/auctions/live-stream/august-2026?auction_id=17', desc='Commercial Property.'","url='https://www.btgeddisonspropertyauctions.com/properties/202607231641sq_tkoe-300926/for-auction-stoke-on-trent', desc='Commercial Property.'",1)

old='''        wanted=[]
        for lot,address in targets:
            addr=norm(address).lower()
            best=None
            for a in s.find_all("a",href=True):
                href=urljoin(catalogue,a["href"])
                if "/properties/" not in href:
                    continue
                label=norm(a.get_text(" ",strip=True)).lower()
                if label and (label==addr or label in addr or addr in label):
                    best=href
                    break
            if best:
                wanted.append((lot,best))
'''
new='''        # Cache exact lot links and labels once, then match each seed robustly.
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
'''
assert old in c, 'Pugh matcher anchor changed'
c=c.replace(old,new,1)
c=c.replace('BUILD = "V6.21-BTG-BOOT"','BUILD = "V6.22-BTG-19OF19"',1)
p.write_text(c,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
assert 'best_score>=0.55' in c
assert 'The Grand Hotel, 13 Market Street' in c
assert 'Unit 4, Bansons Yard, High Street' in c
print('Robust Pugh/BTG address-to-exact-page matcher patch passed')
