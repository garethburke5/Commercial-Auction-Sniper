/* Progressively enhance the same server-rendered Auction Sniper cards. */
(() => {
  'use strict';
  const cash = value => new Intl.NumberFormat('en-GB', {style:'currency',currency:'GBP',maximumFractionDigits:0}).format(value);
  function targetPrices(value) {
    const target=Number(value);
    if (!Number.isFinite(target) || target<1 || target>30) return;
    document.querySelectorAll('[data-rent]').forEach(card => {
      const rent=Number(card.dataset.rent), price=card.querySelector('.target-price'), label=card.querySelector('.target-label');
      if (label) label.textContent=String(target);
      if (price) price.textContent=rent>0 ? cash(rent/(target/100)) : 'Not stated';
    });
  }
  const propertyTarget=document.querySelector('#property-target');
  if (propertyTarget) propertyTarget.addEventListener('input',()=>targetPrices(propertyTarget.value));
  const research=document.querySelector('#open-research');
  if (research) research.addEventListener('click',()=>{
    const frame=document.querySelector('#research-frame');
    frame.src=research.dataset.src;frame.hidden=false;research.remove();
  });
  const board=document.querySelector('#property-board');
  if (!board) return;
  const form=document.querySelector('#property-filters'), results=document.querySelector('#board-results');
  const counter=document.querySelector('#result-count'), pager=document.querySelector('#board-pager');
  const error=document.querySelector('#board-error'), size=document.querySelector('#page-size'), sort=document.querySelector('#sort-order');
  const target=document.querySelector('#target-yield');
  const chunks=new Map();let indexPromise=null, request=0;
  const control=name=>form.elements.namedItem(name);
  const sources=()=>Array.from(control('source').selectedOptions).map(o=>o.value);
  async function loadIndex(){
    if (!indexPromise) indexPromise=fetch(board.dataset.index).then(r=>{if(!r.ok)throw Error('Index unavailable');return r.json();}).catch(e=>{indexPromise=null;throw e;});
    return (await indexPromise).rows;
  }
  async function loadChunk(name){
    if (!chunks.has(name)) chunks.set(name,fetch(new URL(name,new URL(board.dataset.index,location.href))).then(r=>{if(!r.ok)throw Error('Catalogue changed');return r.json();}).catch(e=>{chunks.delete(name);throw e;}));
    return chunks.get(name);
  }
  function parameters(page){
    const p=new URLSearchParams();
    ['q','max','yield','tenure','status'].forEach(k=>{const v=control(k).value.trim();if(v)p.set(k,v);});
    sources().forEach(v=>p.append('source',v));
    if(!control('unknown').checked)p.set('unknown','0');
    if(target.value!=='10')p.set('target',target.value);
    if(size.value!=='50')p.set('size',size.value);
    if(sort.value!=='date')p.set('sort',sort.value);
    if(page>1)p.set('page',page);
    return p;
  }
  function restore(){
    const p=new URLSearchParams(location.search);
    form.reset();size.value='50';sort.value='date';
    ['q','max','yield','tenure','status','target'].forEach(k=>{if(p.has(k))control(k).value=p.get(k);});
    Array.from(control('source').options).forEach(o=>{o.selected=p.getAll('source').includes(o.value);});
    control('unknown').checked=p.get('unknown')!=='0';
    if(['10','50','100','All'].includes(p.get('size')))size.value=p.get('size');
    if(['date','price','yield'].includes(p.get('sort')))sort.value=p.get('sort');
    return Math.max(1,parseInt(p.get('page')||board.dataset.page,10)||1);
  }
  function matches(row){
    const terms=control('q').value.toLowerCase().trim().split(/[\s,;]+/).filter(Boolean);
    const address=row.address.toLowerCase();
    if(!terms.every(term=>address.includes(term)))return false;
    const selected=sources();if(selected.length && !selected.includes(row.source))return false;
    const tenure=control('tenure').value.toLowerCase();if(tenure && (row.tenure||'').toLowerCase()!==tenure)return false;
    const status=control('status').value;if(status==='available'&&row.unavailable)return false;
    if(status==='unavailable'&&!row.unavailable)return false;
    const unknown=control('unknown').checked,max=Number(control('max').value),min=Number(control('yield').value);
    if(max>0 && (row.guide_price==null ? !unknown : row.guide_price>max))return false;
    if(min>0 && (row.giy==null ? !unknown : row.giy<min))return false;
    return true;
  }
  function sorted(rows){
    if(sort.value==='price')return rows.sort((a,b)=>(a.guide_price??Infinity)-(b.guide_price??Infinity));
    if(sort.value==='yield')return rows.sort((a,b)=>(b.giy??-Infinity)-(a.giy??-Infinity));
    return rows;
  }
  async function render(page=1,writeUrl=true){
    const sequence=++request;error.hidden=true;results.setAttribute('aria-busy','true');
    try{
      const rows=sorted((await loadIndex()).filter(matches));
      const pageSize=size.value==='All'?Math.max(rows.length,1):Number(size.value);
      const pages=Math.max(1,Math.ceil(rows.length/pageSize));page=Math.min(pages,Math.max(1,page));
      const start=(page-1)*pageSize,visible=rows.slice(start,start+pageSize);
      const names=[...new Set(visible.map(r=>r.chunk))];
      const loaded=await Promise.all(names.map(loadChunk));
      if(sequence!==request)return;
      const html=Object.assign({},...loaded);
      if(visible.some(r=>!html[r.id]))throw Error('Catalogue changed');
      // Only build-generated escaped HTML from our own origin is inserted.
      results.innerHTML=visible.length?'<div class="cards">'+visible.map(r=>html[r.id]).join('')+'</div>':'<div class="empty-results"><h3>No properties match these filters</h3><p>Try a wider area or clear your filters.</p></div>';
      counter.textContent=`Showing ${visible.length?start+1:0}–${start+visible.length} of ${rows.length} lots`;
      pager.replaceChildren();
      function pageLink(n,label){
        const a=document.createElement('a');a.textContent=label;a.dataset.page=n;
        a.href=location.pathname+'?'+parameters(n).toString();
        if(n===page)a.setAttribute('aria-current','page');pager.append(a);
      }
      if(page>1)pageLink(page-1,'‹ Previous');
      const left=Math.max(1,Math.min(page-2,pages-4));
      for(let n=left;n<=Math.min(pages,left+4);n++)pageLink(n,String(n));
      if(page<pages)pageLink(page+1,'Next ›');
      if(writeUrl){const params=parameters(page).toString();history.pushState({},'',location.pathname+(params?'?'+params:''));}
      targetPrices(target.value);
    }catch(e){if(sequence!==request)return;error.textContent='The catalogue could not be loaded. Your existing results are still available. Reload the page and try again.';error.hidden=false;}
    finally{if(sequence===request)results.removeAttribute('aria-busy');}
  }
  form.addEventListener('submit',event=>{event.preventDefault();render(1);});
  document.querySelector('#clear-filters').addEventListener('click',()=>{form.reset();sort.value='date';render(1);});
  size.addEventListener('change',()=>render(1));sort.addEventListener('change',()=>render(1));
  target.addEventListener('input',()=>targetPrices(target.value));
  pager.addEventListener('click',event=>{const a=event.target.closest('[data-page]');if(a&&!event.ctrlKey&&!event.metaKey){event.preventDefault();render(Number(a.dataset.page));document.querySelector('.board-toolbar').scrollIntoView({block:'start'});}});
  window.addEventListener('popstate',()=>render(restore(),false));
  const page=restore();if(location.search)render(page,false);
})();
