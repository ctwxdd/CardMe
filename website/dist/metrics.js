// Counts events only; no cookies, persistent IDs, URLs or referrers are sent.
(() => {
  if (navigator.doNotTrack === '1' || navigator.globalPrivacyControl === true) return;
  const send = event => {
    try {
      const body = JSON.stringify({schema_version: 1, event_id: crypto.randomUUID(), event,
        app_version: 'web', mode: 'none', full_size: 0, previews: 0, thumbnails: 0,
        review: 0, unrecovered: null});
      void fetch('https://pickology-control-plane.azurewebsites.net/api/v1/cardme/usage', {
        method: 'POST', body, headers: {'Content-Type': 'text/plain;charset=UTF-8'},
        credentials: 'omit', referrerPolicy: 'no-referrer', keepalive: true
      }).catch(() => {});
    } catch (_) { /* Statistics must never affect navigation. */ }
  };
  send('page_view');
  document.addEventListener('click', event => {
    const link = event.target.closest?.('a');
    if (link?.getAttribute('href') === '/cardme/download') send('download_click');
    if (link?.getAttribute('href') === 'https://ko-fi.com/alittleseal') send('web_coffee_click');
  });
})();
