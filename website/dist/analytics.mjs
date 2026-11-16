const $ = id => document.getElementById(id);
const score = cents => (cents / 100).toFixed(2);
const record = value => `${value.wins}–${value.losses}${value.ties ? `–${value.ties}` : ''}`;
const clauses = value => value.clauses.length === 2 ? value.clauses.join(' and ') : `${value.clauses.slice(0, -1).join(', ')}, and ${value.clauses.at(-1)}`;
const sentence = value => `${value.team} has a ${record(value.record)} record ${clauses(value)}.`;
const categoryLabels = { 'Week math': 'Week & season splits', 'Score quirks': 'Scoring splits', Bouncebacks: 'Previous-game splits', Rivalries: 'Head-to-head' };
let archive;
let games;
let filtered = [];
let featured;
let visible = 12;

function feature(stat) {
  featured = stat;
  $('feature-title').textContent = sentence(stat);
  $('feature-category').textContent = (categoryLabels[stat.category] ?? stat.category).toUpperCase();
  const seasons = [...new Set(stat.game_ids.map(id => games.get(id).season))].sort();
  $('feature-sample').textContent = `${stat.sample_size} matching games · ${seasons.length} seasons`;
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function sourceLink(game, text = 'ESPN ↗') {
  const link = element('a', '', text);
  link.href = `https://fantasy.espn.com/football/scoreboard?leagueId=${archive.league_id}&seasonId=${game.season}&matchupPeriodId=${game.matchup_period}`;
  link.target = '_blank'; link.rel = 'noopener noreferrer';
  link.setAttribute('aria-label', `View ${game.team_name}, ${game.season} Week ${game.week} on ESPN`);
  return link;
}

function receipts(stat, details) {
  const wrap = element('div', 'receipt-wrap');
  const table = element('table', 'receipt-table');
  const caption = element('caption', 'sr-only', `Every matching game for ${stat.team}: ${clauses(stat)}.`);
  const previous = stat.conditions.some(condition => condition.startsWith('after-'));
  const headers = ['YEAR', 'WEEK', 'TEAM / OPPONENT', 'SCORE', 'RESULT', ...(previous ? ['PREVIOUS WEEK'] : []), 'SOURCE'];
  const head = document.createElement('thead'); const header = document.createElement('tr');
  for (const title of headers) { const th = element('th', '', title); th.scope = 'col'; header.append(th); }
  head.append(header);
  const body = document.createElement('tbody');
  for (const id of stat.game_ids) {
    const game = games.get(id); const row = document.createElement('tr');
    row.append(element('td', '', game.season), element('td', '', game.week));
    const names = element('td', 'receipt-name', `${game.team_name} vs ${game.opponent_name}`);
    row.append(names, element('td', '', `${score(game.score)}–${score(game.opponent_score)}`), element('td', game.result === 'L' ? 'negative' : 'positive', game.result));
    if (previous) {
      const cell = document.createElement('td');
      const prior = games.get(game.previous_id);
      if (prior) cell.append(sourceLink(prior, `${prior.result} by ${score(Math.abs(prior.score - prior.opponent_score))}`));
      else cell.textContent = '—';
      row.append(cell);
    }
    const source = document.createElement('td'); source.append(sourceLink(game)); row.append(source);
    body.append(row);
  }
  table.append(caption, head, body); wrap.append(table); details.append(wrap);
  details.append(element('p', 'receipt-count', `All ${stat.sample_size} matching games are listed. Scores are this team first. W–L${stat.record.ties ? '–T' : ''} follows ESPN’s declared result.`));
}

function card(stat) {
  const article = element('article', 'stat-card');
  const top = element('div', 'stat-card-top');
  top.append(element('span', 'stat-category', categoryLabels[stat.category] ?? stat.category), element('span', 'sample-badge', `${stat.sample_size} GAMES`));
  const metric = element('div', 'stat-record');
  metric.append(element('strong', stat.record.losses > stat.record.wins ? 'negative' : '', record(stat.record)), element('span', '', stat.record.ties ? 'WIN–LOSS–TIE' : 'WIN–LOSS'));
  article.append(top, metric, element('h3', '', stat.team), element('p', 'stat-clauses', `${clauses(stat)}.`));
  article.append(element('p', 'stat-context', `${stat.sample_size} of ${stat.overall_sample_size} archived games match these conditions. Overall record: ${record(stat.overall_record)}.`));
  const details = element('details', 'stat-receipts');
  details.append(element('summary', '', `View game log · ${stat.sample_size} games`));
  let loaded = false;
  details.addEventListener('toggle', () => { if (details.open && !loaded) { receipts(stat, details); loaded = true; } });
  article.append(details);
  return article;
}

function showCards() {
  const fragment = document.createDocumentFragment();
  for (const stat of filtered.slice(0, visible)) fragment.append(card(stat));
  if (!filtered.length) fragment.append(element('p', 'analytics-empty', 'No records match those filters. Try another team, category, or split detail.'));
  $('analytics-cards').replaceChildren(fragment);
  $('analytics-status').textContent = `${filtered.length} statistical notes match · ${Math.min(visible, filtered.length)} shown · Every record has at least ${archive.min_sample} games.`;
  $('show-more').hidden = filtered.length <= visible;
}

function applyFilters() {
  const team = $('analytics-team').value;
  const category = $('analytics-category').value;
  const specificity = $('analytics-specificity').value;
  filtered = archive.stats.filter(stat => (team === 'all' || stat.team_id === Number(team)) && (category === 'all' || stat.category === category) && (specificity === 'all' || stat.conditions.length === Number(specificity)));
  visible = 12;
  if (filtered.length) feature(filtered[0]);
  else {
    featured = null;
    $('feature-title').textContent = 'No records match this selection.';
    $('feature-category').textContent = 'NO MATCHES';
    $('feature-sample').textContent = 'Change a filter to view another statistical note.';
  }
  $('another-stat').disabled = filtered.length < 2;
  $('copy-feature').disabled = !featured;
  showCards();
}

async function load() {
  try {
    const response = await fetch('analytics.json');
    if (!response.ok) throw new Error('The analytics archive could not be loaded. Please reload to try again.');
    archive = await response.json();
    games = new Map(archive.games.map(game => [game.id, game]));
    const teamIds = new Set(archive.stats.map(stat => stat.team_id));
    for (const team of archive.teams.filter(team => teamIds.has(team.id)).sort((a, b) => a.name.localeCompare(b.name))) {
      $('analytics-team').append(new Option(team.name, String(team.id)));
    }
    for (const id of ['analytics-team', 'analytics-category', 'analytics-specificity']) $(id).disabled = false;
    $('archive-size').textContent = `${archive.game_count.toLocaleString()} completed matchups · ${archive.seasons[0]}–${archive.seasons.at(-1)}`;
    const date = new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'short', day: 'numeric' }).format(new Date(archive.checked_at));
    $('analytics-checked').textContent = `Archive checked ${date}. ${archive.stats.length} statistical notes from ${archive.game_count} matchups. Each matchup contributes one observation per team; records count team observations, not twice as many games.`;
    applyFilters();
  } catch (error) {
    $('analytics-error').textContent = error.message;
    $('analytics-error').hidden = false;
    $('feature-title').textContent = 'Statistical notes are temporarily unavailable.';
    $('feature-category').textContent = 'UNAVAILABLE';
    $('feature-sample').textContent = 'Reload the page to try again.';
    $('analytics-status').textContent = 'No analytics loaded.';
  } finally { $('feature').setAttribute('aria-busy', 'false'); }
}

for (const id of ['analytics-team', 'analytics-category', 'analytics-specificity']) $(id).addEventListener('change', applyFilters);
$('another-stat').addEventListener('click', () => {
  const choices = filtered.filter(stat => stat.id !== featured?.id);
  if (choices.length) feature(choices[Math.floor(Math.random() * choices.length)]);
});
$('copy-feature').addEventListener('click', async () => {
  if (!featured) return;
  try {
    await navigator.clipboard.writeText(`Q-alytics\n${sentence(featured)}\nQRFFL ${archive.seasons[0]}–${archive.seasons.at(-1)}, n=${featured.sample_size}. Long Live the Quail.`);
    $('analytics-status').textContent = 'Stat copied.';
  } catch { $('analytics-status').textContent = 'Copy is unavailable in this browser. You can select and copy the stat above.'; }
});
$('show-more').addEventListener('click', () => { visible += 12; showCards(); });
await load();
