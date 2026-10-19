(() => {
'use strict';
const root=document.body.dataset.prefix||'', key='auction-sniper-workspace-v1';
const empty=()=>({properties:{},searches:[],events:[],recent:[]});
let state=empty(), session=null, auth=null, config=null, index={}, features=new Set(), preview=null, authEpoch=0;
const returnQuery=new URLSearchParams(location.search||'');
const checkoutReturned=returnQuery.get('checkout')==='returned'||returnQuery.get('billing')==='returned';
let checkoutAccount=null,checkoutFailed=false;
let authMode='signin', recoveryMode=new URLSearchParams(location.search||'').get('mode')==='recovery', authBusy=false,authRestoring=true;
try { state={...state,...JSON.parse(localStorage.getItem(key)||'{}')}; } catch (_) {}
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=v=>typeof v==='number'?'£'+v.toLocaleString('en-GB'):(v||'Not stated');
const signedIn=()=>!!session&&preview?.plan!=='visitor';
const can=feature=>signedIn()&&features.has(feature);
const notice=s=>{let e=document.querySelector('#workspace-message');if(!e){e=document.createElement('p');e.id='workspace-message';e.className='workspace-toast';e.setAttribute('role','status');document.body.append(e);}e.textContent=s;};
function bounded(promise,ms,message){
 let timer;
 return Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error(message)),ms);})]).finally(()=>clearTimeout(timer));
}
function authFeedback(message,error=false,id='auth-feedback'){
 const e=document.getElementById(id);if(!e){notice(message);return;}
 e.textContent=message;e.hidden=!message;e.dataset.error=String(error);
 if(message)e.focus?.();
}
function setAuthMode(mode){
 if(!['signin','register','reset','magic'].includes(mode)||authBusy)return;
 authMode=mode;authFeedback('');renderAuth();
 document.querySelector(({signin:'#signin-email',register:'#register-name',reset:'#reset-email',magic:'#magic-email'})[mode])?.focus();
}
function renderCheckoutReturn(){
 const box=document.querySelector('#checkout-return');if(!box)return;
 box.hidden=!checkoutReturned;if(!checkoutReturned)return;
 const title=document.querySelector('#checkout-return-title'),message=document.querySelector('#checkout-return-message'),retry=document.querySelector('#checkout-refresh');
 let heading='Checking your membership',detail='Welcome back from Stripe. We are checking your account. Please do not submit another payment.',refresh=false;
 if(!session){heading='Welcome back from Stripe';detail='Sign in with the account you used at checkout to check your membership. Please do not submit another payment.';}
 else if(checkoutFailed){heading='We could not check your membership';detail='Your payment may have completed. Check again below; please do not submit another payment. If this continues, contact team@auctiongeek.co.uk.';refresh=true;}
 else if(checkoutAccount){
  if(checkoutAccount.billing?.payment_required){
   heading='Your payment needs attention';
   detail='Stripe has not confirmed a successful payment. Paid monitoring and new report credits are paused; your shortlist and previously paid reports remain available. '+(checkoutAccount.billing.has_customer&&!preview&&(config.billing_enabled||checkoutAccount.is_owner)?'Use Update payment method & invoices to resolve payment.':'Contact team@auctiongeek.co.uk for help with payment.')+' Please do not start another subscription.';
   refresh=true;
  }else if(['investor','professional'].includes(checkoutAccount.plan)){
   const name=config?.plans?.[checkoutAccount.plan]?.name||(checkoutAccount.plan==='professional'?'Investor Pro':'Investor');
   heading='Your '+name+' membership is active';
   detail='Welcome back. Your account membership has been verified.';
   const balance=checkoutAccount.report_credits;
   if(balance?.period_end)detail+=' '+balance.remaining+' of '+balance.allowance+' included report credits available until '+new Date(balance.period_end*1000).toLocaleDateString('en-GB')+'.';
   detail+=' Report generation remains subject to launch quality approval.';
   if(preview)detail+=' You are viewing a customer preview; select My account to use your membership.';
  }else if(['canceled','incomplete_expired'].includes(checkoutAccount.billing?.status)){
   heading='Your membership is not active';detail='Your account is on Free. Your shortlist and previously paid reports remain available.';
  }else{heading='Your membership update is pending';detail='Your account has not yet received an active membership. Check again shortly; please do not submit another payment. If this continues, contact team@auctiongeek.co.uk.';refresh=true;}
 }
 title.textContent=heading;message.textContent=detail;retry.hidden=!refresh;
}
function renderAuth(){
 renderCheckoutReturn();
 // This controls presentation only; all private data remains authorized by the API.
 const authenticated=!!session;
 document.querySelector('#account-customer-content')?.toggleAttribute('hidden',!authenticated||recoveryMode);
 document.querySelector('#account-entry')?.toggleAttribute('hidden',authenticated||!auth);
 document.querySelector('#new-password-form')?.toggleAttribute('hidden',!authenticated||!recoveryMode);
 const title=document.querySelector('#account-title'),intro=document.querySelector('#account-intro');
 if(title)title.textContent=authenticated?(recoveryMode?'Set your password':'My Auction Geek'):'Sign in / Register';
 if(intro)intro.textContent=authenticated?'Your shortlist, watched properties, private notes, searches and investment reports.':'Your property shortlist and investment research, in one place.';
 const fullName=String(session?.user?.user_metadata?.full_name||'').trim();
 const welcome=document.querySelector('#account-welcome');if(welcome)welcome.textContent=fullName?'Welcome, '+fullName:'Welcome to My Auction Geek';
 const profile=document.querySelector('#profile-name');if(profile&&document.activeElement!==profile)profile.value=fullName;
 document.querySelectorAll('[data-account-link]').forEach(a=>{a.textContent=authenticated?'My Auction Geek':'Sign in / Register';});
 document.querySelectorAll('[data-sign-out]').forEach(b=>{b.hidden=!authenticated;});
 const forms={signin:'sign-in-form',register:'register-form',reset:'reset-password-form',magic:'magic-link-form'};
 for(const [mode,id] of Object.entries(forms))document.getElementById(id)?.toggleAttribute('hidden',authenticated||!auth||mode!==authMode);
 document.querySelector('#registration-next')?.toggleAttribute('hidden',authenticated||!auth||authMode!=='confirmation');
 document.querySelectorAll('[data-auth-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.authMode===authMode)));
 let legacy=false;try{const old=JSON.parse(localStorage.getItem(key)||'{}');legacy=Object.keys(old.properties||{}).length>0||(old.searches||[]).length>0;}catch(_){}
 document.querySelector('#account-device-tools')?.toggleAttribute('hidden',!authenticated||!legacy);
 if(!authenticated){
  document.querySelector('#billing-status')?.setAttribute('hidden','');
  document.querySelector('#billing-status')?.replaceChildren();
  document.querySelector('#account-billing')?.setAttribute('hidden','');
  document.querySelector('#account-retry')?.setAttribute('hidden','');
  document.querySelector('#owner-controls')?.setAttribute('hidden','');
  document.querySelector('#owner-monitoring')?.setAttribute('hidden','');
  document.querySelector('#owner-report-recovery')?.setAttribute('hidden','');
  document.querySelector('#owner-report-status')?.replaceChildren();
  document.querySelector('#owner-monitoring-status')?.replaceChildren();
  document.querySelector('#account-reviews')?.replaceChildren();
  document.querySelector('#account-evidence')?.replaceChildren();
  document.querySelector('#report-credit-balance')?.replaceChildren();
  document.querySelector('#account-status')?.replaceChildren(document.createTextNode(auth?'':'Sign-in is currently unavailable. Please try again shortly; you can still browse properties.'));
 }
}
function workspaceFailed(){
 checkoutAccount=null;checkoutFailed=true;renderCheckoutReturn();
 document.querySelector('#billing-status')?.setAttribute('hidden','');
 document.querySelector('#account-billing')?.setAttribute('hidden','');
 features.clear();
 document.querySelector('#account-status')?.replaceChildren(document.createTextNode('You are signed in, but your workspace could not load. Please retry. Your saved information has not been deleted.'));
 document.querySelector('#account-retry')?.removeAttribute('hidden');
}
function queueAccountLoad(){
 const epoch=authEpoch;
 setTimeout(()=>{if(session&&authEpoch===epoch)loadAccount().catch(()=>{if(authEpoch===epoch)workspaceFailed();});},0);
}
function updateSession(next){
 const changed=next?.user?.id!==session?.user?.id;
 session=next;
 if(changed){
  authEpoch++;
  checkoutAccount=null;checkoutFailed=false;
  if(!next){recoveryMode=false;document.querySelectorAll('input[type=password]').forEach(e=>{e.value='';});}
  features.clear();state=empty();preview=null;
  document.querySelector('#account-reviews')?.replaceChildren();
  document.querySelector('#account-evidence')?.replaceChildren();
  document.querySelector('#report-credit-balance')?.replaceChildren();
  document.querySelector('#account-billing')?.setAttribute('hidden','');
  document.querySelector('#billing-status')?.setAttribute('hidden','');
  document.querySelector('#billing-status')?.replaceChildren();
  document.querySelector('#owner-controls')?.setAttribute('hidden','');
  document.querySelector('#owner-monitoring')?.setAttribute('hidden','');
  document.querySelector('#owner-report-recovery')?.setAttribute('hidden','');
  document.querySelector('#owner-report-status')?.replaceChildren();
  document.querySelector('#owner-monitoring-status')?.replaceChildren();
  if(next)document.querySelector('#account-status')?.replaceChildren(document.createTextNode('Signed in. Loading your private workspace…'));
  else try{sessionStorage.removeItem('auction-owner-preview');}catch(_){}
  render();
 }
 renderAuth();if(changed)window.dispatchEvent(new Event('auction-auth-change'));return changed;
}
async function refreshSession(){
 if(auth){const {data,error}=await bounded(auth.auth.getSession(),15000,'Your sign-in check timed out. Please reload this page and try again.');if(error)throw error;updateSession(data.session);}
}
function persist(){if(session)return;try{localStorage.setItem(key,JSON.stringify(state));}catch(_){notice('This browser could not save your workspace. Download your stored data for a backup.');}}
async function api(path,method='GET',body){
 if(preview&&method!=='GET')throw Error('Read-only customer preview. Return to My account to make changes.');
 return accountRequest(path,{method,headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});
}
async function accountRequest(path,options={},format='json'){
 const epoch=authEpoch;
 const current=()=>{if(epoch!==authEpoch)throw Error('Your account changed. Please retry.');};
 await refreshSession();
 current();
 if(!session||!config?.api_origin)throw Error('Sign in is required');
 const r=await fetch(config.api_origin+path,{...options,signal:options.signal||(typeof AbortSignal!=='undefined'?AbortSignal.timeout(60000):undefined),headers:{...options.headers,Authorization:'Bearer '+session.access_token}});
 current();
 const result=await (r.ok&&format==='blob'?r.blob():r.json());
 current();
 if(!r.ok)throw Error(result.detail||'Could not complete the request');return result;
}
function safePath(p){return typeof p==='string'&&p.startsWith('/')&&!p.startsWith('//')?root+p:root+'/properties/';}
function access(feature){
 if(feature==='watch')notice('Watch is not active. Property Watch requires Investor or Investor Pro. See Plans & Pricing for membership details.');
 if(feature!=='save'){
  const anchor=document.activeElement;
  const host=anchor?.closest('.save-actions, .plan-card, form, section')||document.querySelector('main');
  if(host){let hint=host.querySelector('.contextual-membership');if(!hint){hint=document.createElement('p');hint.className='contextual-membership';hint.setAttribute('role','status');host.append(hint);}
   hint.replaceChildren(document.createTextNode(feature==='subscription'?'Membership checkout is being activated. ':feature==='watch'?'Watch is not active for this account. Property Watch is included with Investor and Investor Pro; saving to your shortlist remains free. ':'Property Watch, saved searches and private research tools are included with Investor from £15/month. '));
   const link=document.createElement('a');link.href=root+'/plans/';link.textContent='Compare plans and launch availability →';hint.append(link);}
  return;
 }
 const dialog=document.querySelector('#access-dialog');if(!dialog)return;
 const save=feature==='save', billing=feature==='subscription';
 const title=save?'Keep your shortlist with a free account':billing?'Your membership, ready when checkout opens':feature==='saved_searches'?'Save this search & get new-match alerts':feature==='watch'?'Watch this property for meaningful changes':'Make this research your own';
 document.querySelector('#access-title').textContent=title;
 document.querySelector('#access-eyebrow').textContent=save?'FREE REGISTERED ACCOUNT':billing?'PLANS & PRICING':'MEMBERSHIP TOOLS';
 document.querySelector('#access-description').textContent=save
  ?'Save is your personal shortlist. Register or sign in for free to keep properties together and return to your research.'
  :billing?'Secure subscription checkout is being activated. The initial monthly prices are shown on Plans & Pricing; no payment will be taken here.'
  :'Available with Investor and Investor Pro.';
 const detail=document.querySelector('#access-detail');detail.replaceChildren();
 const p=document.createElement('p');p.className='small';
 p.textContent=save?(config?.accounts_enabled?'Your shortlist is private to your account.':'Registration is being activated. Free property search and Free Property Snapshots remain available now.')
  :feature==='watch'?'Follow guide prices, status, auction dates, legal-pack availability and important particulars. Membership monitoring is separate from your free shortlist. Email delivery is being activated.'
  :feature==='saved_searches'?'Keep your applied criteria ready to reopen. New-match email delivery is being activated; normal searching stays free.'
  :billing?'One-off Full Investment Reports remain separate: a monthly subscription is never required to research one property.'
  :'Keep private notes and a personal bid target alongside the property evidence.';
 detail.append(p);
 const primary=document.querySelector('#access-primary');
 primary.href=root+(save?'/account/':'/plans/');primary.textContent=save?(config?.accounts_enabled?'Register / sign in free →':'Free account information →'):'View Plans & Pricing →';
 if(!dialog.open)dialog.showModal();
}
function renderButtons(){document.querySelectorAll('[data-save],[data-watch]').forEach(b=>{
 const id=b.dataset.save||b.dataset.watch,kind=b.dataset.save?'saved':'watched';
 const on=!!state.properties[id]?.[kind]&&(kind==='saved'||can('watch'));
 const text=kind==='saved'?(on?'✓ Saved':'♡ Save'):(on?'◉ Watching':state.properties[id]?.watched?'Stop Watch':'○ Watch');
 if(b.textContent!==text)b.textContent=text;b.setAttribute('aria-pressed',String(on));
});}
function item(row){
 if(!row)return '';const p=state.properties[row.id]||{};
 const edit=can('notes')&&can('bid_targets');
 const notes=edit?`<form data-note-form="${esc(row.id)}"><label>Private note<textarea name="notes" maxlength="10000" rows="3">${esc(p.notes||'')}</textarea></label><label>My target / maximum bid (£)<input type="number" min="0" step="100" name="target_price" value="${esc(p.target_price??'')}"></label><button class="button outline">Save note & target</button></form>`
  :`${p.notes?`<p>${esc(p.notes)}</p>`:''}${p.target_price!=null?`<p>Stored target: ${esc(money(p.target_price))}</p>`:''}<p class="small">Private notes and saved bid targets are membership tools. Your earlier records are preserved.</p><button class="button outline" data-feature="notes">Explore research tools</button>`;
 return `<article class="workspace-card"><div>${row.image_url?`<img src="${esc(row.image_url)}" alt="" loading="lazy" width="112" height="84">`:''}<h3>${row.catalogue_missing?esc(row.address):`<a href="${esc(safePath(row.path))}">${esc(row.address)}</a>`}</h3><p>${row.catalogue_missing?'No longer in the current catalogue. You can still remove this property or stop its watch.':`${esc(row.source)} · ${esc(row.guide||money(row.guide_price))}`}</p></div><div class="save-actions"><button data-save="${esc(row.id)}" aria-pressed="${!!p.saved}">${p.saved?'✓ Saved':'♡ Save'}</button><button data-watch="${esc(row.id)}" aria-pressed="${!!p.watched&&can('watch')}">${p.watched?(can('watch')?'◉ Watching':'Stop Watch'):'○ Watch'}</button></div><details><summary>My notes & bid target</summary>${notes}</details></article>`;
}
function render(){
 const emailToggle=document.querySelector('#email-alerts-enabled'),emailStatus=document.querySelector('#email-alerts-status');
 if(emailToggle){
  const pref=checkoutAccount?.alert_preferences;
  emailToggle.checked=!!pref?.enabled&&!preview;
  emailToggle.disabled=!!preview||!signedIn()||(!pref?.enabled&&(!pref?.delivery_available||!can('alerts')));
  emailStatus.textContent=preview?'Email settings cannot be changed in a customer preview.':!pref?.delivery_available?'Email delivery is not yet enabled. Your updates remain available in My Auction Geek.':!can('alerts')?'Email alerts require an active Investor or Investor Pro membership.':pref.enabled?'Daily email updates enabled. You can switch them off here or unsubscribe in any email.':'Email updates are off. Enable them to receive new updates at your verified account address.';
 }
 renderButtons();if(!document.querySelector('#account-dashboard'))return;
 for(const [kind,el,count]of[['saved','saved-items','saved-count'],['watched','watched-items','watch-count']]){
  const rows=Object.entries(state.properties).filter(([,p])=>p[kind]).map(([id,p])=>index[id]||p.property).filter(Boolean);
  const permitted=kind==='saved'||can('watch');
  document.getElementById(el).innerHTML=(!permitted?'<p>Monitoring is paused until membership is active. You can still stop earlier watches.</p><button class="button outline" data-feature="watch">Explore Watch →</button>':'')+(rows.map(item).join('')||`<p>No ${kind==='saved'?'saved':'watched'} properties yet.</p>`);
  document.getElementById(count).textContent=rows.length;
 }
 document.querySelector('#saved-searches').innerHTML=can('saved_searches')?(state.searches.map(s=>`<p><a href="${esc(root+'/properties/?'+s.query)}">${esc(s.name)}</a> <label class="small"><input type="checkbox" data-search-digest="${esc(s.id)}" ${s.digest?'checked':''} ${preview?'disabled':''}> Include in email digest</label> <button data-remove-search="${esc(s.id)}" class="textlink">Remove</button></p>${(s.matches||[]).length?`<ul>${s.matches.map(m=>`<li>New match: <a href="${esc(safePath(m.property?.path))}">${esc(m.property?.address||'View property')}</a></li>`).join('')}</ul>`:''}`).join('')||'<p>Apply filters on Find property, then Save this search.</p>'):'<p>Save your criteria with membership. Any previously saved criteria are preserved in your stored data.</p><button class="button outline" data-feature="saved_searches">Explore saved searches →</button>';
 document.querySelector('#watch-updates').innerHTML=can('watch')?(state.events.slice(0,50).map(e=>`<article class="watch-event"><b>${esc(e.title)}</b><p><a href="${esc(safePath(e.property?.path))}">${esc(e.property?.address||e.property_id)}</a></p><p>${esc(money(e.before))} → ${esc(money(e.after))}</p><small>Observed ${esc(new Date(e.at||e.created_at*1000).toLocaleDateString('en-GB'))}</small></article>`).join('')||'<p>No changes recorded. Watches begin with the snapshot available when you select Watch.</p>'):'<p>Property-change monitoring is included with membership.</p>';
 document.querySelector('#recent-items').innerHTML=state.recent.slice(0,8).map(id=>item(index[id]||state.properties[id]?.property)).join('')||'<p>Recently viewed properties appear as you research in your account.</p>';
}
document.querySelector('#email-alerts-enabled')?.addEventListener('change',async event=>{
 const input=event.target,epoch=authEpoch;input.disabled=true;
 try{
  const result=await api('/api/account/alerts','PUT',{enabled:input.checked});
  if(epoch!==authEpoch||preview)return;
  checkoutAccount.alert_preferences=result;render();
 }catch(error){if(epoch===authEpoch){render();notice(error.message);}}
});
document.querySelector('#saved-searches')?.addEventListener('change',async event=>{
 const input=event.target.closest('[data-search-digest]');if(!input||preview)return;
 const search=state.searches.find(s=>s.id===input.dataset.searchDigest);if(!search)return;
 const epoch=authEpoch;input.disabled=true;
 try{
  await api('/api/account/searches/'+encodeURIComponent(search.id),'PUT',{name:search.name,query:search.query,digest:input.checked});
  if(epoch!==authEpoch||preview)return;
  search.digest=input.checked;render();notice('Search email preference saved. Delivery also requires email updates to be enabled.');
 }catch(error){if(epoch===authEpoch){render();notice(error.message);}}
});
async function toggle(id,kind){
 if(kind==='saved'&&!signedIn()){access('save');return;}
 if(kind==='watched'&&!can('watch')&&!state.properties[id]?.watched){access('watch');return;}
 const row=index[id]||state.properties[id]?.property;if(!row){notice('Property details are still loading. Please try again.');return;}
 const p=state.properties[id]||{property:row},on=!p[kind];
 if(kind==='saved')await api('/api/account/saved/'+id,on?'PUT':'DELETE');
 else await api('/api/account/workspace/'+id,'PUT',{watched:on});
 p[kind]=on;p.property=row;state.properties[id]=p;render();notice(on?(kind==='saved'?'Saved to your shortlist':'Watching for changes'):(kind==='saved'?'Removed from shortlist':'Watch stopped'));
}
function searchQuery(){
 const query=new URLSearchParams(document.querySelector('#save-search')?.dataset.query||'');
 for(const k of [...query.keys()])if(!['q','source','min','max','yield','status','tenure','sort'].includes(k))query.delete(k);
 return query;
}
document.addEventListener('click',async e=>{
 const b=e.target.closest('button');if(!b)return;
 const propertyAction=!!(b.dataset.save||b.dataset.watch);
 if(propertyAction){if(b.disabled)return;b.disabled=true;b.setAttribute('aria-busy','true');notice('Checking your account…');}
 if(b.hasAttribute('data-close-dialog')){b.closest('dialog').close();return;}
 try{
  if(b.dataset.authMode){setAuthMode(b.dataset.authMode);return;}
  // This remains available while the private workspace is still loading.
  if(b.hasAttribute('data-sign-out')){
   if(!auth||!session||b.disabled)return;
   b.disabled=true;
   try{const {error}=await auth.auth.signOut();if(error)throw error;updateSession(null);location.assign(root+'/account/');}
   finally{b.disabled=false;}
   return;
  }
  if(propertyAction)await bounded(initialized,20000,'Your account is taking too long to load. Nothing was changed. Please try again.');
  else await initialized;
  if(b.id==='account-retry'||b.id==='checkout-refresh'){
   checkoutAccount=null;checkoutFailed=false;renderCheckoutReturn();
   b.disabled=true;try{await loadAccount();}catch(_){workspaceFailed();}finally{b.disabled=false;}return;
  }
  if(b.id==='account-password-reset'){
   if(!auth||!session||preview)return;
   b.disabled=true;try{
    const {error}=await auth.auth.resetPasswordForEmail(session.user.email,{redirectTo:location.origin+root+'/account/'});
    if(error)throw error;
    authFeedback('Check your email for a link to set or reset your password.',false,'settings-feedback');
   }catch(_){authFeedback('We could not send a reset link. Please try again shortly.',true,'settings-feedback');}finally{b.disabled=false;}return;
  }
  if(b.id==='export-device-workspace'){
   const previous=JSON.parse(localStorage.getItem(key)||'{}');
   const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify({schema_version:1,...previous},null,2)],{type:'application/json'}));a.download='auction-geek-earlier-browser-records.json';a.click();URL.revokeObjectURL(a.href);return;
  }
  if(b.dataset.save)await toggle(b.dataset.save,'saved');
  if(b.dataset.watch)await toggle(b.dataset.watch,'watched');
  if(b.hasAttribute('data-register'))access('save');
  if(b.dataset.feature)access(b.dataset.feature);
  if(b.id==='save-search'){
   if(!can('saved_searches')){access('saved_searches');return;}
   const query=searchQuery();if(!query.toString())return;
   document.querySelector('#save-search-form input[name=name]').value=query.get('q')||query.get('source')||'My property search';
   document.querySelector('#search-dialog').showModal();
  }
  if(b.dataset.removeSearch){await api('/api/account/searches/'+b.dataset.removeSearch,'DELETE');state.searches=state.searches.filter(s=>s.id!==b.dataset.removeSearch);render();}
  if(b.id==='export-workspace'){
   const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify({schema_version:1,...state},null,2)],{type:'application/json'}));a.download='auction-geek-workspace.json';a.click();URL.revokeObjectURL(a.href);
  }
  if(b.dataset.sandboxBilling){
   if(b.disabled)return;
   if(preview)throw Error('Return to My account before testing billing.');
   b.disabled=true;
   try{
    notice('Opening Stripe sandbox… No real payment will be taken.');
    const plan=b.dataset.sandboxBilling;
    const r=await api('/api/admin/billing/'+(plan==='portal'?'portal':'checkout'),'POST',plan==='portal'?undefined:{plan});
    location.assign(r.url);
   }finally{b.disabled=false;}
   return;
  }
  if(b.dataset.subscribe){
   if(!config?.billing_enabled){access('subscription');return;}
   if(!signedIn()){access('save');return;}
   const r=await api('/api/billing/checkout','POST',{plan:b.dataset.subscribe});location.assign(r.url);
  }
  if(b.id==='account-billing'){
   if(b.disabled)return;
   b.disabled=true;
   try{const r=await api(config?.billing_enabled?'/api/billing/portal':'/api/admin/billing/portal','POST');location.assign(r.url);}
   finally{b.disabled=false;}
  }
 }catch(err){notice(err.name==='TimeoutError'||err.name==='AbortError'?'The connection timed out. Please reload to check the current saved state before trying again.':err.message);}
 finally{if(propertyAction){b.disabled=false;b.removeAttribute('aria-busy');}}
});
async function submitIdentity(f){
 if(authBusy)return;
 authBusy=true;const submit=f.querySelector('button[type=submit]');if(submit)submit.disabled=true;
 const target=f.id==='new-password-form'?'password-feedback':f.id==='profile-form'?'profile-feedback':'auth-feedback';
 authFeedback('Please wait…',false,target);
 try{
  await initialized;if(!auth)throw Error('Sign-in is unavailable. Please try again shortly.');
  const fd=new FormData(f),email=String(fd.get('email')||'').trim(),password=String(fd.get('password')||'');
  const callback=location.origin+root+'/account/';
  if(f.id==='sign-in-form'){
   const {data,error}=await auth.auth.signInWithPassword({email,password});
   if(error)throw Error('Could not sign in. Check your email and password, confirm your email if needed, or use Forgot password.');
   if(updateSession(data.session))queueAccountLoad();authFeedback('');
  }else if(f.id==='register-form'){
   const name=String(fd.get('full_name')||'').trim();
   if(!name||name.length>100)throw Error('Enter your name (up to 100 characters).');
   if(password.length<12)throw Error('Use at least 12 characters for your password.');
   const {data,error}=await auth.auth.signUp({email,password,options:{emailRedirectTo:callback,data:{full_name:name}}});
   if(error)throw error;
   if(data.session){if(updateSession(data.session))queueAccountLoad();}
   else {
    authMode='confirmation';authFeedback('');
    const address=document.querySelector('#registration-email');if(address)address.textContent=email;
    for(const id of ['signin-email','reset-email']){const input=document.getElementById(id);if(input)input.value=email;}
    renderAuth();const heading=document.querySelector('#registration-next-title');heading?.focus();heading?.scrollIntoView?.({block:'center',behavior:'auto'});
   }
  }else if(f.id==='magic-link-form'){
   const {error}=await auth.auth.signInWithOtp({email,options:{shouldCreateUser:false,emailRedirectTo:callback}});
   if(error&&error.status===429)throw Error('Please wait a minute before requesting another email.');
   if(error&&error.status>=500)throw Error('Email sign-in is temporarily unavailable. Please try again shortly.');
   authFeedback('If this email belongs to an account, a sign-in link is on its way. Check your inbox and spam folder. New here? Choose Create account.');
  }else if(f.id==='reset-password-form'){
   const {error}=await auth.auth.resetPasswordForEmail(email,{redirectTo:callback});if(error)throw error;
   authFeedback('If this email belongs to an account, we’ve sent a password reset link. Check your inbox and spam folder.');
  }else if(f.id==='new-password-form'){
   if(!session||!recoveryMode||preview)throw Error('Open a fresh password reset link to continue.');
   if(password.length<12)throw Error('Use at least 12 characters for your password.');
   if(password!==fd.get('confirm_password'))throw Error('The passwords do not match.');
   const epoch=authEpoch;const {error}=await auth.auth.updateUser({password});if(error)throw error;
   if(epoch!==authEpoch||!session)throw Error('Your account changed. Please sign in again.');
   recoveryMode=false;history.replaceState(null,'',root+'/account/');renderAuth();window.dispatchEvent(new Event('auction-auth-change'));
   document.querySelector('#account-status')?.replaceChildren(document.createTextNode('Password saved. You are signed in to your existing account.'));queueAccountLoad();
  }else if(f.id==='profile-form'){
   if(!session||preview)throw Error('Return to your own account to edit your details.');
   const name=String(fd.get('full_name')||'').trim();if(!name||name.length>100)throw Error('Enter your name (up to 100 characters).');
   const epoch=authEpoch;const {data,error}=await auth.auth.updateUser({data:{full_name:name}});if(error)throw error;
   if(epoch!==authEpoch||!session)throw Error('Your account changed. Please sign in again.');
   session={...session,user:data.user};renderAuth();authFeedback('Your name has been saved.',false,target);
  }
 }catch(error){authFeedback(error.status===429?'Please wait a minute before trying again.':error.message||'Could not complete this request. Please try again.',true,target);}
 finally{f.querySelectorAll('input[type=password]').forEach(e=>{e.value='';});authBusy=false;if(submit)submit.disabled=false;}
}
document.addEventListener('submit',async e=>{
 const f=e.target;
 const identityForms=['sign-in-form','register-form','reset-password-form','magic-link-form','new-password-form','profile-form'];
 if(!f.dataset.noteForm&&!identityForms.includes(f.id)&&f.id!=='save-search-form')return;
 e.preventDefault();
 if(identityForms.includes(f.id)){await submitIdentity(f);return;}
 try{
  await initialized;
  if(f.dataset.noteForm){
   if(!can('notes')||!can('bid_targets')){access('notes');return;}
   const fd=new FormData(f),id=f.dataset.noteForm,patch={notes:String(fd.get('notes')||''),target_price:fd.get('target_price')===''?null:Number(fd.get('target_price'))};
   await api('/api/account/workspace/'+id,'PUT',patch);state.properties[id]={...state.properties[id],...patch};notice('Note and bid target saved');
  }
  if(f.id==='save-search-form'){
   if(!can('saved_searches')){f.closest('dialog').close();access('saved_searches');return;}
   const s={id:crypto.randomUUID(),name:String(new FormData(f).get('name')).trim(),query:searchQuery().toString()};
   if(!s.name||!s.query)return;
   await api('/api/account/searches/'+s.id,'PUT',s);state.searches.unshift(s);f.closest('dialog').close();render();notice('Search saved to your account');
  }

 }catch(err){notice(err.message);}
});
document.querySelector('#import-workspace')?.addEventListener('change',async e=>{
 try{
  await initialized;if(session)throw Error('Sign out to open an earlier device backup; account data is unchanged.');
  const f=e.target.files[0];if(!f)return;if(f.size>2000000)throw Error('Workspace file is too large');
  const v=JSON.parse(await f.text());if(v.schema_version!==1||!v.properties||typeof v.properties!=='object'||!Array.isArray(v.searches))throw Error('Choose an Auction Geek workspace export');
  state={...state,properties:{...state.properties,...v.properties},searches:[...state.searches,...v.searches].slice(0,100),events:state.events};persist();render();notice('Earlier records opened. Paid monitoring remains paused.');
 }catch(err){notice(err.message);}
});
async function loadAccount(){
 document.querySelector('#account-retry')?.setAttribute('hidden','');
 const userId=session?.user?.id;
 const epoch=authEpoch;
 const remote=await api('/api/account');
 // A response started before sign-out must not restore the previous customer's UI.
 if(!userId||session?.user?.id!==userId)return;
 checkoutAccount=remote;checkoutFailed=false;
 features=new Set(remote.features||[]);state=empty();
 for(const p of remote.workspace.properties)state.properties[p.property_id]={...p,property:p.property};
 for(const id of remote.saved_properties)state.properties[id]={...state.properties[id],saved:true,property:index[id]||state.properties[id]?.property};
 state.searches=remote.workspace.saved_searches.map(s=>({...s,id:s.search_id}));state.events=remote.workspace.events;
 const credits=document.querySelector('#report-credit-balance'),balance=remote.report_credits;
 if(credits&&balance)credits.textContent=balance.period_end?`${balance.remaining} of ${balance.allowance} included report credits available until ${new Date(balance.period_end*1000).toLocaleDateString('en-GB')}. Unused credits do not roll over.`:'No included report credits are available. Full Investment Reports remain under quality review.';
 const reviews=document.querySelector('#account-reviews');
 if(reviews)reviews.innerHTML=remote.workspace.reviews.map(r=>`<p><a href="${root}/due-diligence/?review=${encodeURIComponent(r.id)}">Saved property research · ${new Date(r.created_at*1000).toLocaleDateString('en-GB')}</a></p>`).join('');
 const evidence=document.querySelector('#account-evidence');
 if(evidence){
  evidence.replaceChildren();
  for(const review of remote.workspace.reviews.filter(r=>r.purchased_access)){
   const p=document.createElement('p'),a=document.createElement('a');a.href=root+'/due-diligence/?review='+encodeURIComponent(review.id)+'#supporting-evidence';
   a.textContent='Supporting evidence · report saved '+new Date(review.created_at*1000).toLocaleDateString('en-GB');p.append(a);evidence.append(p);
  }
  if(!evidence.childElementCount)evidence.textContent='Supporting evidence for purchased reports will appear here. Public sources are listed at the end of each Free Property Snapshot.';
 }
 document.querySelector('#owner-controls')?.toggleAttribute('hidden',!remote.is_owner);
 if(remote.is_owner){
  let tier='';try{tier=sessionStorage.getItem('auction-owner-preview')||'';}catch(_){}
  if(tier){
   try{const nextPreview=await api('/api/admin/preview/'+encodeURIComponent(tier));if(session?.user?.id!==userId)return;preview=nextPreview;features=new Set(preview.features);state=empty();}
   catch(_){if(authEpoch!==epoch)return;preview=null;try{sessionStorage.removeItem('auction-owner-preview');}catch(_){} }
  }
  if(session?.user?.id!==userId)return;
  const previewSelect=document.querySelector('#owner-preview');if(previewSelect)previewSelect.value=preview?.plan||'';
  const previewStatus=document.querySelector('#owner-preview-status');if(previewStatus)previewStatus.textContent=preview?'Read-only customer preview: no saving, payments, uploads or purchased-report access.':'Owner account. Select a tier to preview customer access.';
 }
 document.querySelector('#owner-sandbox-billing')?.toggleAttribute('hidden',!remote.is_owner||!!preview);
 document.querySelector('#owner-monitoring')?.toggleAttribute('hidden',!remote.is_owner||!!preview);
 document.querySelector('#owner-report-recovery')?.toggleAttribute('hidden',!remote.is_owner||!!preview);
 const name=config?.plans?.[preview?.plan||remote.plan]?.name||preview?.plan||remote.plan;
 document.querySelector('#account-status')?.replaceChildren(document.createTextNode(preview?'Read-only preview · '+name+'. Your account and purchases are unchanged.':'Signed in · '+name+' account. Your workspace is private to your account.'));
 renderAuth();
 const billing=remote.billing,manage=document.querySelector('#account-billing'),billingNotice=document.querySelector('#billing-status');
 const canManage=!!billing?.has_customer&&!preview&&(config.billing_enabled||remote.is_owner);
 if(manage){manage.toggleAttribute('hidden',!canManage);manage.textContent=billing?.payment_required?'Update payment method & invoices':'Manage subscription & invoices';}
 if(billingNotice){
  billingNotice.toggleAttribute('hidden',!billing?.payment_required||!!preview);
  billingNotice.textContent=billing?.payment_required?'Your membership payment needs attention. Paid monitoring and new report credits are paused. Your shortlist and previously paid reports remain available. '+(canManage?'Use Update payment method & invoices to resolve payment, then check your membership again.':'Contact team@auctiongeek.co.uk for help with payment.') : '';
 }
 if(preview&&reviews)reviews.replaceChildren(document.createTextNode('Purchased reports are excluded from customer previews.'));
 if(preview&&evidence)evidence.replaceChildren(document.createTextNode('Purchased evidence is excluded from customer previews.'));
 const current=document.querySelector('[data-current-property]')?.dataset.currentProperty;
 if(current)state.recent=[current];render();
}
async function loadMonitoringStatus(){
 const box=document.querySelector('#owner-monitoring'),output=document.querySelector('#owner-monitoring-status');
 if(!box||box.hidden||!output||preview||!checkoutAccount?.is_owner)return;
 const epoch=authEpoch;
 output.textContent='Checking monitoring status…';
 try{
  const result=await api('/api/admin/monitoring');
  if(epoch!==authEpoch||!session||preview)return;
  const finished=Number(result.finished_at),started=Number(result.started_at),now=Date.now()/1000;
  if(result.status==='completed'&&finished>0){
   output.textContent='Last check completed '+new Date(finished*1000).toLocaleString('en-GB')+'.';
   if(now-finished>2700)output.textContent+=' No completed check in the last 45 minutes; investigate the scheduler.';
   if(result.details?.generated_at)output.textContent+=' Catalogue snapshot: '+new Date(result.details.generated_at).toLocaleString('en-GB')+'.';
  }else if(result.status==='running')output.textContent=started>0&&now-started>900?'The last check was interrupted or is overdue. The next scheduled run can retry.':'A monitoring check is running.';
  else if(result.status==='failed')output.textContent='The last check failed. Earlier observations were retained; inspect the service logs before relying on new updates.';
  else output.textContent='No completed monitoring check is recorded yet.';
 }catch(_){if(epoch===authEpoch&&session)output.textContent='Monitoring status could not be loaded. This does not confirm a failed check; try Refresh status.';}
}
document.querySelector('#owner-monitoring')?.addEventListener('toggle',e=>{if(e.target.open)loadMonitoringStatus();});
document.querySelector('#owner-monitoring-refresh')?.addEventListener('click',loadMonitoringStatus);
async function loadReportJobs(){
 const box=document.querySelector('#owner-report-recovery'),output=document.querySelector('#owner-report-status');
 if(!box||box.hidden||!output||preview||!checkoutAccount?.is_owner)return;
 const epoch=authEpoch;output.textContent='Checking report jobs…';
 try{
  const result=await api('/api/admin/report-usage');
  if(epoch!==authEpoch||!session||preview)return;
  output.replaceChildren();
  const jobs=result.attempts.filter(r=>r.status==='processing'||r.status==='interrupted');
  if(!jobs.length){output.textContent='No processing or interrupted attempts in the latest 200 records.';return;}
  for(const job of jobs){
   const entry=document.createElement('div'),label=document.createElement('p');
   label.style.overflowWrap='anywhere';label.textContent=`Report ${job.review_id}, attempt ${job.attempt}: ${job.status}.`;
   entry.append(label);
   if(job.recovery_available){
    const confirmation=document.createElement('label'),check=document.createElement('input'),button=document.createElement('button');
    check.type='checkbox';confirmation.append(check,document.createTextNode(' I checked provider activity and confirmed the previous worker has stopped.'));
    button.type='button';button.className='button outline';button.textContent='Allow customer retry';button.disabled=true;
    check.addEventListener('change',()=>{button.disabled=!check.checked;});
    button.addEventListener('click',async()=>{
     if(epoch!==authEpoch||preview||!checkoutAccount?.is_owner||!check.checked)return;
     button.disabled=true;
     try{
      const body=new FormData();body.set('attempt',job.attempt);body.set('worker_stopped','true');
      await window.AuctionWorkspace.upload('/api/admin/reviews/'+encodeURIComponent(job.review_id)+'/recover',body);
      if(epoch===authEpoch&&session&&!preview)await loadReportJobs();
     }catch(error){if(epoch===authEpoch&&session&&!preview){label.textContent=error.message;button.disabled=!check.checked;}}
    });
    entry.append(confirmation,button);
   }
   if(job.status==='interrupted')entry.append(document.createTextNode('Reconcile any provider usage before closing this attempt.'));
   output.append(entry);
  }
 }catch(_){if(epoch===authEpoch&&session&&!preview)output.textContent='Report status could not be loaded. Try again.';}
}
document.querySelector('#owner-report-recovery')?.addEventListener('toggle',e=>{if(e.target.open)loadReportJobs();});
document.querySelector('#owner-report-refresh')?.addEventListener('click',loadReportJobs);
document.querySelector('#owner-preview')?.addEventListener('change',async e=>{
 try{
  await initialized;
  const plan=e.target.value;
  if(plan)await api('/api/admin/preview/'+encodeURIComponent(plan));
  try{if(plan)sessionStorage.setItem('auction-owner-preview',plan);else sessionStorage.removeItem('auction-owner-preview');}catch(_){throw Error('Preview requires session storage.');}
  location.reload();
 }catch(err){notice(err.message);}
});
async function initialize(){
 try{const r=await fetch(root+'/workspace-index.json',{signal:typeof AbortSignal!=='undefined'?AbortSignal.timeout(15000):undefined});if(!r.ok)throw Error();const data=await r.json();index=Object.fromEntries(data.rows.map(r=>[r.id,r]));render();}
 catch(_){notice('Property workspace details are unavailable. Your earlier records remain intact.');}
 try{
  const r=await fetch(root+'/platform-config.json',{cache:'no-store'});if(!r.ok)throw Error();config=await r.json();
  if(config.accounts_enabled&&window.AuctionIdentity){
   auth=window.AuctionIdentity.createClient(config.supabase_url,config.supabase_key,{auth:{flowType:'pkce'}});
   auth.auth.onAuthStateChange((event,next)=>{
    if(event==='PASSWORD_RECOVERY')recoveryMode=true;
    const changed=updateSession(next);
    if(next&&changed&&!authRestoring)queueAccountLoad();
   });
   try{await refreshSession();}catch(_){authFeedback('Your sign-in link could not be completed. Request a fresh link or sign in with your password.',true);}
   authRestoring=false;
   if(session){try{await loadAccount();}catch(_){workspaceFailed();}}

  }
 }catch(_){features.clear();notice('Account services are unavailable. Free property search remains available.');}
 renderAuth();render();
 const params=new URLSearchParams(location.hash?.slice(1)||'');
 if(params.has('error')){history.replaceState(null,'',root+'/account/');authFeedback('This email link has expired or has already been used. Request a fresh link or sign in with your password.',true);}
}
window.AuctionWorkspace={api,register:rows=>{for(const r of rows)index[r.id]=r;render();},signedIn,canReturnToReport:()=>signedIn()&&!recoveryMode&&!preview,config:()=>config,upload:async(path,body)=>{
 if(preview)throw Error('Uploads are disabled in customer preview.');
 // Investigation has a bounded 15-minute provider budget plus document work.
 // A browser's ordinary one-minute account timeout must not abandon that job.
 const reportRun=/^\/api\/(?:account|admin)\/reviews\/[^/]+\/(?:analyse|validate)$/.test(path);
 const timeout=reportRun?1200000:path==='/api/account/reviews'?300000:60000;
 return accountRequest(path,{method:'POST',body,signal:typeof AbortSignal!=='undefined'?AbortSignal.timeout(timeout):undefined});
},download:async(path)=>{
 if(preview)throw Error('Purchased-report downloads are disabled in customer preview.');
 return accountRequest(path,{},'blob');
}};
new MutationObserver(renderButtons).observe(document.querySelector('#board-results')||document.createElement('div'),{childList:true});
const initialized=initialize();render();
})();

