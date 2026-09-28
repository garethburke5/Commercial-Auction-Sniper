import json
import subprocess
from pathlib import Path
from bs4 import BeautifulSoup
from web_platform.glossary import GROUPS


def test_shipped_numeric_filters_exclude_unknowns_at_explicit_boundaries():
    script = r'''
const assert=require('node:assert/strict');
const {numericMatches:match}=require(process.argv[1]);
for(const unknown of [null,undefined,NaN,Infinity,-Infinity,'Not stated','10',0,-1]){
  assert.equal(match({giy:unknown},{yield:10,unknown:true}),false);
  assert.equal(match({guide_price:unknown},{min:100000,unknown:true}),false);
  assert.equal(match({guide_price:unknown},{max:200000,unknown:true}),false);
}
for(const [giy,expected] of [[15,true],[10,true],[9.9,false]])
  assert.equal(match({giy},{yield:10}),expected);
assert.equal(match({guide_price:100000,giy:10},{min:100000,max:100000,yield:10}),true);
assert.equal(match({guide_price:99999,giy:15},{min:100000}),false);
assert.equal(match({guide_price:200001,giy:15},{max:200000}),false);
assert.equal(match({guide_price:150000,giy:null},{min:100000,max:200000}),true);
assert.equal(match({guide_price:null,giy:null},{}),true);
assert.equal(match({guide_price:150000,giy:9.9},{min:100000,max:200000,yield:10}),false);
assert.equal(match({giy:10,giy_min:9.9},{yield:10}),false);
assert.equal(match({giy:15,giy_min:10},{yield:10}),true);
assert.equal(match({giy:15,giy_min:null},{yield:10}),false);
'''
    subprocess.run(['node','-e',script,str(Path(__file__).parents[1]/'static/search.js')],check=True)


def test_yield_range_qualifies_at_the_highest_guide():
    from web_platform.board import enrich_board_row,index_row
    row=enrich_board_row({'address':'Test shop','annual_rent':10000,'guide_price':100000,'guide_price_upper':110000})
    assert row['giy']==10 and 9<row['giy_min']<10
    assert index_row(row,'x')['giy_min']==row['giy_min']


def test_glossary_has_required_terms_and_stable_unique_links():
    ids=[key for _,_,terms in GROUPS for key,_,_ in terms]
    assert len(ids)==len(set(ids))
    assert {'giy','erv','fri','iri','historic-rent','togc','auction-deposit','sold-prior','stp'}<=set(ids)
    for _,_,terms in GROUPS:
        for key,title,definition in terms:
            assert len(definition)>90 and title and ' ' not in key


def test_rendered_glossary_is_indexable_and_linked(tmp_path):
    from web_platform.site import Site
    from web_platform.glossary import SOURCES,REVIEWED
    from web_platform.catalogue import Catalogue
    (tmp_path/'data/auction_history').mkdir(parents=True)
    (tmp_path/'data/properties.json').write_text(json.dumps({'properties':[],'generated_at':'2026-09-28'}))
    (tmp_path/'data/auction_history/progress.json').write_text(json.dumps({'by_sector':{'commercial':0,'mixed-use':0}}))
    site=Site(Catalogue(tmp_path),origin='https://example.test/sniper')
    html=site.page('/glossary/','Glossary of property auction terms','glossary','Definitions',
        glossary=GROUPS,glossary_sources=SOURCES,glossary_reviewed=REVIEWED)
    doc=BeautifulSoup(html,'html.parser')
    assert doc.select_one('link[rel=canonical]')['href']=='https://example.test/sniper/glossary/'
    assert not doc.select_one('meta[name=robots]')
    assert doc.select_one('nav[aria-label=Footer] a[href="/sniper/glossary/"]')
    schema=json.loads(doc.select_one('script[type="application/ld+json"]').text)
    assert schema[0]['@type']=='DefinedTermSet' and len(schema[0]['hasDefinedTerm'])==len(doc.select('.glossary-term'))
    assert '/glossary/' in site.sitemap(['/glossary/'])
