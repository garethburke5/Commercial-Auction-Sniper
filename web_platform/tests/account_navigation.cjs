// Run the real workspace client with a controlled Supabase adapter and small DOM.
// These tests verify session transitions without sending authentication emails.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/workspace.js'), 'utf8');
const buyer = id => ({user:{id}, access_token:'test-token-'+id});
const tick = async () => {for(let i=0;i<4;i++) await new Promise(resolve=>setImmediate(resolve));};
class Element {
 constructor(id='', hidden=false){this.id=id;this.hidden=hidden;this.disabled=false;this.dataset={};this.textContent='';this.innerHTML='';this.attrs=new Set();}
 setAttribute(name){if(name==='hidden')this.hidden=true;this.attrs.add(name);}
 removeAttribute(name){if(name==='hidden')this.hidden=false;this.attrs.delete(name);}
 toggleAttribute(name,on){if(on)this.setAttribute(name);else this.removeAttribute(name);}
 hasAttribute(name){return this.attrs.has(name);}
 replaceChildren(...nodes){this.textContent=nodes.join('');this.innerHTML='';}
 addEventListener(){}
 closest(selector){return selector==='button'?this:null;}
}
async function setup({initial=null,enabled=true,accountError=false,delayed=false,owner=false}={}){
 let stored=initial,callback,release,signOutError=null,signOutCalls=0,accountCalls=0;
 const elements=Object.fromEntries(['account-dashboard','account-status','account-billing','owner-controls','owner-preview','owner-preview-status','account-reviews','report-credit-balance','saved-items','saved-count','watched-items','watch-count','saved-searches','watch-updates','recent-items','workspace-message'].map(id=>['#'+id,new Element(id)]));
 const link=new Element();link.textContent='Sign in / Register';
 const navSignOut=new Element('nav-signout',true),dashboardSignOut=new Element('account-signout',true);
 for(const b of [navSignOut,dashboardSignOut])b.setAttribute('data-sign-out');
 elements['#account-signout']=dashboardSignOut;elements['#sign-in-form']=new Element('sign-in-form',true);
 const handlers={},redirects=[],timers=[];
 const storage=new Map(owner?[['auction-owner-preview','visitor']]:[]);
 const auth={
  getSession:async()=>({data:{session:stored},error:null}),
  onAuthStateChange:fn=>{callback=fn;return {data:{subscription:{unsubscribe(){}}}};},
  signOut:async()=>{signOutCalls++;if(signOutError)return {error:signOutError};stored=null;callback('SIGNED_OUT',null);return {error:null};}
 };
 const config={accounts_enabled:enabled,api_origin:'https://private.example',billing_enabled:true,plans:{free:{name:'Free'}}};
 const remote={features:['watch'],saved_properties:[],plan:'free',is_owner:owner,workspace:{properties:[],saved_searches:[],events:[],reviews:[{id:'private-report',created_at:1}]}};
 const context={Event,window:{dispatchEvent(){},AuctionIdentity:{createClient:()=>({auth})}},document:{
  body:{dataset:{prefix:'/test'},append(){}},
  querySelector:s=>elements[s]||null,
  querySelectorAll:s=>s==='[data-account-link]'?[link]:s==='[data-sign-out]'?[navSignOut,dashboardSignOut]:[],
  getElementById:id=>elements['#'+id],createElement:()=>new Element(),createTextNode:s=>s,
  addEventListener:(name,fn)=>{handlers[name]=fn;}
 },localStorage:{getItem:()=>null},sessionStorage:{getItem:k=>storage.get(k),removeItem:k=>storage.delete(k)},
 location:{assign:url=>redirects.push(url)},MutationObserver:class{observe(){}},
 setTimeout:fn=>timers.push(fn),URLSearchParams,
 fetch:async url=>{
  if(url.endsWith('workspace-index.json'))return {ok:true,json:async()=>({rows:[]})};
  if(url.endsWith('platform-config.json'))return {ok:true,json:async()=>config};
  if(url.includes('/api/admin/preview/'))return {ok:true,json:async()=>({plan:'visitor',features:[]})};
  assert.equal(url,'https://private.example/api/account');accountCalls++;
  if(delayed)await new Promise(resolve=>{release=resolve;});
  if(accountError)throw Error('Private API unavailable');
  return {ok:true,json:async()=>remote,blob:async()=>Buffer.from('private report')};
 }};
 vm.runInNewContext(source,context);await tick();
 return {link,navSignOut,dashboardSignOut,elements,redirects,storage,
  get accountCalls(){return accountCalls;},get signOutCalls(){return signOutCalls;},
  emit(event,next){stored=next;assert.ok(callback,'Auth listener must survive API errors');callback(event,next);},
  async flush(){while(timers.length){timers.shift()();await tick();}},
  release:async()=>{release();await tick();},
  delayNext:()=>{delayed=true;},
  click:async button=>{await handlers.click({target:button});await tick();},
  failSignOut:()=>{signOutError=Error('Sign out failed. Please retry.');},
  workspace:context.window.AuctionWorkspace};
}
function expectGuest(app){
 assert.equal(app.link.textContent,'Sign in / Register');
 assert.equal(app.navSignOut.hidden,true);assert.equal(app.dashboardSignOut.hidden,true);
}
function expectCustomer(app){
 assert.equal(app.link.textContent,'My Auction Geek');
 assert.equal(app.navSignOut.hidden,false);assert.equal(app.dashboardSignOut.hidden,false);
 assert.equal(app.elements['#sign-in-form'].hidden,true);
}
test('disabled accounts and ordinary guests have an honest static navigation',async()=>{
 expectGuest(await setup({enabled:false}));
 const app=await setup();expectGuest(app);assert.equal(app.elements['#sign-in-form'].hidden,false);
});
test('restores a returning Supabase session and signs in without a page reload',async()=>{
 expectCustomer(await setup({initial:buyer('a')}));
 const app=await setup();app.emit('SIGNED_IN',buyer('b'));expectCustomer(app);await app.flush();
 assert.equal(app.accountCalls,1);
 app.emit('TOKEN_REFRESHED',{...buyer('b'),access_token:'refreshed'});await app.flush();
 expectCustomer(app);assert.equal(app.accountCalls,1,'Token refresh must not reload private data');
});
test('sign-out events from another tab clear navigation and private account controls',async()=>{
 const app=await setup({initial:buyer('a')});expectCustomer(app);
 assert.match(app.elements['#account-reviews'].innerHTML,/private-report/);
 app.emit('SIGNED_OUT',null);expectGuest(app);
 for(const id of ['account-reviews','report-credit-balance'])assert.equal(app.elements['#'+id].innerHTML,'');
 for(const id of ['account-billing','owner-controls'])assert.equal(app.elements['#'+id].hidden,true);
 assert.equal(app.elements['#sign-in-form'].hidden,false);
});
for(const control of ['navSignOut','dashboardSignOut'])test(control+' reuses Supabase signOut and returns to the account page',async()=>{
 const app=await setup({initial:buyer('a')});await app.click(app[control]);
 expectGuest(app);assert.equal(app.signOutCalls,1);assert.deepEqual(app.redirects,['/test/account/']);
});
test('failed sign-out keeps the customer state and offers a retry',async()=>{
 const app=await setup({initial:buyer('a')});app.failSignOut();await app.click(app.navSignOut);
 expectCustomer(app);assert.equal(app.navSignOut.disabled,false);assert.deepEqual(app.redirects,[]);
 assert.match(app.elements['#workspace-message'].textContent,/Sign out failed/);
});
test('private API failure does not suppress navigation or the auth subscription',async()=>{
 const app=await setup({initial:buyer('a'),accountError:true});expectCustomer(app);
 app.emit('SIGNED_OUT',null);expectGuest(app);
 app.emit('SIGNED_IN',buyer('b'));await app.flush();expectCustomer(app);
});
test('sign-out remains usable during a slow API call and its late response is ignored',async()=>{
 const app=await setup({initial:buyer('a'),delayed:true});expectCustomer(app);
 await app.click(app.navSignOut);expectGuest(app);await app.release();expectGuest(app);
 assert.equal(app.elements['#account-reviews'].innerHTML,'');
 assert.equal(app.elements['#account-billing'].hidden,true);
});
test('owner visitor preview never hides the real session or its sign-out control',async()=>{
 const app=await setup({initial:buyer('owner'),owner:true});expectCustomer(app);
 assert.equal(app.workspace.signedIn(),false,'Existing read-only visitor preview remains intact');
 await app.click(app.navSignOut);expectGuest(app);assert.equal(app.storage.has('auction-owner-preview'),false);
});
for(const method of ['api','upload','download'])test(method+' rejects a late private response after account changes',async()=>{
 const app=await setup({initial:buyer('a')});app.delayNext();
 const request=app.workspace[method]('/api/account');
 const rejected=assert.rejects(request,/account changed/);await tick();
 app.emit('SIGNED_OUT',null);app.emit('SIGNED_IN',buyer('b'));
 await app.release();await rejected;expectCustomer(app);
 assert.equal(app.elements['#account-reviews'].innerHTML,'');
});
test('logging out and back into the same account still invalidates old requests',async()=>{
 const app=await setup({initial:buyer('a')});app.delayNext();
 const request=app.workspace.api('/api/account');
 const rejected=assert.rejects(request,/account changed/);await tick();
 app.emit('SIGNED_OUT',null);app.emit('SIGNED_IN',buyer('a'));
 await app.release();await rejected;
});
