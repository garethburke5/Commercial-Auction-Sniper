/* Desktop/mobile sharing without sending messages or depending on accounts. */
const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('assert/strict'),{execFileSync}=require('child_process');
process.chdir(path.resolve(__dirname,'../..'));
const render=mode=>execFileSync(process.env.PYTHON||'python',['-m','web_platform.tests.render_share_fixture',mode],{encoding:'utf8'});
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
 for(const width of [390,1440]) for(const mode of ['property','cards','snapshot']) {
  const page=await browser.newPage({viewport:{width,height:950},hasTouch:width<500,isMobile:width<500});
  const events=[],errors=[],requests=[];page.on('pageerror',e=>errors.push(e.message));
  const html=render(mode);
  await page.route('**/*',r=>{
   const u=new URL(r.request().url());requests.push(u.pathname);
   if(u.pathname==='/fixture/')return r.fulfill({contentType:'text/html',body:html});
   if(u.pathname.startsWith('/static/')&&fs.existsSync('web_platform'+u.pathname))return r.fulfill({contentType:u.pathname.endsWith('.css')?'text/css':'text/javascript',body:fs.readFileSync('web_platform'+u.pathname)});
   if(u.pathname==='/platform-config.json')return r.fulfill({json:{accounts_enabled:false,share_analytics_endpoint:'https://preview.example/api/share-events'}});
   if(u.pathname==='/api/share-events'){events.push(r.request().postDataJSON());return r.fulfill({status:204});}
   return r.fulfill({body:'',contentType:'text/plain'});
  });
  await page.addInitScript(()=>{
   Object.defineProperty(navigator,'share',{configurable:true,writable:true,value:undefined});
   Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{window.copied=text;}}});
  });
  await page.goto('https://preview.example/fixture/?utm_source=test#history');
  assert(!requests.includes('/api/share-events'),'viewing a snapshot/page must not log sharing');
  const button=page.locator('[data-share-url]').first();await button.click();
  const dialog=page.locator('.share-dialog');assert(await dialog.isVisible());
  const canonical=await button.getAttribute('data-share-url');
  assert.equal(await dialog.locator('#share-link').inputValue(),canonical);
  const email=new URL(await dialog.locator('[data-channel=email]').getAttribute('href'));
  assert(email.searchParams.get('body').includes(canonical));assert(email.searchParams.get('subject').includes('Auction Geek'));
  const whatsapp=new URL(await dialog.locator('[data-channel=whatsapp]').getAttribute('href'));
  assert.equal(whatsapp.hostname,'api.whatsapp.com');assert.equal(whatsapp.pathname,'/send');assert(whatsapp.searchParams.get('text').includes('Guide price £190,000'));
  assert(!whatsapp.searchParams.get('text').includes('utm_source'));
  for(const channel of ['linkedin','facebook']){const link=new URL(await dialog.locator(`[data-channel=${channel}]`).getAttribute('href'));assert.equal(link.searchParams.get(channel==='linkedin'?'url':'u'),canonical);}
  await dialog.locator('.share-copy').click();
  assert(await dialog.locator('.share-copy').evaluate(e=>{const s=getComputedStyle(e);const rgb=v=>v.match(/\d+/g).slice(0,3).map(Number).map(x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4});const lum=v=>{const c=rgb(v);return .2126*c[0]+.7152*c[1]+.0722*c[2]};const a=lum(s.color),b=lum(s.backgroundColor);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05)>=4.5;}),'Copy button text must remain readable after hover/focus');
  assert.equal(await page.evaluate(()=>window.copied),canonical);
  await page.waitForFunction(()=>document.querySelector('.share-status').textContent==='Property link copied.');
  await page.keyboard.press('Escape');assert(!(await dialog.isVisible()));assert(await button.evaluate(e=>e===document.activeElement));
  // Keyboard entry and modal focus containment.
  await button.focus();await page.keyboard.press('Enter');await page.keyboard.press('Shift+Tab');
  assert(await page.evaluate(()=>document.querySelector('.share-dialog').contains(document.activeElement)));
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  fs.mkdirSync('test-artifacts',{recursive:true});await page.screenshot({path:`test-artifacts/share-${mode}-${width}.png`,fullPage:false});
  // Clipboard rejection must expose a selectable clean link, not a false success.
  await page.evaluate(()=>{navigator.clipboard.writeText=async()=>{throw Error('denied')};document.execCommand=()=>false;});
  await dialog.locator('.share-copy').click();assert.match(await dialog.locator('.share-status').textContent(),/Select and copy/);
  await page.keyboard.press('Escape');
  if(width<500){
   await page.evaluate(()=>{Object.defineProperty(navigator,'share',{configurable:true,writable:true,value:async data=>{window.nativeShared=data}});});
   await button.click();assert.equal((await page.evaluate(()=>window.nativeShared)).url,canonical);assert(!(await dialog.isVisible()));
   await page.evaluate(()=>{navigator.share=async()=>{throw new DOMException('cancel','AbortError')}});await button.click();assert(!(await dialog.isVisible()));
   await page.evaluate(()=>{navigator.share=async()=>{throw new DOMException('blocked','NotAllowedError')}});await button.click();assert(await dialog.isVisible());
  }
  await page.waitForFunction(()=>window.copied);
  assert(events.some(e=>e.channel==='copy'&&e.action==='copied'));
  assert(events.every(e=>Object.keys(e).sort().join(',')==='action,channel,placement'));
  assert.deepEqual(errors,[]);
  // Privacy signals suppress telemetry; sharing continues.
  await page.evaluate(()=>Object.defineProperty(navigator,'doNotTrack',{value:'1',configurable:true}));
  if(await dialog.isVisible())await page.keyboard.press('Escape');
  const before=events.length;await button.click();await page.waitForTimeout(100);assert.equal(events.length,before);
  console.log(`${width}px ${mode}: clean channel links, clipboard/fallback, keyboard, native handoff/cancel/failure and privacy verified`);
  await page.close();
 }
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
