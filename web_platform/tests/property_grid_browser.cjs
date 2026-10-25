/* Verify layout preference against real templates and actual search redraws. */
const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('assert/strict'),{execFileSync}=require('child_process');
process.chdir(path.resolve(__dirname,'../..'));
const fixture=JSON.parse(execFileSync(process.env.PYTHON||'python',['-m','web_platform.tests.render_grid_fixture'],{encoding:'utf8'}));
const columns=page=>page.locator('.cards').first().evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length);
const fits=page=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth && Array.from(document.querySelectorAll('.cards .card')).every(el=>el.scrollWidth<=el.clientWidth));
async function setup(context){
 await context.route('**/*',r=>{
  const u=new URL(r.request().url());
  if(u.hostname==='images.example.com')return r.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="420"><rect width="640" height="420" fill="#dce5e9"/><text x="320" y="210" text-anchor="middle" font-size="30" fill="#526475">Test property image</text></svg>'});
  if(u.pathname==='/properties/')return r.fulfill({contentType:'text/html',body:fixture.html});
  if(u.pathname==='/auction-catalogue/')return r.fulfill({contentType:'text/html',body:fixture.catalogue});
  if(u.pathname.startsWith('/static/')&&fs.existsSync('web_platform'+u.pathname))return r.fulfill({contentType:u.pathname.endsWith('.css')?'text/css':'text/javascript',body:fs.readFileSync('web_platform'+u.pathname)});
  if(fixture.assets[u.pathname])return r.fulfill({contentType:'application/json',body:fixture.assets[u.pathname]});
  return r.fulfill({body:'',contentType:'text/plain'});
 });
}
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
 fs.mkdirSync('test-artifacts',{recursive:true});
 for(const width of [320,390,650,768,1440]){
  const context=await browser.newContext({viewport:{width,height:1050}});await setup(context);
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('https://preview.example/properties/');
  const group=page.getByRole('group',{name:'Property display'}),grid=group.getByRole('button',{name:'Grid',exact:true}),list=group.getByRole('button',{name:'List',exact:true});
  const ids=await page.locator('.cards .card').evaluateAll(cards=>cards.map(c=>c.dataset.id));
  if(width<=650){
   assert.equal(await columns(page),1);assert(await group.isVisible());
   await grid.focus();await page.keyboard.press('Enter');assert.equal(await columns(page),2);
   assert.equal(await grid.getAttribute('aria-pressed'),'true');assert.equal(await list.getAttribute('aria-pressed'),'false');
   assert.deepEqual(await page.locator('.cards .card').evaluateAll(cards=>cards.map(c=>c.dataset.id)),ids);
   assert(await fits(page),`${width}px grid overflow`);
   await page.locator('.investment').first().locator('summary').click();assert(await fits(page),'Expanded details overflow');
   await page.locator('.investment').first().locator('summary').click();
   await page.locator('.board-toolbar').scrollIntoViewIfNeeded();await page.screenshot({path:`test-artifacts/property-grid-${width}.png`});
   await page.reload();assert.equal(await columns(page),2,'Reload loses selected grid');
   await page.locator('#page-size').selectOption('10');await page.waitForFunction(()=>document.querySelectorAll('.cards .card').length===10);
   assert.equal(await columns(page),2,'Result redraw loses grid');
   await page.locator('#board-pager').getByRole('link',{name:'Next ›'}).click();await page.waitForFunction(()=>document.querySelectorAll('.cards .card').length===2);
   assert.equal(await columns(page),2,'Pagination loses grid');
   await page.locator('#property-search').fill('not-a-matching-property');await page.locator('#property-filters button[type=submit]').first().click();await page.getByText('No properties match these filters').waitFor();
   await page.locator('.filter-panel > summary').click();await page.locator('#clear-filters').click();await page.waitForFunction(()=>document.querySelectorAll('.cards .card').length===10);assert.equal(await columns(page),2);
   await page.setViewportSize({width:1440,height:1050});assert(!(await group.isVisible()));assert.equal(await columns(page),4,'Mobile preference changes desktop layout');
   await page.setViewportSize({width,height:1050});assert.equal(await columns(page),2);
   await page.goto('https://preview.example/auction-catalogue/');assert.equal(await columns(page),2,'Catalogue loses preference');
   await page.getByRole('button',{name:'List',exact:true}).click();assert.equal(await columns(page),1);
   await page.reload();assert.equal(await columns(page),1);
  }else{assert(!(await group.isVisible()));assert.equal(await columns(page),width===1440?4:2);}
  assert(await fits(page));assert.deepEqual(errors,[]);await context.close();
  console.log(`${width}px: default, view controls, card access, layout and preference checks passed`);
 }
 const blocked=await browser.newContext({viewport:{width:390,height:900}});await setup(blocked);
 await blocked.addInitScript(()=>{Storage.prototype.getItem=()=>{throw Error('blocked')};Storage.prototype.setItem=()=>{throw Error('blocked')};});
 const p=await blocked.newPage();await p.goto('https://preview.example/properties/');assert.equal(await columns(p),1);await p.getByRole('button',{name:'Grid',exact:true}).click();assert.equal(await columns(p),2);await blocked.close();
 const noJS=await browser.newContext({javaScriptEnabled:false,viewport:{width:390,height:900}});await setup(noJS);const plain=await noJS.newPage();await plain.goto('https://preview.example/properties/');assert.equal(await columns(plain),1);assert(!(await plain.locator('.property-view-toggle').isVisible()));assert.equal(await plain.locator('.cards .card').count(),12);await noJS.close();
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
