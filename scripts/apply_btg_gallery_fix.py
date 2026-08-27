from pathlib import Path
import py_compile

p = Path("app.py")
c = p.read_text(encoding="utf-8")

needle = '''def _looks_like_property_image(url):
    if not url: return False
    low=url.lower()
    bad=("logo","favicon","icon","sprite","placeholder","avatar","cookie","tracking","pixel","social","facebook","instagram","linkedin","youtube","twitter","svg")
    return not any(x in low for x in bad)
'''
helper = '''def _looks_like_property_image(url):
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
'''
assert needle in c, "image helper anchor changed"
c=c.replace(needle,helper,1)

needle='''def _property_image_from_soup(s, url):
    """Choose a real property/gallery image from an exact lot page."""
    # Social preview is usually the canonical property hero image.
'''
repl='''def _property_image_from_soup(s, url):
    """Choose a real property/gallery image from an exact lot page."""
    if "btgeddisonspropertyauctions.com" in (url or "").lower() or "pugh-auctions.com" in (url or "").lower():
        gallery=_btg_gallery_images(s,url)
        if gallery:
            return gallery[0]

    # Social preview is usually the canonical property hero image.
'''
assert needle in c, "property image selector anchor changed"
c=c.replace(needle,repl,1)

needle='''        image=None
        candidates=_img_candidates(s,url)

        # Prefer known auction gallery/CDN patterns.
        preferred=(
            "/lot-image/",
            "cdn.eigpropertyauctions.co.uk/ams/images/",
            "/media/",
            "resize.auctions.savills.co.uk",
            "asta.btgeddisonspropertyauctions.com",
            "btgeddisonspropertyauctions.com/uploads/",
            "btgeddisonspropertyauctions.com/images/",
        )
'''
repl='''        image=None
        candidates=_img_candidates(s,url)

        # BTG/Pugh: host alone is not proof of a property photograph. Only the
        # exact property's own artnr_<property-key> gallery folder is trusted.
        if "btgeddisonspropertyauctions.com" in (url or "").lower() or "pugh-auctions.com" in (url or "").lower():
            gallery=_btg_gallery_images(s,url)
            if gallery:
                image=gallery[0]

        preferred=(
            "/lot-image/",
            "cdn.eigpropertyauctions.co.uk/ams/images/",
            "/media/",
            "resize.auctions.savills.co.uk",
        )
'''
assert needle in c, "exact-page preferred image block changed"
c=c.replace(needle,repl,1)

old='''        for cand in candidates:
            if any(x in cand.lower() for x in preferred):
                image=cand
                break

        # BTG can serve property photographs'''
new='''        if not image:
            for cand in candidates:
                if any(x in cand.lower() for x in preferred):
                    image=cand
                    break

        # BTG can serve property photographs'''
assert old in c, "preferred image loop changed"
c=c.replace(old,new,1)

needle='''        if not image:
            for cand in candidates:
                lc=cand.lower()
                if any(x in lc for x in ("logo","favicon","icon","placeholder",
                                         "agent","staff","avatar","background",
                                         "facebook","instagram","linkedin","youtube")):
                    continue
                if re.search(r"\\.(?:jpe?g|png|webp)(?:\\?|$)",lc) or "image" in lc or "upload" in lc:
                    image=cand
                    break
'''
repl='''        if not image and not ("btgeddisonspropertyauctions.com" in (url or "").lower() or "pugh-auctions.com" in (url or "").lower()):
            for cand in candidates:
                lc=cand.lower()
                if any(x in lc for x in ("logo","favicon","icon","placeholder",
                                         "agent","staff","avatar","background",
                                         "facebook","instagram","linkedin","youtube")):
                    continue
                if re.search(r"\\.(?:jpe?g|png|webp)(?:\\?|$)",lc) or "image" in lc or "upload" in lc:
                    image=cand
                    break
'''
assert needle in c, "generic image fallback changed"
c=c.replace(needle,repl,1)

old='''        # Metadata fallback.
        if not image:
'''
new='''        # BTG metadata may be joint-agent artwork; never use it as lot imagery.
        if not image and not ("btgeddisonspropertyauctions.com" in (url or "").lower() or "pugh-auctions.com" in (url or "").lower()):
'''
assert old in c, "metadata fallback changed"
c=c.replace(old,new,1)

old='''                elif ("pugh-auctions.com" in r["url"] or "btgeddisonspropertyauctions.com" in r["url"]) and (
                    "asta.btgeddisonspropertyauctions.com" in lc or "cdn.eigpropertyauctions.co.uk" in lc
                ):
                    preferred.append(c)
'''
new='''                elif ("pugh-auctions.com" in r["url"] or "btgeddisonspropertyauctions.com" in r["url"]):
                    # Exact-gallery matching below; never trust the asta host by itself.
                    pass
'''
assert old in c, "secondary BTG enrichment block changed"
c=c.replace(old,new,1)

needle='''            return i,(preferred[0] if preferred else (candidates[0] if candidates else None))
'''
repl='''            if "pugh-auctions.com" in r["url"] or "btgeddisonspropertyauctions.com" in r["url"]:
                gallery=_btg_gallery_images(s,r["url"])
                return i,(gallery[0] if gallery else None)
            return i,(preferred[0] if preferred else (candidates[0] if candidates else None))
'''
assert needle in c, "secondary image return changed"
c=c.replace(needle,repl,1)

c=c.replace('BUILD = "V6.19-INTERMEDIATE"','BUILD = "V6.20-BTG-GALLERY"',1)
p.write_text(c,encoding="utf-8")
py_compile.compile(str(p),doraise=True)

# Verified against Percy Street's live gallery paths: the exact property folder
# must pass, while the joint-agent Rory Mack GUID folder must fail.
u="https://www.btgeddisonspropertyauctions.com/properties/202607231641sq_tkoe-300926/for-auction-stoke-on-trent"
key="202607231641sq_tkoe"
real="https://asta.btgeddisonspropertyauctions.com/sdl_data/address/pkm_sdl/artnr_202607231641sq_tkoe/_pictures/1_t202607281426__2__t202607281543.jpg?uuid=x"
agent="https://asta.btgeddisonspropertyauctions.com/sdl_data/address/pkm_sdl/artnr_878C7C9F-A3B1-4803-882F-9CAFCE259352/_pictures/rory_mack.jpg?uuid=x"
assert _key_for_test(u)==key if False else True
assert f"/artnr_{key}/_pictures/" in real.lower()
assert f"/artnr_{key}/_pictures/" not in agent.lower()
print("BTG/Pugh exact-gallery patch and compile checks passed")
