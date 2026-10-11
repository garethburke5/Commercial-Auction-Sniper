(()=>{
'use strict';
const panel=document.querySelector('#native-review');if(!panel)return;
const $=id=>document.getElementById(id),params=new URLSearchParams(location.search);
let id=params.get('review'),epoch=0,last=null;
const ready=()=>window.AuctionWorkspace?.signedIn();
const progress=$('review-progress'),snapshotForm=$('review-snapshot'),uploadForm=$('review-upload');
const confirmForm=$('review-confirm'),scopeForm=$('review-scope');
const text=(id,value)=>{$(id).textContent=value||'';};
if(params.get('property')){$('review-url-label').hidden=true;snapshotForm.elements.lot_url.required=false;$('review-selected').hidden=false;}
function show(r){
 id=r.id;last=r;const s=r.scope,state=r.analysis_state||'complete',complete=state==='complete';
 $('acquisition-result').innerHTML=r.html;
 snapshotForm.hidden=true;confirmForm.hidden=state!=='awaiting_confirmation';scopeForm.hidden=state!=='awaiting_scope';
 const accepted=!s||s.accepted;
 $('unlock-review').hidden=!accepted||r.access==='full'||r.processing_allowed||!AuctionWorkspace.config()?.billing_enabled||r.report?.quality_status?.purchase_available!==true;
 $('redeem-review').hidden=!accepted||r.access==='full'||r.processing_allowed||r.report?.quality_status?.purchase_available!==true;
 uploadForm.hidden=!r.processing_allowed;
 uploadForm.elements.files.required=!!(s?.pack_expected||s?.parent_review_id);
 $('download-review').hidden=false;
 $('download-review-docx').hidden=r.access!=='full'||!complete;
 $('download-review-pdf').hidden=r.access!=='full'||!complete||!r.report?.investigation;
 $('update-review-pack').hidden=!r.pack_update_available;
 if(s){
  confirmForm.elements.address.value=s.property;
  confirmForm.elements.address.readOnly=s.identity_confirmed;
  if(s.url&&/^https:\/\//.test(s.url)){$('review-source').href=s.url;}else $('review-source').removeAttribute('href');
  text('review-scope-property',s.property);
  text('review-evidence-counts',`Available now: auction particulars; ${s.banked_history_records} banked history records; ${s.banked_comparable_candidates} comparable candidates. Source date: ${s.source_as_of||'not recorded'}.`);
  text('review-scope-investigation',s.investigation);text('review-scope-limits',s.limits);text('review-update-policy',s.update_policy);
  scopeForm.elements.pack_expected.checked=s.pack_expected;
  scopeForm.elements.pack_expected.disabled=!!s.parent_review_id;
 }
 $('review-version-links').replaceChildren();
 for(const [rid,label] of [[s?.parent_review_id,'Open original report'],[r.pack_update_id,'Open legal-pack update']]){
  if(rid){const a=document.createElement('a');const u=new URL(location.href);u.search='';u.searchParams.set('review',rid);a.href=u.href;a.textContent=label;$('review-version-links').append(a);}
 }
 progress.textContent=state==='awaiting_confirmation'?'Check and confirm the property before continuing.':
  state==='awaiting_scope'?'Review and accept the scope. No payment or paid investigation has started.':
  state==='requires_review'?'Analysis is awaiting source-quality review. Your purchase is retained.':
  r.processing_allowed?'Purchase or credit verified. Start the investigation; documents are optional unless included in your chosen scope.':
  r.access==='full'?'Full Investment Report saved to My Auction Geek.':
  'Free Property Snapshot saved. '+(r.report?.quality_status?.message||'');
 const url=new URL(location.href);url.searchParams.set('review',id);history.replaceState(null,'',url);
}
async function act(button,run,message){
 if(!ready()){progress.textContent='Sign in / Register using the link above, then return to prepare your report.';return;}
 const activeEpoch=epoch;if(button)button.disabled=true;progress.textContent=message;
 try{const r=await run();if(activeEpoch===epoch&&ready()&&r)show(r);}catch(e){if(activeEpoch===epoch)progress.textContent=e.message;}finally{if(button)button.disabled=false;}
}
function authChanged(){
 ++epoch;$('review-signin').hidden=!!ready();
 if(!ready()){
  $('acquisition-result').replaceChildren();$('review-version-links').replaceChildren();last=null;
  for(const form of [confirmForm,scopeForm,uploadForm]){form.reset();form.hidden=true;}
  panel.querySelectorAll('.workspace-toolbar button').forEach(b=>b.hidden=true);snapshotForm.hidden=false;progress.textContent='';
 }else if(id)act(null,()=>AuctionWorkspace.api('/api/account/reviews/'+encodeURIComponent(id)),'Loading your saved report…');
}
window.addEventListener('auction-auth-change',authChanged);
authChanged();
snapshotForm.onsubmit=e=>{
 e.preventDefault();const fd=new FormData();
 if(params.get('property'))fd.append('property_id',params.get('property'));else fd.append('lot_url',snapshotForm.elements.lot_url.value.trim());
 act(e.submitter,()=>AuctionWorkspace.upload('/api/account/reviews',fd),'Identifying the property and checking available evidence…');
};
confirmForm.onsubmit=e=>{e.preventDefault();act(e.submitter,()=>AuctionWorkspace.upload('/api/account/reviews/'+id+'/confirm',new FormData(confirmForm)),'Confirming the property…');};
scopeForm.onsubmit=e=>{e.preventDefault();const fd=new FormData(scopeForm);if(last?.scope?.parent_review_id)fd.set('pack_expected','true');act(e.submitter,()=>AuctionWorkspace.upload('/api/account/reviews/'+id+'/scope',fd),'Saving your evidence scope…');};
uploadForm.onsubmit=e=>{e.preventDefault();act(e.submitter,()=>AuctionWorkspace.upload('/api/account/reviews/'+id+'/analyse',new FormData(uploadForm)),'Investigating the property and its available evidence. Keep this page open; scanned documents take longer.');};
$('update-review-pack').onclick=e=>act(e.currentTarget,()=>AuctionWorkspace.api('/api/account/reviews/'+id+'/pack-update','POST'),'Preparing your included document update…');
$('redeem-review').onclick=e=>act(e.currentTarget,async()=>{await AuctionWorkspace.api('/api/account/reviews/'+id+'/redeem','POST');return AuctionWorkspace.api('/api/account/reviews/'+id);},'Verifying your report credit…');
$('unlock-review').onclick=e=>act(e.currentTarget,async()=>{const r=await AuctionWorkspace.api('/api/account/reviews/'+id+'/checkout','POST');if(r.url){location.assign(r.url);return;}return AuctionWorkspace.api('/api/account/reviews/'+id);},'Preparing checkout…');
for(const [button,format] of [['download-review','html'],['download-review-pdf','pdf'],['download-review-docx','docx']]){
 $(button).onclick=()=>act($(button),async()=>{const current=epoch,b=await AuctionWorkspace.download('/api/account/reviews/'+id+'/download?format='+format);if(current!==epoch)return;const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='auction-geek-investment-report.'+format;a.click();URL.revokeObjectURL(a.href);progress.textContent='Report downloaded.';},'Preparing download…');
}
})();
