/* Evidence is fetched with the existing authenticated API client, never tokens in links. */
(()=>{
'use strict';
// Store identifiers only, for a short sign-in return on this browser. The API
// still checks the signed-in owner and current entitlement on every request.
const root=document.body.dataset.prefix||'',returnKey='auction-evidence-return';
const validID=value=>typeof value==='string'&&/^[A-Za-z0-9_-]{1,100}$/.test(value);
const params=new URLSearchParams(location.search);
if(location.pathname===root+'/account/'){
 let pending;
 try{pending=JSON.parse(localStorage.getItem(returnKey)||'null');}catch(_){}
 if(validID(params.get('return_review'))){
  pending={review:params.get('return_review'),evidence:validID(params.get('return_evidence'))?params.get('return_evidence'):null,expires:Date.now()+30*60*1000};
  try{localStorage.setItem(returnKey,JSON.stringify(pending));}catch(_){}
 }
 const resume=()=>{
  if(!pending||!validID(pending.review)||pending.expires<Date.now()||!window.AuctionWorkspace?.canReturnToReport())return;
  const query=new URLSearchParams({review:pending.review});if(validID(pending.evidence))query.set('evidence',pending.evidence);
  try{localStorage.removeItem(returnKey);}catch(_){}
  pending=null;location.assign(root+'/due-diligence/?'+query+'#supporting-evidence');
 };
 window.addEventListener('auction-auth-change',resume);resume();return;
}
const signin=document.querySelector('#review-signin a');
if(signin&&validID(params.get('review'))){
 const query=new URLSearchParams({return_review:params.get('review')});if(validID(params.get('evidence')))query.set('return_evidence',params.get('evidence'));
 signin.href=root+'/account/?'+query;
}
const panel=document.getElementById('supporting-evidence');if(!panel)return;
const status=document.getElementById('evidence-status'),list=document.getElementById('evidence-list'),detail=document.getElementById('evidence-detail');
let review=null,epoch=0,request=0;
const ready=()=>window.AuctionWorkspace?.signedIn();
const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
const safeURL=value=>{try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)&&!u.username&&!u.password?u.href:null;}catch(_){return null;}};
function sourceLink(url,label){const href=safeURL(url);if(!href)return el('span','Original source link unavailable');const a=el('a',label);a.href=href;a.target='_blank';a.rel='noopener noreferrer';return a;}
function clear(){++epoch;++request;review=null;panel.hidden=true;list.replaceChildren();detail.replaceChildren();status.textContent='';}
function current(e,r,q){return e===epoch&&r===review&&q===request&&ready();}
async function openEvidence(eid){
 if(!review||!ready())return;
 const e=epoch,r=review,q=++request;detail.replaceChildren();status.textContent='Loading the supporting evidence…';
 try{
  const data=await AuctionWorkspace.api('/api/account/reviews/'+encodeURIComponent(r)+'/evidence/'+encodeURIComponent(eid));
  if(!current(e,r,q))return;
  detail.append(el('h3',data.label),el('p','Document: '+(data.document||data.label)));
  if(data.url)detail.append(sourceLink(data.url,'Open original source ↗'));
  if(data.private)detail.append(el('p','This is retained extracted text, not an image of the original document. Page numbers refer to the supplied PDF. Check the original for handwriting, layout and plans.'));
  for(const page of data.pages||[]){
   const card=el('section');card.className='evidence-page';card.append(el('h4',page.number?'Page '+page.number:'Page number not recorded'));
   if(page.ocr)card.append(el('p','This text was extracted using OCR and may contain reading errors.'));
   if(page.unmatched_extract)card.append(el('p','The cited extract could not be matched exactly to the retained page text. No highlight has been assumed.'));
   for(const text of page.extracts||[])card.append(el('blockquote',text));
   if(page.segments?.length){
    const context=el('details'),p=el('p');context.append(el('summary','Read the retained page text'));
    for(const part of page.segments)p.append(part.highlighted?el('mark',part.text):document.createTextNode(part.text));
    context.append(p);card.append(context);
   }else card.append(el('p','Only this extract was retained; the complete page is not available here.'));
   detail.append(card);
  }
  status.textContent='';const url=new URL(location.href);url.searchParams.set('evidence',eid);url.hash='supporting-evidence';history.replaceState(null,'',url);
  detail.focus();detail.scrollIntoView({block:'start',behavior:'auto'});
 }catch(error){if(current(e,r,q)){detail.replaceChildren();list.replaceChildren();status.textContent=error.message||'The evidence could not be opened.';}}
}
async function browse(){
 if(!review||!ready())return;
 const e=epoch,r=review,q=++request;status.textContent='Loading supporting sources…';list.replaceChildren();
 try{
  const data=await AuctionWorkspace.api('/api/account/reviews/'+encodeURIComponent(r)+'/evidence');
  if(!current(e,r,q))return;
  const groups=new Map();
  for(const source of data.sources||[]){
   const key=source.document||source.label;
   if(!groups.has(key)){const group=el('details');group.append(el('summary',source.label));groups.set(key,group);list.append(group);}
   const group=groups.get(key),p=el('p');
   if(source.url)p.append(sourceLink(source.url,'Open original source ↗'));
   else if(source.available){const button=el('button',(source.page_label||'Retained extract')+(source.contexts?.[0]?' — '+source.contexts[0]:''));button.type='button';button.className='textlink';button.onclick=()=>openEvidence(source.id);p.append(button);}
   else p.textContent=(source.page_label||'Page not recorded')+' — '+(source.restricted?'Access restricted; consult the original document.':'No shareable extract is retained.');
   group.append(p);
  }
  status.textContent=groups.size?'Choose a document to see its references.':'No supporting sources are available for this report.';
 }catch(error){if(current(e,r,q)){detail.replaceChildren();status.textContent=error.message||'The source list could not be opened.';}}
}
document.getElementById('show-report-evidence').onclick=browse;
document.getElementById('acquisition-result').addEventListener('click',event=>{
 const link=event.target.closest('a[data-evidence-id]');if(!link||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;
 event.preventDefault();if(!panel.hidden)openEvidence(link.dataset.evidenceId);
});
window.addEventListener('auction-auth-change',clear);
window.addEventListener('auction-report-loaded',event=>{
 clear();review=event.detail.id;panel.hidden=!event.detail.available;
 const params=new URLSearchParams(location.search);
 if(!panel.hidden&&params.get('review')===review){
  if(params.get('evidence'))openEvidence(params.get('evidence'));
  else if(location.hash==='#supporting-evidence')browse();
 }
});
})();
