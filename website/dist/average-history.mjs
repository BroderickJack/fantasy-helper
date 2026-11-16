const $ = id => document.getElementById(id);
const points = value => value == null ? '—' : value.toFixed(2);
const record = row => `${row.wins}–${row.losses}${row.ties ? `–${row.ties}` : ''}`;
let archive;

function element(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text != null) el.textContent = text;
  return el;
}

function source(url, text) {
  const link = element('a', 'source-link', text);
  link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer';
  return link;
}

function renderGameLog() {
  if (!archive) return;
  const season = $('average-history-season').value;
  const phase = $('average-history-phase').value;
  const games = archive.seasons.flatMap(row => row.games).filter(game => (season === 'all' || game.season === Number(season)) && (phase === 'all' || game.phase === phase))
    .sort((a, b) => b.season - a.season || b.week - a.week);
  const rows = document.createDocumentFragment();
  for (const game of games) {
    const row = document.createElement('tr');
    const date = element('td', '', `${game.season} · Week ${game.week}`);
    if (game.phase === 'playoff') date.append(element('span', 'average-season-sub', 'Championship bracket'));
    row.append(date, element('td', 'team-name', game.opponent_name), element('td', 'number', points(game.score)), element('td', 'number', points(game.opponent_score)), element('td', `number ${game.result === 'W' ? 'positive' : game.result === 'L' ? 'negative' : ''}`, game.result));
    row.append(element('td', 'number', `${game.margin > 0 ? '+' : game.margin < 0 ? '−' : ''}${points(Math.abs(game.margin))}`));
    const cell = document.createElement('td'); cell.className = 'number'; cell.append(source(game.source_url, 'ESPN ↗')); row.append(cell);
    rows.append(row);
  }
  if (!games.length) { const row = document.createElement('tr'); const cell = element('td', 'loading-cell', 'No completed games match this selection.'); cell.colSpan = 7; row.append(cell); rows.append(row); }
  $('average-game-log').replaceChildren(rows);
  $('average-log-count').textContent = `${games.length} recorded game${games.length === 1 ? '' : 's'} · Scores and results as entered in ESPN.`;
  for (const button of document.querySelectorAll('#average-scoring-bars button')) button.setAttribute('aria-pressed', String(button.dataset.season === season));
}

function renderSeasons() {
  const rows = document.createDocumentFragment();
  for (const season of [...archive.seasons].reverse()) {
    const row = document.createElement('tr');
    const year = document.createElement('td');
    year.append(source(season.source_url, `${season.season}${season.season === archive.current_season ? ' · YTD' : ''}`));
    year.append(element('span', 'average-season-sub', `${season.name} · ${season.season === archive.current_season ? `through Week ${season.through_week}` : `${season.regular.games} games`}`));
    row.append(year);
    for (const value of [record(season.regular), season.regular.games, points(season.regular.ppg), points(season.regular.opponent_ppg), season.playoffs.games ? record(season.playoffs) : '—', season.final_rank ? `#${season.final_rank}` : 'In progress']) row.append(element('td', 'number', value));
    rows.append(row);
  }
  $('average-seasons').replaceChildren(rows);
  const scale = Math.max(1, ...archive.seasons.flatMap(season => [season.regular.ppg ?? 0, season.regular.opponent_ppg ?? 0])) * 1.08;
  const bars = document.createDocumentFragment();
  for (const season of archive.seasons) {
    const button = element('button', 'average-score-row'); button.type = 'button'; button.dataset.season = String(season.season);
    button.setAttribute('aria-label', `View ${season.season} game log; Average ${points(season.regular.ppg)} points per game, opponents ${points(season.regular.opponent_ppg)}`);
    button.append(element('span', '', `${season.season}${season.season === archive.current_season ? ' · YTD' : ''}`));
    const track = element('span', 'average-score-track'); track.setAttribute('aria-hidden', 'true');
    for (const [className, value] of [['opponent-bar', season.regular.opponent_ppg], ['average-bar', season.regular.ppg]]) {
      const bar = element('span', className); bar.style.width = `${Math.max(0, (value ?? 0) / scale * 100)}%`; track.append(bar);
    }
    button.append(track, element('span', 'average-score-values', `${season.regular.ppg?.toFixed(1) ?? '—'} / ${season.regular.opponent_ppg?.toFixed(1) ?? '—'}`));
    button.addEventListener('click', () => { $('average-history-season').value = String(season.season); renderGameLog(); });
    bars.append(button);
  }
  $('average-scoring-bars').replaceChildren(bars);
}

export async function loadAverageHistory() {
  try {
    const response = await fetch('average-history.json');
    if (!response.ok) throw new Error('Historical results could not be loaded. Reload to try again.');
    archive = await response.json();
    if (!archive.seasons?.length) throw new Error('Season history is not available yet.');
    const latest = archive.seasons.at(-1);
    $('average-history-coverage').textContent = `${archive.seasons[0].season}–${latest.season}${latest.season === archive.current_season ? ` · ${latest.season} through Week ${latest.through_week}` : ''}`;
    $('average-career-record').textContent = record(archive.regular);
    $('average-career-games').textContent = `${archive.regular.games} recorded games · ${archive.seasons.length} seasons`;
    $('average-career-rate').textContent = archive.regular.win_pct == null ? '—' : `${(archive.regular.win_pct * 100).toFixed(1)}%`;
    const best = archive.seasons.find(row => row.season === archive.best_season);
    $('average-best-record').textContent = best ? record(best.regular) : '—';
    $('average-best-year').textContent = best ? String(best.season) : '';
    const finishes = archive.seasons.filter(row => row.season < archive.current_season && row.final_rank).sort((a, b) => a.final_rank - b.final_rank);
    $('average-best-finish').textContent = finishes.length ? `#${finishes[0].final_rank}` : '—';
    $('average-finish-year').textContent = finishes.length ? String(finishes[0].season) : '';
    const notes = [];
    if (best) notes.push(`${best.season} was the strongest completed regular season at ${record(best.regular)}${best.final_rank ? `, with a #${best.final_rank} overall finish` : ''}.`);
    if (archive.high_score) notes.push(`Highest recorded regular-season score: ${points(archive.high_score.score)} in ${archive.high_score.season}, Week ${archive.high_score.week}.`);
    $('average-history-note').textContent = notes.join(' ');
    $('average-history-season').append(...[...archive.seasons].reverse().map(row => new Option(`${row.season}${row.season === archive.current_season ? ' · YTD' : ''}`, String(row.season))));
    $('average-history-season').value = String(latest.season);
    $('average-history-season').disabled = false; $('average-history-phase').disabled = false;
    $('average-history-season').addEventListener('change', renderGameLog); $('average-history-phase').addEventListener('change', renderGameLog);
    const date = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(archive.checked_at));
    const unposted = archive.seasons.reduce((total, season) => total + season.excluded.score_not_posted, 0);
    $('average-history-updated').textContent = `Historical archive built ${date}. ${archive.regular.games} regular-season games are recorded${unposted ? `; ${unposted} matchups still awaiting a posted score are excluded` : ''}. The history is a saved snapshot; the current matchup above updates live.`;
    renderSeasons(); renderGameLog();
  } catch (error) {
    archive = null;
    $('average-history-error').textContent = error.message; $('average-history-error').hidden = false;
    $('average-history-coverage').textContent = 'History unavailable';
    for (const id of ['average-seasons', 'average-game-log']) { const row = document.createElement('tr'); const cell = element('td', 'loading-cell', 'Historical results are unavailable. Reload to try again.'); cell.colSpan = 7; row.append(cell); $(id).replaceChildren(row); }
  }
}
