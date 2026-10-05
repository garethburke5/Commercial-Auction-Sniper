(() => {
'use strict';
const root=document.body.dataset.prefix||'', key='auction-sniper-workspace-v1';
const empty=()=>({properties:{},searches:[],events:[],recent:[]});
let state=empty(), session=null, auth=null, config=null, index={}, features=new Set();
try { state={...state,...JSON.parse(localStorage.getItem(key)||'{}')}; } catch (_) {}
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=v=>typeof v==='number'?'£'+v.toLocaleString('en-GB'):(v||'Not stated');
const can=feature=>!!session&&features.has(feature);
const notice=s=>{let e=document.querySelector('#workspace-message');if(!e){e=document.createElement('p');e.id='workspace-message';e.className='workspace-toast';e.setAttribute('role','status');document.body.append(e);}e.textContent=s;};
function persist(){if(session)return;try{localStorage.setItem(key,JSON.stringify(state));}catch(_){notice('This browser could not save your workspace. Download your stored data for a backup.');}}
async function api(path,method='GET',body){
 if(auth)session=(await auth.auth.getSession()).data.session;
 if(!session||!config?.api_origin)throw Error('Sign in is required');
 const r=await fetch(config.api_origin+path,{method,headers:{Authorization:'Bearer '+session.access_token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});
 if(!r.ok)throw Error((await r.json()).detail||'Could not complete the request');return r.json();
}
function safePath(p){return typeof p==='string'&&p.startsWith('/')&&!p.startsWith('//')?root+p:root+'/properties/';}
function access(feature){
 const dialog=document.querySelector('#access-dialog');if(!dialog)return;
 const save=feature==='save', billing=feature==='subscription';
 const title=save?'Keep your shortlist with a free account':billing?'Your membership, ready when checkout opens':feature==='saved_searches'?'Save this search & get new-match alerts':feature==='watch'?'Watch this property for meaningful changes':'Make this research your own';
 document.querySelector('#access-title').textContent=title;
 document.querySelector('#access-eyebrow').textContent=save?'FREE REGISTERED ACCOUNT':billing?'PLANS & PRICING':'MEMBERSHIP TOOLS';
 document.querySelector('#access-description').textContent=save
  ?'Save is your personal shortlist. Register or sign in for free to keep properties together and return to your research.'
  :billing?'Secure subscription checkout is being activated. The initial monthly prices are shown on Plans & Pricing; no payment will be taken here.'
  :'Available with Premium Investor and Professional & Business.';
 const detail=document.querySelector('#access-detail');detail.replaceChildren();
 const p=document.createElement('p');p.className='small';
 p.textContent=save?(config?.accounts_enabled?'Your shortlist is private to your account.':'Registration is being activated. Free property search and the Acquisition Intelligence Snapshot remain available now.')
  :feature==='watch'?'Follow guide prices, status, auction dates, legal-pack availability and important particulars. Membership monitoring is separate from your free shortlist. Email delivery is being activated.'
  :feature==='saved_searches'?'Keep your applied criteria ready to reopen. New-match email delivery is being activated; normal searching stays free.'
  :billing?'One-off Acquisition Reviews remain separate: a monthly subscription is never required to research one property.'
  :'Keep private notes and a personal bid target alongside the property evidence.';
 detail.append(p);
 const primary=document.querySelector('#access-primary');
 primary.href=root+(save?'/account/':'/plans/');primary.textContent=save?(config?.accounts_enabled?'Register / sign in free →':'Free account information →'):'View Plans & Pricing →';
 if(!dialog.open)dialog.showModal();
}
function renderButtons(){document.querySelectorAll('[data-save],[data-watch]').forEach(b=>{
 const id=b.dataset.save||b.dataset.watch,kind=b.dataset.save?'saved':'watched';
 const on=!!state.properties[id]?.[kind]&&(kind==='saved'||can('watch'));
 const text=kind==='saved'?(on?'✓ Saved':'♡ Save'):(on?'◉ Watching':'◉ Watch');
 if(b.textContent!==text)b.textContent=text;b.setAttribute('aria-pressed',String(on));
});}
function item(row){
 if(!row)return '';const p=state.properties[row.id]||{};
 const edit=can('notes')&&can('bid_targets');
 const notes=edit?`<form data-note-form="${esc(row.id)}"><label>Private note<textarea name="notes" maxlength="10000" rows="3">${esc(p.notes||'')}</textarea></label><label>My target / maximum bid (£)<input type="number" min="0" step="100" name="target_price" value="${esc(p.target_price??'')}"></label><button class="button outline">Save note & target</button></form>`
  :`${p.notes?`<p>${esc(p.notes)}</p>`:''}${p.target_price!=null?`<p>Stored target: ${esc(money(p.target_price))}</p>`:''}<p class="small">Private notes and saved bid targets are membership tools. Your earlier records are preserved.</p><button class="button outline" data-feature="notes">Explore research tools</button>`;
 return `<article class="workspace-card"><div>${row.image_url?`<img src="${esc(row.image_url)}" alt="" loading="lazy" width="112" height="84">`:''}<h3><a href="${esc(safePath(row.path))}">${esc(row.address)}</a></h3><p>${esc(row.source)} · ${esc(row.guide||money(row.guide_price))}</p></div><div class="save-actions"><button data-save="${esc(row.id)}" aria-pressed="${!!p.saved}">${p.saved?'✓ Saved':'♡ Save'}</button><button data-watch="${esc(row.id)}" aria-pressed="${!!p.watched&&can('watch')}">${p.watched&&can('watch')?'◉ Watching':'◉ Watch'}</button></div><details><summary>My notes & bid target</summary>${notes}</details></article>`;
}
function render(){
 renderButtons();if(!document.querySelector('#account-dashboard'))return;
 for(const [kind,el,count]of[['saved','saved-items','saved-count'],['watched','watched-items','watch-count']]){
  const rows=Object.entries(state.properties).filter(([,p])=>p[kind]).map(([id,p])=>index[id]||p.property).filter(Boolean);
  const permitted=kind==='saved'||can('watch');
  document.getElementById(el).innerHTML=permitted?(rows.map(item).join('')||`<p>No ${kind==='saved'?'saved':'watched'} properties yet.</p>`):'<p>Track meaningful changes with Premium Investor or Professional & Business. Earlier watches are preserved and monitoring is paused until membership is active.</p><button class="button outline" data-feature="watch">Explore Watch →</button>';
  document.getElementById(count).textContent=permitted?rows.length:'';
 }
 document.querySelector('#saved-searches').innerHTML=can('saved_searches')?(state.searches.map(s=>`<p><a href="${esc(root+'/properties/?'+s.query)}">${esc(s.name)}</a> <button data-remove-search="${esc(s.id)}" class="textlink">Remove</button></p>`).join('')||'<p>Apply filters on Find property, then Save this search.</p>'):'<p>Save your criteria with membership. Any previously saved criteria are preserved in your stored data.</p><button class="button outline" data-feature="saved_searches">Explore saved searches →</button>';
 document.querySelector('#watch-updates').innerHTML=can('watch')?(state.events.slice(0,50).map(e=>`<article class="watch-event"><b>${esc(e.title)}</b><p><a href="${esc(safePath(e.property?.path))}">${esc(e.property?.address||e.property_id)}</a></p><p>${esc(money(e.before))} → ${esc(money(e.after))}</p><small>Observed ${esc(new Date(e.at||e.created_at*1000).toLocaleDateString('en-GB'))}</small></article>`).join('')||'<p>No changes recorded. Watches begin with the snapshot available when you select Watch.</p>'):'<p>Property-change monitoring is included with membership.</p>';
 document.querySelector('#recent-items').innerHTML=state.recent.slice(0,8).map(id=>item(index[id]||state.properties[id]?.property)).join('')||'<p>Recently viewed properties appear as you research in your account.</p>';
}
async function toggle(id,kind){
 if(kind==='saved'&&!session){access('save');return;}
 if(kind==='watched'&&!can('watch')){access('watch');return;}
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
 if(b.hasAttribute('data-close-dialog')){b.closest('dialog').close();return;}
 try{
  await initialized;
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
   const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify({schema_version:1,...state},null,2)],{type:'application/json'}));a.download='auction-sniper-workspace.json';a.click();URL.revokeObjectURL(a.href);
  }
  if(b.id==='account-signout'){await auth.auth.signOut();session=null;features.clear();state=empty();location.assign(root+'/account/');}
  if(b.dataset.subscribe){
   if(!config?.billing_enabled){access('subscription');return;}
   if(!session){access('save');return;}
   const r=await api('/api/billing/checkout','POST',{plan:b.dataset.subscribe});location.assign(r.url);
  }
  if(b.id==='account-billing'){const r=await api('/api/billing/portal','POST');location.assign(r.url);}
 }catch(err){notice(err.message);}
});
document.addEventListener('submit',async e=>{
 const f=e.target;
 if(!f.dataset.noteForm&&!['sign-in-form','save-search-form'].includes(f.id))return;
 e.preventDefault();
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
  if(f.id==='sign-in-form'){
   if(!auth){access('save');return;}
   const {error}=await auth.auth.signInWithOtp({email:new FormData(f).get('email'),options:{emailRedirectTo:location.origin+root+'/account/'}});notice(error?error.message:'Check your email for the secure sign-in link.');
  }
 }catch(err){notice(err.message);}
});
document.querySelector('#import-workspace')?.addEventListener('change',async e=>{
 try{
  await initialized;if(session)throw Error('Sign out to open an earlier device backup; account data is unchanged.');
  const f=e.target.files[0];if(!f)return;if(f.size>2000000)throw Error('Workspace file is too large');
  const v=JSON.parse(await f.text());if(v.schema_version!==1||!v.properties||typeof v.properties!=='object'||!Array.isArray(v.searches))throw Error('Choose an Auction Sniper workspace export');
  state={...state,properties:{...state.properties,...v.properties},searches:[...state.searches,...v.searches].slice(0,100),events:state.events};persist();render();notice('Earlier records opened. Paid monitoring remains paused.');
 }catch(err){notice(err.message);}
});
async function loadAccount(){
 const remote=await api('/api/account');features=new Set(remote.features||[]);state=empty();
 for(const p of remote.workspace.properties)state.properties[p.property_id]={...p,property:p.property};
 for(const id of remote.saved_properties)state.properties[id]={...state.properties[id],saved:true,property:index[id]||state.properties[id]?.property};
 state.searches=remote.workspace.saved_searches.map(s=>({...s,id:s.search_id}));state.events=remote.workspace.events;
 const reviews=document.querySelector('#account-reviews');
 if(reviews)reviews.innerHTML=remote.workspace.reviews.map(r=>`<p><a href="${root}/due-diligence/?review=${encodeURIComponent(r.id)}">Acquisition Review · ${new Date(r.created_at*1000).toLocaleDateString('en-GB')}</a></p>`).join('');
 const name=config?.plans?.[remote.plan]?.name||remote.plan;
 document.querySelector('#account-status')?.replaceChildren(document.createTextNode('Signed in · '+name+' account. Your workspace is private to your account.'));
 document.querySelector('#sign-in-form')?.setAttribute('hidden','');document.querySelector('#account-signout')?.removeAttribute('hidden');
 if(config.billing_enabled)document.querySelector('#account-billing')?.removeAttribute('hidden');
 const current=document.querySelector('[data-current-property]')?.dataset.currentProperty;
 if(current)state.recent=[current];render();
}
async function initialize(){
 try{const r=await fetch(root+'/workspace-index.json');if(!r.ok)throw Error();const data=await r.json();index=Object.fromEntries(data.rows.map(r=>[r.id,r]));render();}
 catch(_){notice('Property workspace details are unavailable. Your earlier records remain intact.');}
 try{
  const r=await fetch(root+'/platform-config.json',{cache:'no-store'});if(!r.ok)throw Error();config=await r.json();
  if(config.accounts_enabled&&window.AuctionIdentity){
   auth=window.AuctionIdentity.createClient(config.supabase_url,config.supabase_key,{auth:{flowType:'pkce'}});
   session=(await auth.auth.getSession()).data.session;
   document.querySelector('#sign-in-form')?.removeAttribute('hidden');
   if(session)await loadAccount();
   auth.auth.onAuthStateChange((event,next)=>{
    const changed=next?.user?.id!==session?.user?.id;session=next;
    if(!next){features.clear();state=empty();render();}
    else if(changed)queueMicrotask(()=>loadAccount().catch(()=>{features.clear();notice('Account sync is unavailable. Try again shortly.');}));
   });
   if(!session)document.querySelector('#account-status')?.replaceChildren(document.createTextNode('Register or sign in free to save your shortlist. Membership adds monitoring and research tools.'));
  }
 }catch(_){features.clear();notice('Account services are unavailable. Free property search remains available.');}
 render();
}
window.AuctionWorkspace={api,register:rows=>{for(const r of rows)index[r.id]=r;render();},signedIn:()=>!!session,config:()=>config,upload:async(path,body)=>{
 if(auth)session=(await auth.auth.getSession()).data.session;
 if(!session||!config?.api_origin)throw Error('Sign in to save this review');
 const r=await fetch(config.api_origin+path,{method:'POST',headers:{Authorization:'Bearer '+session.access_token},body});if(!r.ok)throw Error((await r.json()).detail||'Processing failed');return r.json();
},download:async(path)=>{
 if(auth)session=(await auth.auth.getSession()).data.session;
 if(!session||!config?.api_origin)throw Error('Sign in to download your review');
 const r=await fetch(config.api_origin+path,{headers:{Authorization:'Bearer '+session.access_token}});if(!r.ok)throw Error('Download unavailable');return r.blob();
}};
new MutationObserver(renderButtons).observe(document.querySelector('#board-results')||document.createElement('div'),{childList:true});
const initialized=initialize();render();
})();
