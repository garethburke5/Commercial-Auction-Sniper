(() => {
'use strict';
const panel=document.querySelector('[data-history-property]');if(!panel)return;
const content=panel.querySelector('[data-history-content]'),preview=panel.querySelector('[data-history-preview]'),status=panel.querySelector('[data-history-status]');
let epoch=0,expiry;
function clear(){epoch++;clearTimeout(expiry);content.replaceChildren();content.hidden=true;preview.hidden=false;status.textContent='';panel.querySelectorAll('[data-history-buy]').forEach(b=>b.disabled=true);}
async function availability(current){
 try{const result=await window.AuctionWorkspace.api('/api/history/products');if(current!==epoch)return;if(result?.purchases_available)panel.querySelectorAll('[data-history-buy]').forEach(b=>{b.disabled=!result.products[b.dataset.historyBuy]?.enabled;});}catch(_){}
}
async function load(){
 clear();const current=epoch,workspace=window.AuctionWorkspace;
 if(!workspace?.canReturnToReport()){status.textContent='Sign in to check your property history access.';return;}
 availability(current);
 status.textContent='Checking your history access…';
 try{
  const result=await workspace.api('/api/history/'+encodeURIComponent(panel.dataset.historyProperty));
  if(current!==epoch||!workspace.canReturnToReport())return;
  content.innerHTML=result.html;content.hidden=false;preview.hidden=true;
  status.textContent=result.access.expires_at?'History access until '+new Date(result.access.expires_at*1000).toLocaleString('en-GB')+'.':'Your premium history access is active.';
  if(result.access.expires_at)expiry=setTimeout(clear,Math.max(0,Math.min(2147483647,result.access.expires_at*1000-Date.now())));
 }catch(error){if(current===epoch)status.textContent=error.message||'We could not check history access. Please try again.';}
}
window.addEventListener('auction-auth-change',()=>{clear();if(window.AuctionWorkspace?.canReturnToReport())load();});
window.addEventListener('pagehide',clear);
window.addEventListener('pageshow',()=>{clear();});
panel.querySelector('[data-history-load]').addEventListener('click',load);
panel.querySelectorAll('[data-history-buy]').forEach(button=>button.addEventListener('click',async()=>{
 const workspace=window.AuctionWorkspace;if(!workspace?.canReturnToReport()){status.textContent='Sign in before purchasing history access.';return;}
 button.disabled=true;
 try{const result=await workspace.api('/api/history/checkout','POST',{product:button.dataset.historyBuy,property_id:panel.dataset.historyProperty});location.assign(result.url);}
 catch(error){status.textContent=error.message;button.disabled=false;}
}));
// Anonymous browsing never calls the private API just to display prices.
if(new URLSearchParams(location.search).get('history_purchase')==='returned')status.textContent='Payment confirmation can take a moment. Sign in and check your history access. Please do not pay again.';
})();
