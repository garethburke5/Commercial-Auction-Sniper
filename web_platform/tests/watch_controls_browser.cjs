// Real account template and JavaScript, with an isolated synthetic API/session.
const {chromium}=require('playwright');
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
process.chdir(path.resolve(__dirname,'../..'));
const html=require('child_process').execFileSync(process.env.PYTHON||'python',['web_platform/tests/render_account_fixture.py'],{encoding:'utf8'});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined,args:['--no-sandbox']});
 for(const width of [360,390,430,1440]){
  const page=await browser.newPage({viewport:{width,height:900}}),writes=[],errors=[],recoveries=[];
  let reportRecovered=false;
  page.on('pageerror',error=>errors.push(error.message));
  const remote={plan:'free',features:['save'],saved_properties:[],workspace:{properties:[{property_id:'removed',watched:1,notes:'',target_price:null,property:{id:'removed',address:'Earlier property',catalogue_missing:true}}],saved_searches:[],events:[],reviews:[]}};
  await page.route('**/*',route=>{
   const url=new URL(route.request().url());
   if(url.pathname==='/account/')return route.fulfill({contentType:'text/html',body:html});
   if(['/static/workspace.js','/static/navigation.js','/static/site.css'].includes(url.pathname))return route.fulfill({contentType:url.pathname.endsWith('.css')?'text/css':'text/javascript',body:fs.readFileSync('web_platform'+url.pathname,'utf8')});
   if(url.pathname==='/platform-config.json')return route.fulfill({json:{accounts_enabled:true,api_origin:'https://api.example'}});
   if(url.pathname==='/workspace-index.json')return route.fulfill({json:{rows:[]}});
   if(url.pathname==='/api/account')return route.fulfill({json:remote});
   if(url.pathname==='/api/admin/monitoring')return route.fulfill({json:{status:'completed',finished_at:Math.floor(Date.now()/1000)-3600,details:{generated_at:new Date().toISOString()}}});
   if(url.pathname==='/api/admin/report-usage')return route.fulfill({json:{attempts:[{review_id:'a'.repeat(32),attempt:1,status:reportRecovered?'interrupted':'processing',recovery_available:!reportRecovered}]}});
   if(url.pathname==='/api/admin/reviews/'+'a'.repeat(32)+'/recover'){
    recoveries.push(route.request().postData());reportRecovered=true;return route.fulfill({json:{status:'retry_available'}});
   }
   if(url.pathname==='/api/account/workspace/removed'){
    writes.push(route.request().postDataJSON());return route.fulfill({json:{updated:true}});
   }
   return route.fulfill({body:''});
  });
  await page.addInitScript(()=>{
   const session={access_token:'fixture-only',user:{id:'buyer',email:'buyer@example.com',user_metadata:{full_name:'Buyer'}}};
   window.AuctionIdentity={createClient:()=>({auth:{getSession:async()=>({data:{session}}),onAuthStateChange:()=>{}}})};
  });
  await page.goto('https://preview.example/account/');
  const stop=page.locator('#watched-items [data-watch="removed"]');
  await stop.waitFor({state:'visible'});
  assert.equal(await stop.textContent(),'Stop Watch');
  assert.match(await page.locator('#watched-items').textContent(),/Monitoring is paused/);
  assert.match(await page.locator('#watched-items').textContent(),/No longer in the current catalogue/);
  assert.equal(await page.locator('#watched-items h3 a').count(),0);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await stop.click();
  await page.waitForFunction(()=>document.querySelector('#watch-count').textContent==='0');
  assert.deepEqual(writes,[{watched:false}]);
  assert.equal(await page.locator('#watched-items [data-watch]').count(),0);
  assert.deepEqual(errors,[]);
  console.log(`${width}px: expired member can stop missing-property watch, no dead link or overflow`);
  remote.plan='investor';remote.features=['save','watch','saved_searches'];
  remote.workspace.properties=[];
  remote.workspace.saved_searches=[{search_id:'s',name:'Retail research',query:'q=retail',matches:[{property:{id:'new',address:'Retail <shop> & investment',path:'/property/new/'}}]}];
  await page.reload();
  const match=page.locator('#saved-searches li a');
  await match.waitFor({state:'visible'});
  assert.equal(await match.textContent(),'Retail <shop> & investment');
  assert.equal(await match.getAttribute('href'),'/property/new/');
  assert.equal(await page.locator('#saved-searches shop').count(),0);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.deepEqual(errors,[]);
  console.log(`${width}px: saved-search match shown safely with correct property link`);
  assert.equal(await page.locator('#owner-monitoring').isVisible(),false);
  assert.equal(await page.locator('#owner-report-recovery').isVisible(),false);
  remote.is_owner=true;
  await page.reload();
  await page.locator('#owner-controls').waitFor({state:'visible'});
  await page.locator('#owner-monitoring summary').click();
  await page.waitForFunction(()=>document.querySelector('#owner-monitoring-status').textContent.includes('45 minutes'));
  assert.match(await page.locator('#owner-monitoring-status').textContent(),/Last check completed/);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.deepEqual(errors,[]);
  console.log(`${width}px: owner sees overdue monitoring status without overflow`);
  await page.locator('#owner-report-recovery summary').click();
  const recovery=page.getByRole('button',{name:'Allow customer retry'});
  await recovery.waitFor({state:'visible'});assert(await recovery.isDisabled());
  await page.locator('#owner-report-status input[type=checkbox]').check();
  assert(await recovery.isEnabled());await recovery.click();
  await page.waitForFunction(()=>document.querySelector('#owner-report-status').textContent.includes('Reconcile any provider usage'));
  assert.equal(recoveries.length,1);assert.match(recoveries[0],/worker_stopped/);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.deepEqual(errors,[]);
  console.log(`${width}px: owner confirms stopped worker before allowing one retry`);
  await page.close();
 }
 await browser.close();
})().catch(error=>{console.error(error);process.exit(1)});
