(() => {
  const link = document.getElementById('login');
  document.getElementById('status').textContent = '正在連線至管理後台，需要時會請你登入 Microsoft 帳號。';
  // Paint the static status before starting a navigation that may wake Azure.
  requestAnimationFrame(() => requestAnimationFrame(() => location.replace(link.href)));
})();
