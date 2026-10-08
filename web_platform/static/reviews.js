(()=>{
const panel=document.querySelector('#native-review');if(!panel)return;
const params=new URLSearchParams(location.search);let id=params.get('review');
const progress=document.querySelector('#review-progress');
const snapshotForm=document.querySelector('#review-snapshot');
const uploadForm=document.querySelector('#review-upload');
function ready(){return window.AuctionWorkspace?.signedIn();}
function show(r){
 id=r.id;document.querySelector('#acquisition-result').innerHTML=r.html;
 const complete=(r.analysis_state||'complete')==='complete';
 document.querySelector('#unlock-review').hidden=r.access==='full'||r.processing_allowed||!AuctionWorkspace.config()?.billing_enabled||r.report?.quality_status?.purchase_available!==true;
 uploadForm.hidden=!r.processing_allowed;
 document.querySelector('#download-review').hidden=false;
 document.querySelector('#download-review-docx').hidden=r.access!=='full'||!complete;
 document.querySelector('#download-review-pdf').hidden=r.access!=='full'||!complete||!r.report?.investigation;
 if(r.processing_allowed)progress.textContent='Payment verified. Upload the legal pack to start your purchased analysis.';
 else if(r.access==='full')progress.textContent='Full review saved to My Auction Sniper.';
 else progress.textContent='Free listing snapshot saved. '+(r.report?.quality_status?.message||'');
 const url=new URL(location.href);url.searchParams.set('review',id);history.replaceState(null,'',url);
}
async function start(){if(!ready())return;panel.hidden=false;if(id){try{show(await AuctionWorkspace.api('/api/account/reviews/'+encodeURIComponent(id)));}catch(e){progress.textContent=e.message;}}}
let attempts=0;const timer=setInterval(()=>{if(ready()||++attempts>=20){clearInterval(timer);start();}},500);
snapshotForm.onsubmit=async e=>{
 e.preventDefault();if(!params.get('property')){progress.textContent='Open Acquisition Intelligence from a property page.';return;}
 const fd=new FormData();fd.append('property_id',params.get('property'));
 progress.textContent='Preparing your listing snapshot.';
 try{show(await AuctionWorkspace.upload('/api/account/reviews',fd));}catch(e){progress.textContent=e.message;}
};
uploadForm.onsubmit=async e=>{
 e.preventDefault();if(!id)return;
 const button=e.target.querySelector('button');button.disabled=true;
 progress.textContent='Analysing your purchased legal pack. Scanned documents take longer; keep this page open.';
 try{show(await AuctionWorkspace.upload('/api/account/reviews/'+encodeURIComponent(id)+'/analyse',new FormData(e.target)));}catch(e){progress.textContent=e.message;}finally{button.disabled=false;}
};
document.querySelector('#unlock-review').onclick=async()=>{try{const r=await AuctionWorkspace.api('/api/account/reviews/'+id+'/checkout','POST');if(r.url)location.assign(r.url);else show(await AuctionWorkspace.api('/api/account/reviews/'+id));}catch(e){progress.textContent=e.message;}};
for(const [button,format] of [['download-review','html'],['download-review-pdf','pdf'],['download-review-docx','docx']]){
 document.querySelector('#'+button).onclick=async()=>{try{const b=await AuctionWorkspace.download('/api/account/reviews/'+id+'/download?format='+format);const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='auction-sniper-acquisition-review.'+format;a.click();URL.revokeObjectURL(a.href);}catch(e){progress.textContent=e.message;}};
}
})();
