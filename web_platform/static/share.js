/* Public sharing: no account, AI, paid service, recipient or tracking URL. */
(() => {
  'use strict';
  let dialog, active, trigger, config;
  const prefix = document.body.dataset.prefix || '';
  function track(channel, action) {
    const detail = {channel, action, placement: active?.placement || 'property'};
    document.dispatchEvent(new CustomEvent('auctiongeek:share', {detail}));
    // Respect browser privacy signals. The endpoint stores only aggregate counters.
    if (navigator.doNotTrack === '1' || navigator.globalPrivacyControl) return;
    config ||= fetch(prefix + '/platform-config.json', {credentials:'omit'}).then(r => r.ok ? r.json() : {}).catch(() => ({}));
    config.then(c => {
      if (!c.share_analytics_endpoint) return;
      fetch(c.share_analytics_endpoint, {method:'POST', credentials:'omit', keepalive:true,
        headers:{'Content-Type':'application/json'}, body:JSON.stringify(detail)}).catch(() => {});
    });
  }
  function buildDialog() {
    dialog = document.createElement('dialog');
    dialog.className = 'share-dialog';
    dialog.setAttribute('aria-labelledby', 'share-title');
    dialog.innerHTML = '<button type="button" class="share-close" aria-label="Close sharing">×</button><h2 id="share-title">Share this property</h2><p class="share-address"></p><div class="share-options"><a data-channel="whatsapp" target="_blank" rel="noopener noreferrer">WhatsApp</a><a data-channel="email">Email</a><a data-channel="linkedin" target="_blank" rel="noopener noreferrer">LinkedIn</a><a data-channel="facebook" target="_blank" rel="noopener noreferrer">Facebook</a><button type="button" class="share-copy">Copy property link</button></div><label for="share-link">Property link</label><input id="share-link" readonly><p class="share-status" role="status" aria-live="polite"></p>';
    document.body.append(dialog);
    dialog.querySelector('.share-close').onclick = () => dialog.close();
    dialog.addEventListener('close', () => {if (!dialog.open) trigger?.focus();});
    dialog.addEventListener('keydown', e => {
      if (e.key !== 'Tab') return;
      const items = [...dialog.querySelectorAll('button,a[href],input')];
      const first = items[0], last = items[items.length-1];
      if (e.shiftKey && document.activeElement === first) {e.preventDefault();last.focus();}
      else if (!e.shiftKey && document.activeElement === last) {e.preventDefault();first.focus();}
    });
    dialog.addEventListener('click', e => {
      if (e.target === dialog) {const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();}
      const link = e.target.closest('[data-channel]');
      if (link) track(link.dataset.channel, 'selected');
    });
    dialog.querySelector('#share-link').onclick = e => e.target.select();
    dialog.querySelector('.share-copy').onclick = async () => {
      const input = dialog.querySelector('#share-link'), status = dialog.querySelector('.share-status');
      let copied = false;
      try {await navigator.clipboard.writeText(active.url);copied = true;} catch (_) {
        input.focus();input.select();
        try {copied = document.execCommand('copy');} catch (_) {}
      }
      status.textContent = copied ? 'Property link copied.' : 'Select and copy the property link above.';
      track('copy', copied ? 'copied' : 'manual_copy');
    };
  }
  function fallback() {
    if (!dialog) buildDialog();
    const {title,text,url} = active, message = title + '\n' + text + '\n' + url;
    dialog.querySelector('.share-address').textContent = title.replace(/ \| Auction Geek$/, '');
    dialog.querySelector('#share-link').value = url;
    dialog.querySelector('.share-status').textContent = '';
    const links = {
      whatsapp: 'https://api.whatsapp.com/send?text=' + encodeURIComponent(message),
      email: 'mailto:?subject=' + encodeURIComponent(title) + '&body=' + encodeURIComponent(message),
      linkedin: 'https://www.linkedin.com/sharing/share-offsite/?url=' + encodeURIComponent(url),
      facebook: 'https://www.facebook.com/sharer/sharer.php?u=' + encodeURIComponent(url)
    };
    for (const [channel,href] of Object.entries(links)) dialog.querySelector('[data-channel="'+channel+'"]').href = href;
    dialog.showModal();
  }
  document.addEventListener('click', async e => {
    const button = e.target.closest('[data-share-url]');
    if (!button) return;
    e.preventDefault();
    const url = new URL(button.dataset.shareUrl, location.href);
    if (!['http:', 'https:'].includes(url.protocol)) return;
    url.search = '';url.hash = '';
    trigger = button;
    active = {title:button.dataset.shareTitle, text:button.dataset.shareText+'\nView property details and investment intelligence on Auction Geek:', url:url.href, placement:button.dataset.sharePlacement || 'property'};
    track('menu', 'opened');
    const data = {title:active.title,text:active.text,url:active.url};
    let canShare = false;
    try {canShare = !!navigator.share && matchMedia('(pointer: coarse)').matches && (!navigator.canShare || navigator.canShare(data));} catch (_) {}
    if (canShare) {
      try {await navigator.share(data);track('native','handed_off');return;}
      catch (error) {if(error.name === 'AbortError')return;}
    }
    fallback();
  });
})();
