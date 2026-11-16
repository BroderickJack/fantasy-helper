import { DEFAULT_TEAM_ID } from './data.mjs';
import { combineSeasons, headToHead } from './research-data.mjs';

const $ = id => document.getElementById(id);
const number = (value, digits = 1) => value == null ? '—' : value.toFixed(digits);
const percent = value => value == null ? '—' : `${(value * 100).toFixed(1)}%`;
const signed = value => value == null ? '—' : `${value > .00001 ? '+' : value < -.00001 ? '−' : ''}${Math.abs(value).toFixed(2)}`;
const record = row => `${row.wins}–${row.losses}${row.ties ? `–${row.ties}` : ''}`;
const node = (tag, className, text) => { const el = document.createElement(tag); if (className) el.className = className; if (text != null) el.textContent = text; return el; };
let data;
let selected = DEFAULT_TEAM_ID;
try { selected = Number(localStorage.getItem('qrffl-team')) || DEFAULT_TEAM_ID; } catch { /* Optional preference. */ }
const label = id => data.teams.find(team => team.id === id)?.name ?? `Team #${id}`;
const source = (url, text = 'ESPN ↗') => { const a = node('a', 'source-link', text); a.href = url; a.target = '_blank'; a.rel = 'noopener noreferrer'; return a; };

function scopeRows() {
  const season = $('research-season').value;
  return data.performance.filter(row => season === 'all' || row.season === Number(season));
}

function drawChart() {
  const compare = Number($('research-compare').value) || null;
  const series = [selected, ...(compare && compare !== selected ? [compare] : [])].map(id => ({ id, rows: data.performance.filter(row => row.team_id === id && row.scoring_index != null).sort((a, b) => a.season - b.season) }));
  const all = series.flatMap(line => line.rows);
  if (!all.length) { $('research-chart').replaceChildren(node('p', 'research-note', 'No scoring history is available for this selection.')); return; }
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg'); svg.setAttribute('viewBox', '0 0 760 250'); svg.setAttribute('role', 'img'); svg.setAttribute('aria-labelledby', 'research-chart-svg-title');
  const title = document.createElementNS(ns, 'title'); title.id = 'research-chart-svg-title'; title.textContent = `Season scoring index for ${series.map(line => label(line.id)).join(' and ')}; league baseline 100. Exact values are in the season table.`; svg.append(title);
  const minYear = Math.min(...data.seasons), maxYear = Math.max(...data.seasons);
  const lo = Math.floor(Math.min(100, ...all.map(row => row.scoring_index)) / 5) * 5 - 5;
  const hi = Math.ceil(Math.max(100, ...all.map(row => row.scoring_index)) / 5) * 5 + 5;
  const x = year => 48 + (year - minYear) / Math.max(1, maxYear - minYear) * 680;
  const y = value => 205 - (value - lo) / (hi - lo) * 160;
  function shape(tag, attributes, text) { const el = document.createElementNS(ns, tag); for (const [key, value] of Object.entries(attributes)) el.setAttribute(key, String(value)); if (text != null) el.textContent = text; svg.append(el); return el; }
  for (let i = 0; i < 4; i++) {
    const value = lo + (hi - lo) * i / 3;
    shape('line', { x1: 48, x2: 728, y1: y(value), y2: y(value), stroke: '#e3e8d9' });
    shape('text', { x: 37, y: y(value) + 3, 'text-anchor': 'end', class: 'chart-axis' }, value.toFixed(0));
  }
  shape('line', { x1: 48, x2: 728, y1: y(100), y2: y(100), stroke: '#a2b28f', 'stroke-dasharray': '4 5' });
  for (const year of data.seasons) shape('text', { x: x(year), y: 229, 'text-anchor': 'middle', class: 'chart-axis' }, year);
  series.forEach((line, index) => {
    const color = index ? '#bc7946' : '#315c40';
    shape('text', { x: 48 + index * 350, y: 18, class: 'chart-title', style: `fill:${color}` }, label(line.id).slice(0, 45));
    let segment = [];
    function flush() { if (segment.length) shape('polyline', { points: segment.map(row => `${x(row.season)},${y(row.scoring_index)}`).join(' '), stroke: color, class: 'chart-line' }); segment = []; }
    for (const row of line.rows) {
      if (segment.length && row.season !== segment.at(-1).season + 1) flush();
      segment.push(row);
    }
    flush();
    for (const row of line.rows) {
      const dot = shape('circle', { cx: x(row.season), cy: y(row.scoring_index), r: 4, fill: color });
      const tip = document.createElementNS(ns, 'title'); tip.textContent = `${row.season}: ${row.team_name} · index ${number(row.scoring_index)} · ${record(row)}${row.season === data.current_season ? ` through Week ${data.current_through_week}` : ''}`; dot.append(tip);
    }
  });
  $('research-chart').replaceChildren(svg);
}

function renderProfile() {
  const rows = scopeRows().filter(row => row.team_id === selected);
  const summary = combineSeasons(rows);
  $('research-record').textContent = summary ? record(summary) : '—';
  $('research-games').textContent = summary ? `${summary.games} games · ${summary.seasons} season${summary.seasons === 1 ? '' : 's'} in scope` : 'No games in this scope';
  $('research-allplay').textContent = summary ? percent(summary.all_play_pct) : '—';
  $('research-index').textContent = summary ? number(summary.scoring_index) : '—';
  $('research-swing').textContent = summary ? signed(summary.schedule_swing) : '—';
  const fragment = document.createDocumentFragment();
  for (const season of data.performance.filter(row => row.team_id === selected).sort((a, b) => b.season - a.season)) {
    const row = document.createElement('tr'); const info = node('td', 'season-title');
    info.append(source(season.standings_url, `${season.season}${season.season === data.current_season ? ' · YTD' : ''}`), node('span', 'season-subtitle', `${season.team_name} · ${season.managers.join(' & ') || 'Manager not recorded'}`));
    row.append(info);
    for (const text of [record(season), number(season.ppg), percent(season.all_play_wins == null ? null : season.all_play_wins / season.all_play_comparisons), number(season.scoring_index), number(season.expected_wins, 2), season.final_rank == null ? 'In progress' : `#${season.final_rank}`]) row.append(node('td', 'number', text));
    fragment.append(row);
  }
  $('research-seasons').replaceChildren(fragment);
  drawChart();
  const comparison = Number($('research-compare').value) || null;
  if (comparison && comparison !== selected) {
    const h2h = headToHead(data.head_to_head, selected, comparison);
    $('research-h2h').textContent = h2h.games ? `Head-to-head, 2019–2025: ${label(selected)} is ${record(h2h)} against ${label(comparison)} across ${h2h.games} archived regular-season and championship-bracket games.` : 'These franchises have no head-to-head games in the 2019–2025 archive.';
  } else $('research-h2h').textContent = 'Choose a comparison franchise to see its trajectory and the archived head-to-head record.';
}

function renderLeaderboard() {
  if (!data) return;
  const rows = scopeRows();
  const teams = [...new Set(rows.map(row => row.team_id))].map(id => combineSeasons(rows.filter(row => row.team_id === id)));
  const metric = $('research-sort').value;
  teams.sort((a, b) => (b[metric] ?? -Infinity) - (a[metric] ?? -Infinity) || a.team_id - b.team_id);
  const years = new Set(rows.map(row => row.season));
  const fragment = document.createDocumentFragment();
  for (const team of teams) {
    const row = document.createElement('tr'); row.classList.toggle('selected', team.team_id === selected);
    const name = document.createElement('td'); const button = node('button', 'research-team-link', label(team.team_id));
    button.addEventListener('click', () => { selected = team.team_id; $('research-team').value = String(selected); render(); });
    name.append(button, node('span', 'season-subtitle', `Team slot #${team.team_id} · ${team.seasons} seasons`)); row.append(name);
    const titles = data.championships.filter(title => title.team_id === team.team_id && years.has(title.season)).length;
    for (const value of [team.games, record(team), percent(team.win_pct), percent(team.all_play_pct), number(team.scoring_index), signed(team.schedule_swing), titles]) row.append(node('td', 'number', value));
    fragment.append(row);
  }
  $('research-leaderboard').replaceChildren(fragment);
}

function tradeEvidence(trade, details) {
  const wrap = node('div', 'trade-evidence'); const table = document.createElement('table');
  const caption = node('caption', 'sr-only', `Week-by-week production and retained starter credit for the ${trade.season} Week ${trade.week} trade.`);
  const head = document.createElement('thead'); const headings = document.createElement('tr');
  for (const text of ['RECIPIENT / PLAYER', 'WEEK', 'PLAYER PTS', 'LINEUP / OWNERSHIP', 'CREDITED PTS', 'SOURCE']) { const th = node('th', '', text); th.scope = 'col'; headings.append(th); }
  head.append(headings); const body = document.createElement('tbody');
  for (const party of trade.parties) for (const player of party.received) for (const event of player.evidence) {
    const row = document.createElement('tr'); const identity = node('td', 'player-cell', player.name); identity.append(node('span', 'season-subtitle', party.team_name)); row.append(identity);
    for (const text of [event.week, number(event.points, 2), `${event.lineup}${event.score_source === 'bye' ? ' · NFL bye' : event.score_source === 'missing' ? ' · points unavailable' : ''}`, number(event.starter_credit, 2)]) row.append(node('td', '', text));
    const cell = document.createElement('td'); cell.append(source(`https://fantasy.espn.com/football/scoreboard?leagueId=${data.league_id}&seasonId=${trade.season}&matchupPeriodId=${trade.period_by_week[event.week]}`)); row.append(cell); body.append(row);
  }
  table.append(caption, head, body); wrap.append(table); details.append(wrap);
  if (trade.associated_drops.length) details.append(node('p', 'trade-context-note', `Associated roster drops: ${trade.associated_drops.join(', ')}. Their opportunity cost is not included in the package comparison.`));
  details.append(node('p', 'trade-context-note', 'Scoring uses full weeks after the deal, through the stated cutoff. Starter credit stops before the exit week or at the first roster absence. Player output continues after exits. Bench, IR, and weeks without a scored matchup earn zero starter credit. Unavailable data stays blank.'));
  details.append(source(trade.source_url, 'ESPN transaction activity ↗'));
}

function renderTrades() {
  if (!data) return;
  const year = $('trade-season').value;
  const selectedOnly = $('trade-selected-only').checked;
  const trades = data.trades.filter(trade => (year === 'all' || trade.season === Number(year)) && (!selectedOnly || trade.parties.some(party => party.team_id === selected)));
  trades.sort((a, b) => (b.starter_edge?.points ?? -Infinity) - (a.starter_edge?.points ?? -Infinity) || b.season - a.season || b.week - a.week);
  const coverage = data.trade_coverage.filter(row => year === 'all' || row.season === Number(year));
  $('trade-coverage').textContent = `${trades.length} recovered deals shown · ${coverage.map(row => `${row.season} through W${row.through_week}`).join(' · ')}`;
  const fragment = document.createDocumentFragment();
  for (const trade of trades) {
    const measured = trade.through_week >= trade.first_full_week;
    const article = node('article', 'trade-card'); const header = node('div', 'trade-card-header');
    let headline = !measured ? 'Awaiting the first full post-trade week' : !trade.starter_edge ? 'Starter-point comparison unavailable' : trade.starter_edge.points < .005 ? 'Level on received starter points' : `${trade.parties.find(p => p.team_id === trade.starter_edge.team_id).team_name} · +${number(trade.starter_edge.points, 2)} starter-point edge`;
    const date = trade.date ? new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', timeZone: 'America/New_York' }).format(new Date(trade.date)) : `Week ${trade.week}`;
    header.append(node('h3', '', headline), node('span', '', `${trade.season} · Week ${trade.week} · ${date}`)); article.append(header);
    const parties = node('div', 'trade-parties');
    if (trade.parties.length > 2) parties.style.gridTemplateColumns = '1fr';
    for (const party of trade.parties) {
      const side = node('section', 'trade-party'); side.append(node('h4', '', party.team_name), node('p', 'trade-manager', party.managers.join(' & ') || 'Manager not recorded'), node('span', 'small-label', 'RECEIVED'));
      const list = document.createElement('ul');
      for (const player of party.received) list.append(node('li', '', `${player.name}${player.exit_week ? ` · exited Week ${player.exit_week}` : ''}`));
      side.append(list, node('p', 'sent-players', `Sent: ${party.sent.map(player => player.name).join(', ') || 'No player legs recorded'}`));
      const metrics = node('div', 'trade-output');
      for (const [title, value] of [['RECEIVED STARTER POINTS', party.starter_points], ['PLAYER OUTPUT', party.production_points]]) {
        const metric = document.createElement('div'); metric.append(node('span', 'small-label', title), node('strong', '', measured ? number(value, 2) : '—')); metrics.append(metric);
      }
      side.append(metrics);
      const window = measured ? `Full weeks ${trade.first_full_week}–${trade.through_week}; starter credit only during the first roster stay.` : `Measurement starts Week ${trade.first_full_week}.`;
      side.append(node('p', 'trade-context-note', window));
      const before = `${record(party.before)} in ${party.before.games} games, ${number(party.before.ppg)} PPG`;
      const after = `${record(party.after)} in ${party.after.games} games, ${number(party.after.ppg)} PPG`;
      side.append(node('p', 'trade-record-context', `Regular-season context · Before: ${before}. After: ${after}. Trade week excluded.`)); parties.append(side);
    }
    article.append(parties);
    if (measured) {
      const details = document.createElement('details'); details.append(node('summary', '', 'Player-by-player, week-by-week receipts'));
      let loaded = false; details.addEventListener('toggle', () => { if (details.open && !loaded) { tradeEvidence(trade, details); loaded = true; } }); article.append(details);
    }
    fragment.append(article);
  }
  if (!trades.length) fragment.append(node('p', 'trade-empty', 'No recovered trades match these filters.'));
  $('research-trades').replaceChildren(fragment);
}

function renderInsights() {
  const rows = scopeRows();
  const aggregates = [...new Set(rows.map(row => row.team_id))].map(id => combineSeasons(rows.filter(row => row.team_id === id)));
  const strongest = aggregates.filter(row => row.scoring_index != null).sort((a, b) => b.scoring_index - a.scoring_index)[0];
  const gap = aggregates.filter(row => row.schedule_swing != null).sort((a, b) => Math.abs(b.schedule_swing) - Math.abs(a.schedule_swing))[0];
  const articles = [];
  function insight(title, text) { const article = document.createElement('article'); article.append(node('h3', '', title), node('p', '', text)); articles.push(article); }
  if (strongest) insight('Strongest scoring in scope', `${label(strongest.team_id)} leads with a ${number(strongest.scoring_index)} scoring index across ${strongest.games} games. The weekly league average is 100.`);
  if (gap) insight('Largest results-versus-score gap', `${label(gap.team_id)} recorded ${number(Math.abs(gap.schedule_swing), 2)} ${gap.schedule_swing >= 0 ? 'more' : 'fewer'} win equivalents than the all-play model expected across ${gap.games} games.`);
  const completed = data.performance.filter(row => row.team_id === selected && row.season < data.current_season && row.scoring_index != null).sort((a, b) => b.season - a.season);
  if (completed.length >= 2 && completed[0].season === completed[1].season + 1) insight('Latest completed-year change', `${label(selected)} moved ${signed(completed[0].scoring_index - completed[1].scoring_index)} scoring-index points from ${completed[1].season} to ${completed[0].season}. Current-year partial results are excluded from this comparison.`);
  $('research-insights').replaceChildren(...articles);
}
function render() { renderProfile(); renderLeaderboard(); renderTrades(); renderInsights(); }

async function load() {
  try {
    const response = await fetch('research.json'); if (!response.ok) throw new Error('The analytics archive could not be loaded. Reload to try again.');
    data = await response.json();
    const available = data.teams.filter(team => data.performance.some(row => row.team_id === team.id)).sort((a, b) => a.name.localeCompare(b.name));
    if (!available.some(team => team.id === selected)) selected = available[0].id;
    $('research-team').replaceChildren(...available.map(team => new Option(team.name, String(team.id), false, team.id === selected)));
    $('research-compare').append(...available.map(team => new Option(team.name, String(team.id))));
    $('research-season').append(...[...data.seasons].reverse().map(year => new Option(`${year}${year === data.current_season ? ' · YTD' : ''}`, String(year))));
    $('trade-season').append(...[...data.trade_coverage].reverse().map(row => new Option(`${row.season}${row.season === data.current_season ? ' · YTD' : ''}`, String(row.season))));
    for (const id of ['research-team', 'research-season', 'research-compare', 'research-sort', 'trade-season', 'trade-selected-only']) $(id).disabled = false;
    $('research-coverage').textContent = `Performance: ${data.seasons[0]}–${data.seasons.at(-1)} · ${data.current_season} includes completed weeks through Week ${data.current_through_week}. Summary and leaderboard follow the selected scope; the trajectory shows all available years.`;
    const date = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(data.checked_at));
    $('research-updated').textContent = `Archive built ${date}. ${data.performance.length} franchise-season rows; ${data.trades.length} executed trade receipts recovered from ${data.trade_coverage.reduce((total, row) => total + row.players_scanned, 0).toLocaleString()} player-card scans across ${data.trade_coverage.map(row => row.season).join(', ')}. This page is a bundled snapshot, not a live trade feed.`;
    render();
  } catch (error) { $('research-error').textContent = error.message; $('research-error').hidden = false; $('research-coverage').textContent = 'Analytics unavailable. Reload to try again.'; }
}
$('research-team').addEventListener('change', () => { selected = Number($('research-team').value); render(); });
$('research-season').addEventListener('change', render);
$('research-compare').addEventListener('change', renderProfile);
$('research-sort').addEventListener('change', renderLeaderboard);
$('trade-season').addEventListener('change', renderTrades);
$('trade-selected-only').addEventListener('change', renderTrades);
await load();
