(()=>{
'use strict';
const panel=document.querySelector('#native-review');if(!panel)return;
const $=id=>document.getElementById(id),params=new URLSearchParams(location.search);
let id=params.get('review'),epoch=0,last=null;
window.addEventListener('auction-payment-availability',()=>{if(last)show(last);});
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
 $('unlock-review').hidden=!accepted||r.purchase_verified||r.access==='full'||r.processing_allowed||!AuctionWorkspace.config()?.report_checkout_available||r.report?.quality_status?.purchase_available!==true;
 $('redeem-review').hidden=!accepted||r.purchase_verified||r.access==='full'||r.processing_allowed||r.report?.quality_status?.purchase_available!==true;
 uploadForm.hidden=!(r.processing_allowed||r.owner_validation_allowed);
 uploadForm.querySelector('button[type="submit"]').textContent=r.owner_validation_allowed?'Run private validation report':'Generate my Full Investment Report';
 $('review-validation-note').hidden=!(r.owner_validation_allowed||r.validation);
 const metrics=r.validation_metrics,usage=metrics?.provider_usage;
 $('review-validation-usage').hidden=!metrics;
 text('review-validation-usage',metrics?`Validation usage: ${usage?.calls??'unknown'} provider requests; ${usage?.input_tokens??'unknown'} recorded input tokens; ${usage?.output_tokens??'unknown'} recorded output tokens; ${usage?.search_calls??'unknown'} recorded web searches. ${usage?.complete===false?'Usage measurement is incomplete; these counts do not establish the full charge. ':''}${metrics.failure_reason||''} ${usage?.error_category||''} Cost reconciliation: ${metrics.cost?.status||'pending'}.`:'');
 uploadForm.elements.files.required=!!(s?.pack_expected||s?.parent_review_id);
 $('download-review').hidden=false;
 const diagnostic=r.access==='validation';
 $('download-review-docx').hidden=!diagnostic&&!r.free_snapshot_available&&(r.access!=='full'||!complete);
 $('download-review-pdf').hidden=(!diagnostic&&!r.free_snapshot_available&&(r.access!=='full'||!complete))||!r.report?.investigation;
 $('download-validation-json').hidden=!diagnostic;
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
 progress.textContent=diagnostic?'Private validation saved. Approval remains withheld. '+(r.validation_issues||[]).join(' '):
  r.owner_validation_allowed?'Owner validation is available. It uses the production investigation engine and incurs OpenAI usage; no report credit or payment will be taken.':
  state==='awaiting_confirmation'?'Check and confirm the property before continuing.':
  state==='awaiting_scope'?'Review and accept the scope. No payment or paid investigation has started.':
  state==='requires_review'?'Analysis is awaiting source-quality review. Your purchase is retained.':
  state==='processing'?(r.processing_overdue?'Your investigation is taking longer than expected. Contact team@auctiongeek.co.uk so we can check it safely. Your purchase is retained; do not pay again.':'Your investigation is in progress. Your purchase is retained; do not pay again.'):
  state==='failed'&&!r.processing_allowed?'Your investigation needs support review. Contact team@auctiongeek.co.uk. Your purchase is retained.':
  r.processing_allowed?'Purchase or credit verified. Start the investigation; documents are optional unless included in your chosen scope.':
  r.access==='full'?'Full Investment Report saved to My Auction Geek.':
  'Report preparation saved. '+(r.report?.quality_status?.message||'');
 const url=new URL(location.href);url.searchParams.set('review',id);history.replaceState(null,'',url);
 window.dispatchEvent(new CustomEvent('auction-report-loaded',{detail:{id,available:!!r.supporting_evidence_available}}));
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
  $('review-validation-note').hidden=true;$('review-validation-usage').hidden=true;text('review-validation-usage','');
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
uploadForm.onsubmit=e=>{e.preventDefault();const path=last?.owner_validation_allowed?'/api/admin/reviews/'+id+'/validate':'/api/account/reviews/'+id+'/analyse';act(e.submitter,async()=>{
 try{return await AuctionWorkspace.upload(path,new FormData(uploadForm));}
 catch(error){
  // Read the saved outcome after a network/provider failure; never retry a
  // chargeable investigation automatically or invite a duplicate submission.
  try{const saved=await AuctionWorkspace.api('/api/account/reviews/'+encodeURIComponent(id));if(['processing','failed','requires_review','complete'].includes(saved.analysis_state))return saved;}catch(_){}
  throw error;
 }
},'Investigating the property and its available evidence. Keep this page open; scanned documents take longer.');};
$('update-review-pack').onclick=e=>act(e.currentTarget,()=>AuctionWorkspace.api('/api/account/reviews/'+id+'/pack-update','POST'),'Preparing your included document update…');
$('redeem-review').onclick=e=>act(e.currentTarget,async()=>{await AuctionWorkspace.api('/api/account/reviews/'+id+'/redeem','POST');return AuctionWorkspace.api('/api/account/reviews/'+id);},'Verifying your report credit…');
$('unlock-review').onclick=e=>act(e.currentTarget,async()=>{const r=await AuctionWorkspace.api('/api/account/reviews/'+id+'/checkout','POST');if(r.url){location.assign(r.url);return;}return AuctionWorkspace.api('/api/account/reviews/'+id);},'Preparing checkout…');
for(const [button,format] of [['download-review','html'],['download-review-pdf','pdf'],['download-review-docx','docx'],['download-validation-json','json']]){
 $(button).onclick=()=>act($(button),async()=>{const current=epoch,validation=last?.access==='validation',path=validation?'/api/admin/reviews/'+id+'/validation-download':'/api/account/reviews/'+id+'/download',b=await AuctionWorkspace.download(path+'?format='+format);if(current!==epoch)return;const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=(validation?'auction-geek-private-validation':last?.free_snapshot_available?'auction-geek-property-snapshot':'auction-geek-investment-report')+'.'+format;a.click();URL.revokeObjectURL(a.href);progress.textContent='Report downloaded.';},'Preparing download…');
}
})();
