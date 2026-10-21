/* Public price preview and account-switch isolation at desktop/mobile sizes. */
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert/strict'),path=require('path'),{execFileSync}=require('child_process');
process.chdir(path.resolve(__dirname,'../..'));
const html=execFileSync(process.env.PYTHON||'python',['-c',`
from jinja2 import Environment,FileSystemLoader,select_autoescape
from web_platform.plans import CATALOGUE
from pathlib import Path
e=Environment(loader=FileSystemLoader('web_platform/templates'),autoescape=select_autoescape())
e.globals.update(plans=CATALOGUE,url=lambda p:p)
print('<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>'+Path('web_platform/static/site.css').read_text()+'</style></head><body><main>')
print(e.get_template('history_preview.html').render(row={'id':'example'},history_preview={'previous_appearances':2,'related_interests':1,'has_changes':True,'has_comparables':True}))
print('</main></body></html>')
`],{encoding:'utf8'});
const relatedHtml=execFileSync(process.env.PYTHON||'python',['-c',`
import json
from pathlib import Path
from jinja2 import Environment,FileSystemLoader,select_autoescape
from web_platform.catalogue import money
from web_platform.site import uk_date
from web_platform.property_relationships import relationship,result_evidence
f=json.loads(Path('web_platform/tests/fixtures/newbury_related_offerings.json').read_text())
a,b=f['previous'],f['current']
r=dict(a,auctioneer=a['source'],original_url=a['url'],result_evidence=result_evidence(a),**relationship(a,b))
e=Environment(loader=FileSystemLoader('web_platform/templates'),autoescape=select_autoescape())
e.globals.update(money=money,uk_date=uk_date)
print(e.get_template('related_interests.html').render(row=b,market={'related_interests':[r]}))
`],{encoding:'utf8'});
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
 for(const width of [390,1440]){
  const page=await browser.newPage({viewport:{width,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('https://preview.example/**',r=>r.fulfill({contentType:r.request().url().endsWith('.json')?'application/json':'text/html',body:r.request().url().endsWith('.json')?'{}':html}));
  await page.goto('https://preview.example/property/example/');
  await page.addScriptTag({content:`window.signed=false;window.calls=[];window.grant={kind:'subscription',expires_at:Math.floor(Date.now()/1000)+3600};window.AuctionWorkspace={canReturnToReport:()=>window.signed,api:async(path)=>{window.calls.push(path);if(path==='/api/history/products')return {purchases_available:true,products:{property_history:{enabled:true},history_day_pass:{enabled:true}}};if(window.deny){const e=Error('Premium history access is required');e.status=403;throw e;}return window.delayed?new Promise(resolve=>window.release=resolve):{html:'<p>Private earlier guide £123,456</p>'+${JSON.stringify(relatedHtml)},access:window.grant};}};`});
  await page.addScriptTag({content:fs.readFileSync('web_platform/static/history.js','utf8')});
  assert.match(await page.locator('[data-history-preview]').textContent(),/Related property interests found/);
  assert.match(await page.locator('[data-history-preview]').textContent(),/not a like-for-like comparison/);
  assert.equal(await page.locator('[data-history-buy=property_history] strong').textContent(),'£2.99');
  assert(await page.locator('[data-history-buy=property_history]').isDisabled());
  await page.locator('[data-history-load]').click();assert.match(await page.locator('[data-history-status]').textContent(),/Sign in/);
  assert.equal(await page.evaluate(()=>window.calls.length),0);
  await page.evaluate(()=>{window.signed=true;dispatchEvent(new Event('auction-auth-change'));});
  await page.waitForFunction(()=>document.querySelector('[data-history-content]').textContent.includes('£123,456'));
  assert.match(await page.locator('[data-history-status]').textContent(),/Included with your membership/);
  assert(!(await page.locator('[data-history-preview]').isVisible()));
  assert.match(await page.locator('[data-history-content]').textContent(),/Related property interests/);
  assert.match(await page.locator('[data-history-content]').textContent(),/£26,700/);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  fs.mkdirSync('test-artifacts',{recursive:true});await page.screenshot({path:`test-artifacts/history-related-${width}.png`,fullPage:true});
  assert.equal(await page.evaluate(()=>window.calls.filter(x=>x==='/api/history/products').length),0);
  // A pass expiring on an open page clears the data and restores the free choices.
  await page.evaluate(()=>{window.grant={kind:'history_day_pass',expires_at:Date.now()/1000+0.4};dispatchEvent(new Event('auction-auth-change'));});
  await page.waitForFunction(()=>document.querySelector('[data-history-status]').textContent.startsWith('History access until'));
  await page.evaluate(()=>window.deny=true);
  await page.waitForFunction(()=>document.querySelector('[data-history-content]').hidden&&!document.querySelector('[data-history-buy=property_history]').disabled);
  await page.evaluate(()=>{window.deny=false;window.signed=false;dispatchEvent(new Event('auction-auth-change'));});
  assert.equal(await page.locator('[data-history-content]').textContent(),'');
  await page.evaluate(()=>{window.signed=true;window.delayed=true;});await page.locator('[data-history-load]').click();
  await page.waitForFunction(()=>!!window.release);
  await page.evaluate(()=>{window.signed=false;dispatchEvent(new Event('auction-auth-change'));window.release({html:'<p>STALE PRIVATE DATA</p>',access:{}});});
  await page.waitForTimeout(30);assert.equal(await page.locator('[data-history-content]').textContent(),'');
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
  fs.mkdirSync('test-artifacts',{recursive:true});await page.screenshot({path:`test-artifacts/history-${width}.png`,fullPage:true});
  // Existing signed-in session on navigation opens history without a click or auth event.
  await page.goto('https://preview.example/property/example/');
  await page.addScriptTag({content:`window.AuctionWorkspace={canReturnToReport:()=>true,api:async()=>({html:'<p>Already signed in</p>',access:{kind:'subscription',expires_at:null}})};`});
  await page.addScriptTag({content:fs.readFileSync('web_platform/static/history.js','utf8')});
  await page.waitForFunction(()=>document.querySelector('[data-history-content]').textContent.includes('Already signed in'));
  assert(!(await page.locator('[data-history-preview]').isVisible()));
  console.log(`${width}px: automatic membership access, no duplicate purchase offer, pass expiry, sign-out and stale-response isolation`);await page.close();
 }
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
