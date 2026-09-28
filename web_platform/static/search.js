/* Shared keyword matcher, also exercised directly by the regression tests. */
(() => {
  'use strict';
  function normalise(value) {
    return String(value || '').normalize('NFKD').replace(/[\u0300-\u036f]/g,'')
      .toLowerCase().replace(/['’]/g,'').replace(/[^a-z0-9]+/g,' ').trim();
  }
  function matches(row, query) {
    const terms=normalise(query).split(/\s+/).filter(Boolean);
    const text=row.search_text ?? normalise(row.address);
    return terms.every(term=>text.includes(term));
  }
  function numericMatches(row, filters={}) {
    const valid=value=>typeof value==='number' && Number.isFinite(value) && value>0;
    const specified=value=>value!==null && value!==undefined && String(value).trim()!=='' && Number.isFinite(Number(value)) && Number(value)>=0;
    const minimum=Number(filters.min), maximum=Number(filters.max), yieldMinimum=Number(filters.yield);
    if(specified(filters.min) && (!valid(row.guide_price)||row.guide_price<minimum))return false;
    if(specified(filters.max) && (!valid(row.guide_price)||row.guide_price>maximum))return false;
    const qualifyingYield=Object.prototype.hasOwnProperty.call(row,'giy_min')?row.giy_min:row.giy;
    if(specified(filters.yield) && (!valid(qualifyingYield)||qualifyingYield<yieldMinimum))return false;
    return true;
  }
  const api={normalise,matches,numericMatches};
  if(typeof module!=='undefined' && module.exports) module.exports=api;
  else window.AuctionSniperSearch=api;
})();
