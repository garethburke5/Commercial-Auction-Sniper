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
async function setup({initial=null,enabled=true,accountError=false,delayed=false,owner=false,watch=true,propertyPage=false}={}){
 let stored=initial,callback,release,signOutError=null,signOutCalls=0,accountCalls=0;
 const elements=Object.fromEntries(['account-entry','new-password-form','register-form','reset-password-form','magic-link-form','account-retry','account-title','account-intro','account-customer-content','account-dashboard','account-status','account-billing','owner-controls','owner-preview','owner-preview-status','account-reviews','report-credit-balance','saved-items','saved-count','watched-items','watch-count','saved-searches','watch-updates','recent-items','workspace-message'].map(id=>['#'+id,new Element(id)]));
 const link=new Element();link.textContent='Sign in / Register';
 const navSignOut=new Element('nav-signout',true),dashboardSignOut=new Element('account-signout',true);
 for(const b of [navSignOut,dashboardSignOut])b.setAttribute('data-sign-out');
 elements['#account-signout']=dashboardSignOut;elements['#sign-in-form']=new Element('sign-in-form',true);
 if(propertyPage)for(const id of ['account-dashboard','owner-preview','owner-preview-status'])delete elements['#'+id];
 const handlers={},redirects=[],timers=[],writes=[];
 const saveButton=new Element(),watchButton=new Element();saveButton.dataset.save='lot';watchButton.dataset.watch='lot';
 const storage=new Map(owner?[['auction-owner-preview','visitor']]:[]);
 const auth={
  getSession:async()=>({data:{session:stored},error:null}),
  onAuthStateChange:fn=>{callback=fn;return {data:{subscription:{unsubscribe(){}}}};},
  signOut:async()=>{signOutCalls++;if(signOutError)return {error:signOutError};stored=null;callback('SIGNED_OUT',null);return {error:null};}
 };
 const config={accounts_enabled:enabled,api_origin:'https://private.example',billing_enabled:true,plans:{free:{name:'Free'}}};
 const remote={features:watch?['watch']:[],saved_properties:[],plan:'free',is_owner:owner,workspace:{properties:[],saved_searches:[],events:[],reviews:[{id:'private-report',created_at:1}]}};
 const context={Event,window:{dispatchEvent(){},AuctionIdentity:{createClient:()=>({auth})}},document:{
  body:{dataset:{prefix:'/test'},append(){}},
  querySelector:s=>elements[s]||null,
  querySelectorAll:s=>s==='[data-save],[data-watch]'?[saveButton,watchButton]:s==='[data-account-link]'?[link]:s==='[data-sign-out]'?[navSignOut,dashboardSignOut]:[],
  getElementById:id=>elements['#'+id],createElement:()=>new Element(),createTextNode:s=>s,
  addEventListener:(name,fn)=>{handlers[name]=fn;}
 },localStorage:{getItem:()=>null},sessionStorage:{getItem:k=>storage.get(k),removeItem:k=>storage.delete(k)},
 location:{assign:url=>redirects.push(url)},MutationObserver:class{observe(){}},
 setTimeout:(fn,ms)=>ms?setTimeout(fn,ms):timers.push(fn),clearTimeout,URLSearchParams,
 fetch:async (url,options)=>{
  if(url.includes('/api/account/saved/')||url.includes('/api/account/workspace/')){writes.push(options);return {ok:true,json:async()=>({})};}
  if(url.endsWith('workspace-index.json'))return {ok:true,json:async()=>({rows:[{id:'lot'}]})};
  if(url.endsWith('platform-config.json'))return {ok:true,json:async()=>config};
  if(url.includes('/api/admin/preview/'))return {ok:true,json:async()=>({plan:'visitor',features:[]})};
  assert.equal(url,'https://private.example/api/account');accountCalls++;
  if(delayed)await new Promise(resolve=>{release=resolve;});
  if(accountError)throw Error('Private API unavailable');
  return {ok:true,json:async()=>remote,blob:async()=>Buffer.from('private report')};
 }};
 vm.runInNewContext(source,context);await tick();
 return {saveButton,watchButton,writes,link,navSignOut,dashboardSignOut,elements,redirects,storage,
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
 assert.equal(app.elements['#account-title'].textContent,'Sign in / Register');
 assert.equal(app.elements['#account-customer-content'].hidden,true);
 assert.equal(app.navSignOut.hidden,true);assert.equal(app.dashboardSignOut.hidden,true);
}
function expectCustomer(app){
 assert.equal(app.link.textContent,'My Auction Geek');
 assert.equal(app.elements['#account-title'].textContent,'My Auction Geek');
 assert.equal(app.elements['#account-customer-content'].hidden,false);
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

test('backend errors replace indefinite loading with a retry while retaining sign-out',async()=>{
 const app=await setup({initial:buyer('a'),accountError:true});
 assert.match(app.elements['#account-status'].textContent,/could not load/);
 assert.equal(app.elements['#account-retry'].hidden,false);expectCustomer(app);
});
test('password recovery hides the workspace and opens the password form for the same identity',async()=>{
 const app=await setup({initial:buyer('a')});app.emit('PASSWORD_RECOVERY',buyer('a'));
 assert.equal(app.elements['#new-password-form'].hidden,false);
 assert.equal(app.elements['#account-customer-content'].hidden,true);
 app.emit('SIGNED_OUT',null);expectGuest(app);assert.equal(app.elements['#new-password-form'].hidden,true);
});

test('property clicks respond immediately while account loads and block duplicate clicks',async()=>{
 const app=await setup({initial:buyer('a'),delayed:true});
 const pending=app.click(app.saveButton);
 assert.equal(app.saveButton.disabled,true);
 assert.equal(app.elements['#workspace-message'].textContent,'Checking your account…');
 await app.click(app.saveButton);assert.equal(app.writes.length,0);
 await app.release();await pending;
 assert.equal(app.writes.length,1);assert.equal(app.saveButton.textContent,'✓ Saved');assert.equal(app.saveButton.disabled,false);
 await app.click(app.watchButton);assert.equal(app.watchButton.textContent,'◉ Watching');
 await app.click(app.watchButton);assert.equal(app.watchButton.textContent,'○ Watch');
});
test('restricted Watch reports membership requirement without making a write',async()=>{
 const app=await setup({initial:buyer('a'),watch:false});await app.click(app.watchButton);
 assert.equal(app.writes.length,0);assert.match(app.elements['#workspace-message'].textContent,/requires Investor/);assert.equal(app.watchButton.textContent,'○ Watch');assert.equal(app.watchButton.disabled,false);
});

test('owner account can load entitlements and save on a property page without dashboard controls',async()=>{
 const app=await setup({initial:buyer('owner'),owner:true,propertyPage:true});
 app.storage.delete('auction-owner-preview');
 app.emit('SIGNED_OUT',null);app.emit('SIGNED_IN',buyer('owner'));await app.flush();
 await app.click(app.saveButton);assert.equal(app.saveButton.textContent,'✓ Saved');
 await app.click(app.watchButton);assert.equal(app.watchButton.textContent,'◉ Watching');
});
test('bounded waiting rejects stalled work rather than leaving controls pending forever',async()=>{
 const context={setTimeout,clearTimeout};vm.createContext(context);
 vm.runInContext(source.slice(source.indexOf('function bounded('),source.indexOf('function authFeedback(')),context);
 await assert.rejects(context.bounded(new Promise(()=>{}),5,'Please retry'),/Please retry/);
 assert.equal(await context.bounded(Promise.resolve('ready'),100,'timeout'),'ready');
});
