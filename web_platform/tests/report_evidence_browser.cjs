/* Authenticated evidence UI checks. Run with Playwright installed and Chromium. */
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert/strict'),path=require('path');
process.chdir(path.resolve(__dirname,'../..'));
const script=fs.readFileSync('web_platform/static/report-evidence.js','utf8');
const html=`<body><p id="review-signin"><a href="/account/">Sign in</a></p><div id="acquisition-result"><a href="/due-diligence/?review=saved&evidence=source" data-evidence-id="source">View evidence</a></div><section id="supporting-evidence" hidden><h2>Supporting evidence</h2><button id="show-report-evidence">Browse supporting evidence</button><p id="evidence-status"></p><div id="evidence-list"></div><div id="evidence-detail" tabindex="-1"></div></section></body>`;
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined,args:['--no-sandbox','--disable-dev-shm-usage']});
 for(const width of [390,1440]){
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('https://preview.example/**',r=>r.fulfill({contentType:'text/html',body:html}));
  await page.goto('https://preview.example/due-diligence/?review=saved&evidence=source');
  await page.addScriptTag({content:`window.authenticated=true;window.calls=[];window.AuctionWorkspace={signedIn:()=>authenticated,api:async path=>{calls.push(path);if(window.delayed)return new Promise(resolve=>window.release=resolve);return {label:'Commercial lease',document:'lease.pdf',private:true,pages:[{number:30,extracts:['<img src=x onerror=alert(1)>'],segments:[{text:'Context ',highlighted:false},{text:'Exact clause',highlighted:true}],view_kind:'retained_page_text',ocr:true}]};}};`});
  await page.addScriptTag({content:script});
  assert.match(await page.locator('#review-signin a').getAttribute('href'),/return_review=saved&return_evidence=source/);
  await page.evaluate(()=>dispatchEvent(new CustomEvent('auction-report-loaded',{detail:{id:'saved',available:true}})));
  await page.waitForFunction(()=>document.querySelector('#evidence-detail mark'));
  assert.equal(await page.locator('#evidence-detail mark').textContent(),'Exact clause');
  assert.equal(await page.locator('#evidence-detail img').count(),0);
  assert.match(await page.locator('#evidence-detail').textContent(),/not an image of the original/);
  assert.match(await page.locator('#evidence-detail').textContent(),/OCR/);
  await page.evaluate(()=>{window.delayed=true;document.querySelector('[data-evidence-id]').click()});
  await page.waitForFunction(()=>!!window.release);
  await page.evaluate(()=>{window.authenticated=false;dispatchEvent(new Event('auction-auth-change'));window.release({label:'STALE PRIVATE DATA',private:true,pages:[]});});
  await page.waitForTimeout(30);
  assert.equal(await page.locator('#evidence-detail').textContent(),'');assert(await page.locator('#supporting-evidence').isHidden());
  assert.deepEqual(errors,[]);await page.close();console.log(width+'px: deep link, exact highlight, escaped text and logout race passed');
 }
 // Same-browser email return, explicit account return, recovery guard and no open redirect.
 const context=await browser.newContext(),page=await context.newPage();
 await page.route('https://preview.example/**',r=>r.fulfill({contentType:'text/html',body:'<body></body>'}));
 await page.goto('https://preview.example/account/?return_review=saved&return_evidence=source');
 await page.addScriptTag({content:'window.allowed=false;window.AuctionWorkspace={canReturnToReport:()=>allowed};'});
 await page.addScriptTag({content:script});
 assert.match(page.url(),/account/);assert(await page.evaluate(()=>!!localStorage.getItem('auction-evidence-return')));
 await page.evaluate(()=>dispatchEvent(new Event('auction-auth-change')));assert.match(page.url(),/account/);
 await page.goto('https://preview.example/account/');
 await page.addScriptTag({content:'window.AuctionWorkspace={canReturnToReport:()=>true};'});
 await page.addScriptTag({content:script});await page.waitForURL('**/due-diligence/?review=saved&evidence=source#supporting-evidence');
 assert.equal(await page.evaluate(()=>localStorage.getItem('auction-evidence-return')),null);
 await page.goto('https://preview.example/account/?return_review=https%3A%2F%2Fevil.example');
 await page.addScriptTag({content:'window.AuctionWorkspace={canReturnToReport:()=>true};'});await page.addScriptTag({content:script});assert.match(page.url(),/preview.example\/account/);
 console.log('Sign-in continuation, password-recovery guard and invalid redirect rejection passed');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
