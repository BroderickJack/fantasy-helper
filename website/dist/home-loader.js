// Keep startup errors visible even when a module cannot be downloaded or loaded.
(() => {
  const $ = id => document.getElementById(id);
  const showStartupError = () => {
    const message = location.protocol === 'file:'
      ? 'Open this site through its web address or local HTTP server to load scores.'
      : 'The homepage could not start. Reload the page to try again.';
    $('home-scores-error').textContent = message;
    $('home-scores-error').hidden = false;
    $('home-live-status').textContent = 'Scores have not loaded.';
    $('home-matchups').textContent = message;
    const cell = document.createElement('td');
    cell.colSpan = 6;
    cell.className = 'loading-cell';
    cell.textContent = message;
    const row = document.createElement('tr');
    row.append(cell);
    $('home-teams').replaceChildren(row);
    for (const id of ['home-matchups', 'home-comparison', 'defending-card']) $(id).setAttribute('aria-busy', 'false');
    $('defending-title').textContent = 'The record books could not load.';
    $('champion-manager').textContent = 'Reload the page or visit Champions.';
    $('home-refresh').disabled = false;
    $('home-refresh').textContent = '↻ Reload page';
    $('home-refresh').onclick = () => location.reload();
  };
  import('./home.mjs?v=20261116-2').catch(showStartupError);
})();
