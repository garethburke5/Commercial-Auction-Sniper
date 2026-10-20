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
print(e.get_template('history_preview.html').render(row={'id':'example'},history_preview={'previous_appearances':2,'has_changes':True,'has_comparables':True}))
print('</main></body></html>')
`],{encoding:'utf8'});
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
 for(const width of [390,1440]){
  const page=await browser.newPage({viewport:{width,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('https://preview.example/**',r=>r.fulfill({contentType:r.request().url().endsWith('.json')?'application/json':'text/html',body:r.request().url().endsWith('.json')?'{}':html}));
  await page.goto('https://preview.example/property/example/');
  await page.addScriptTag({content:`window.signed=false;window.AuctionWorkspace={canReturnToReport:()=>window.signed,api:async()=>window.delayed?new Promise(resolve=>window.release=resolve):{html:'<p>Private earlier guide £123,456</p>',access:{expires_at:null}}};`});
  await page.addScriptTag({content:fs.readFileSync('web_platform/static/history.js','utf8')});
  assert.equal(await page.locator('[data-history-buy=property_history] strong').textContent(),'£2.99');
  assert(await page.locator('[data-history-buy=property_history]').isDisabled());
  await page.locator('[data-history-load]').click();assert.match(await page.locator('[data-history-status]').textContent(),/Sign in/);
  await page.evaluate(()=>window.signed=true);await page.locator('[data-history-load]').click();
  await page.waitForFunction(()=>document.querySelector('[data-history-content]').textContent.includes('£123,456'));
  await page.evaluate(()=>{window.signed=false;dispatchEvent(new Event('auction-auth-change'));});
  assert.equal(await page.locator('[data-history-content]').textContent(),'');
  await page.evaluate(()=>{window.signed=true;window.delayed=true;});await page.locator('[data-history-load]').click();
  await page.waitForFunction(()=>!!window.release);
  await page.evaluate(()=>{window.signed=false;dispatchEvent(new Event('auction-auth-change'));window.release({html:'<p>STALE PRIVATE DATA</p>',access:{}});});
  await page.waitForTimeout(30);assert.equal(await page.locator('[data-history-content]').textContent(),'');
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
  fs.mkdirSync('test-artifacts',{recursive:true});await page.screenshot({path:`test-artifacts/history-${width}.png`,fullPage:true});
  console.log(`${width}px: visible pricing, signed-out denial, sign-out clearance, stale-response isolation, no overflow`);await page.close();
 }
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
