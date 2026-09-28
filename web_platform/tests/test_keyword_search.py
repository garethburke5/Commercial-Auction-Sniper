"""Run the shipped browser matcher against the real Python index producer."""
import json
import subprocess
from pathlib import Path
from web_platform.board import index_row, search_text

MATCHER = Path(__file__).parents[1] / 'static/search.js'


def run_queries(rows, queries):
    script = '''
const fs=require('node:fs');
const search=require(process.argv[1]);
const {rows,queries}=JSON.parse(fs.readFileSync(0,'utf8'));
process.stdout.write(JSON.stringify(queries.map(q=>rows.filter(r=>search.matches(r,q)).map(r=>r.id))));
'''
    result = subprocess.run(['node','-e',script,str(MATCHER)],
        input=json.dumps({'rows':rows,'queries':queries}),text=True,capture_output=True,check=True)
    return json.loads(result.stdout)


def test_tenant_description_type_and_location_are_searchable_together():
    rows = [index_row({'id':'admiral','address':'22 Broadway, Liverpool L11 1BZ',
             'tenant':'Admiral Casino','description':'An amusement arcade investment.',
             'property_type':'Retail','tenure':'Freehold'},'0.json'),
            index_row({'id':'cafe','address':'10 High Street, York YO1 2AB',
             'description':'Café investment next to a pharmacy.',
             'tenancy_schedule':[{'tenant':'Sainsbury’s Local'}]},'0.json'),
            index_row({'id':'unknown','address':'1 Station Road','description':None,
             'tenant':None,'image_url':'https://casino.example/photo.jpg'},'0.json')]
    queries=['Admiral','CASINO','admiral, Liverpool','casino York','amusement arcade','Retail',
             'L11 1BZ','high street','cafe','Sainsburys','Sainsbury’s','pharmacy','', 'None', 'no-such-business']
    assert run_queries(rows,queries)==[['admiral'],['admiral'],['admiral'],[],['admiral'],['admiral'],
             ['admiral'],['cafe'],['cafe'],['cafe'],['cafe'],['cafe'],['admiral','cafe','unknown'],[],[]]


def test_index_keeps_late_description_terms_and_omits_non_evidence():
    row={'id':'long','address':'21 King’s Road, AB1 2CD','tenant':None,
         'description':'Retail investment. '*500+'Former casino with rear parking.',
         'nearby_occupiers':['Boots','M&S'], 'interpretation':['Hypothetical supermarket'],
         'image_url':'https://example.org/tobacconist.jpg'}
    text=search_text(row)
    assert text.split().count('retail')==1
    indexed=index_row(row,'0.json')
    assert run_queries([indexed],['casino parking','Kings Road','Boots','M&S','supermarket','tobacconist'])==[
        ['long'],['long'],['long'],['long'],[],[]]
    assert indexed['chunk']=='0.json' and 'search_text' in indexed


def test_address_fallback_and_punctuation_do_not_break_existing_searches():
    assert run_queries([{'id':'legacy','address':'106 High Street, Redcar TS10 3DL'}],
        ['Redcar','TS10; 3DL','106 HIGH STREET','London'])==[['legacy'],['legacy'],['legacy'],[]]


def test_search_index_schema_change_invalidates_cached_catalogues(monkeypatch):
    from web_platform import site as module
    class EmptyCatalogue:
        properties=[]
        sources={}
    current=module.Site(EmptyCatalogue())
    monkeypatch.setattr(module,'SEARCH_INDEX_VERSION',1)
    old=module.Site(EmptyCatalogue())
    assert current.board_version!=old.board_version
