// Public aggregate counts only; this read does not send a tracking event.
(async () => {
  const target = document.querySelector('[data-public-totals]');
  if (!target) return;
  try {
    const response = await fetch('https://cardme-control-plane.azurewebsites.net/api/v1/public/totals', {
      credentials: 'omit', referrerPolicy: 'no-referrer', signal: AbortSignal.timeout(8000)
    });
    if (!response.ok) return;
    const totals = await response.json();
    if (Object.keys(totals).length !== 3 || totals.windowDays !== 90 ||
        !['rescueSessions', 'fullSizePhotos'].every(key => Number.isSafeInteger(totals[key]) && totals[key] >= 0)) return;
    const numbers = new Intl.NumberFormat(document.documentElement.lang);
    for (const key of ['rescueSessions', 'fullSizePhotos']) target.querySelector(`[data-total="${key}"]`).textContent = numbers.format(totals[key]);
    target.hidden = false;
  } catch (_) { /* Recovery and downloads never depend on statistics. */ }
})();
