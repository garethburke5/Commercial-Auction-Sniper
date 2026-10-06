/* Progressively enhance the same server-rendered Auction Sniper cards. */
(() => {
  'use strict';
  const cash = value => new Intl.NumberFormat('en-GB', {style:'currency',currency:'GBP',maximumFractionDigits:0}).format(value);
  function targetPrices(value) {
    const target=Number(value);
    const valid=String(value).trim()!=='' && Number.isFinite(target) && target>=1 && target<=30;
    document.querySelectorAll('[data-rent]').forEach(card => {
      const rent=Number(card.dataset.rent), price=card.querySelector('.target-price'), label=card.querySelector('.target-label');
      if (label) label.textContent=String(target);
      if (price) price.textContent=!valid ? 'Choose a target yield from 1% to 30%' : rent>0 ? cash(rent/(target/100)) : 'Current rent not stated';
    });
  }
  const propertyTarget=document.querySelector('#property-target');
  if (propertyTarget) propertyTarget.addEventListener('input',()=>targetPrices(propertyTarget.value));
  document.querySelectorAll('.auctioneer-logo').forEach(img=>{
    const fallback=()=>{img.hidden=true;const label=img.parentElement.querySelector('.house-monogram');if(label)label.hidden=false;};
    img.addEventListener('error',fallback);
    if(img.complete&&!img.naturalWidth)fallback();
  });
  let photos=Array.from(document.querySelectorAll('[data-gallery-src]'));
  if (photos.length) {
    let selected=0;
    const hero=document.querySelector('#gallery-hero'), original=document.querySelector('#gallery-original');
    const primary=photos[0], position=document.querySelector('#gallery-position');
    function updateGallery() {
      photos.forEach((button,i)=>{
        button.setAttribute('aria-pressed',String(i===selected));
        button.setAttribute('aria-label',`View image ${i+1}${button===primary?', auctioneer primary photograph':''}`);
      });
      position.textContent=`Image ${selected+1} of ${photos.length} · ${photos[selected].dataset.galleryLabel}`;
      document.querySelector('.gallery-controls').hidden=photos.length<2;
    }
    function showPhoto(n) {
      selected=(n+photos.length)%photos.length;
      const item=photos[selected];
      hero.src=item.dataset.gallerySrc;hero.alt=item.dataset.galleryLabel;
      original.href=item.dataset.gallerySrc;
      updateGallery();
    }
    function unavailablePhoto(button) {
      // A failed optional photograph must not leave a blank gallery slide.
      // Always preserve the auctioneer's primary selection, even if its host fails.
      const index=photos.indexOf(button);
      if(index<0||button===primary)return;
      const active=photos[selected];
      photos=photos.filter(photo=>photo!==button);button.remove();
      if(active===button)showPhoto(Math.min(index,photos.length-1));
      else{selected=photos.indexOf(active);updateGallery();}
    }
    photos.forEach(button=>{
      button.addEventListener('click',()=>showPhoto(photos.indexOf(button)));
      const thumbnail=button.querySelector('img');
      thumbnail.addEventListener('error',()=>unavailablePhoto(button));
      if(thumbnail.complete&&!thumbnail.naturalWidth)unavailablePhoto(button);
    });
    hero.addEventListener('error',()=>unavailablePhoto(photos[selected]));
    document.querySelector('#gallery-previous').addEventListener('click',()=>showPhoto(selected-1));
    document.querySelector('#gallery-next').addEventListener('click',()=>showPhoto(selected+1));
    document.querySelector('.property-gallery').addEventListener('keydown',e=>{
      if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();showPhoto(selected+(e.key==='ArrowLeft'?-1:1));}
    });
  }
  const research=document.querySelector('#open-research');
  if (research) {
    const property=new URLSearchParams(location.search).get('property');
    const source=new URL(research.dataset.src),full=document.querySelector('#research-fullscreen');
    if(property&&/^[a-f0-9]{20}$/.test(property)){
      source.searchParams.set('property',property);
      const direct=new URL(full.href);direct.searchParams.set('property',property);full.href=direct;
    }
    research.addEventListener('click',()=>{
      const frame=document.querySelector('#research-frame');
      frame.src=source.href;frame.hidden=false;research.remove();
    });
    if(property&&/^[a-f0-9]{20}$/.test(property))research.click();
  }
  const houseSearch=document.querySelector('#auctioneer-search');
  if (houseSearch) {
    const currentOnly=document.querySelector('#auctioneer-current');
    const houses=Array.from(document.querySelectorAll('.auctioneer-card'));
    function filterHouses(){
      const terms=houseSearch.value.toLowerCase().trim().split(/\s+/).filter(Boolean);
      let visible=0;
      houses.forEach(h=>{
        h.hidden=!terms.every(t=>h.dataset.house.includes(t)) || (currentOnly.checked && Number(h.dataset.current)===0);
        if(!h.hidden)visible++;
      });
      document.querySelector('#auctioneer-count').textContent=`${visible} of ${houses.length} auctioneers`;
      document.querySelector('#auctioneer-empty').hidden=visible!==0;
    }
    houseSearch.addEventListener('input',filterHouses);
    currentOnly.addEventListener('change',filterHouses);
  }
  const board=document.querySelector('#property-board');
  if (!board) return;
  const form=document.querySelector('#property-filters'), results=document.querySelector('#board-results');
  const counter=document.querySelector('#result-count'), pager=document.querySelector('#board-pager');
  const error=document.querySelector('#board-error'), size=document.querySelector('#page-size'), sort=document.querySelector('#sort-order');
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
    ['q','min','max','yield','tenure','status'].forEach(k=>{const v=control(k).value.trim();if(v)p.set(k,v);});
    sources().forEach(v=>p.append('source',v));
    if(size.value!=='50')p.set('size',size.value);
    if(sort.value!=='date')p.set('sort',sort.value);
    if(page>1)p.set('page',page);
    return p;
  }
  function restore(){
    const p=new URLSearchParams(location.search);
    form.reset();size.value='50';sort.value='date';
    ['q','min','max','yield','tenure','status'].forEach(k=>{if(p.has(k))control(k).value=p.get(k);});
    Array.from(control('source').options).forEach(o=>{o.selected=p.getAll('source').includes(o.value);});
    if(['10','50','100','All'].includes(p.get('size')))size.value=p.get('size');
    if(['date','price','yield'].includes(p.get('sort')))sort.value=p.get('sort');
    return Math.max(1,parseInt(p.get('page')||board.dataset.page,10)||1);
  }
  function matches(row){
    if(!window.AuctionSniperSearch.matches(row,control('q').value))return false;
    const selected=sources();if(selected.length && !selected.includes(row.source))return false;
    const tenure=control('tenure').value.toLowerCase();if(tenure && (row.tenure||'').toLowerCase()!==tenure)return false;
    const status=control('status').value;if(status==='available'&&row.unavailable)return false;
    if(status==='unavailable'&&!row.unavailable)return false;
    return window.AuctionSniperSearch.numericMatches(row,{
      min:control('min').value,max:control('max').value,yield:control('yield').value
    });
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
      counter.textContent=`Showing ${visible.length?start+1:0}–${start+visible.length} of ${rows.length} catalogue lots · ${rows.filter(r=>!r.unavailable).length} available · ${rows.filter(r=>r.unavailable).length} sold / withdrawn / postponed`;
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
      const applied=parameters(1);
      const meaningful=['q','source','min','max','yield','tenure','status'].some(k=>applied.get(k)?.trim());
      const saveSearch=document.querySelector('#save-search');
      saveSearch.hidden=!meaningful;
      const upcoming=document.querySelector('.upcoming-auctions');if(upcoming)upcoming.hidden=meaningful;
      saveSearch.dataset.query=applied.toString();
    }catch(e){if(sequence!==request)return;error.textContent='The catalogue could not be loaded. Your existing results are still available. Reload the page and try again.';error.hidden=false;}
    finally{if(sequence===request)results.removeAttribute('aria-busy');}
  }
  form.addEventListener('submit',event=>{event.preventDefault();render(1);});
  document.querySelector('#clear-filters').addEventListener('click',()=>{form.reset();sort.value='date';render(1);});
  size.addEventListener('change',()=>render(1));sort.addEventListener('change',()=>render(1));
  pager.addEventListener('click',event=>{const a=event.target.closest('[data-page]');if(a&&!event.ctrlKey&&!event.metaKey){event.preventDefault();render(Number(a.dataset.page));document.querySelector('.board-toolbar').scrollIntoView({block:'start'});}});
  window.addEventListener('popstate',()=>render(restore(),false));
  const page=restore();if(location.search)render(page,false);
})();
