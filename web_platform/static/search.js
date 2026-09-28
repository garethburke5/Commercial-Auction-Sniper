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
  const api={normalise,matches};
  if(typeof module!=='undefined' && module.exports) module.exports=api;
  else window.AuctionSniperSearch=api;
})();
