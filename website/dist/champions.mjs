import { championships, managers, finalScores, sourceDetails } from './history-data.mjs';

const $ = id => document.getElementById(id);
const points = value => value.toFixed(2);
let archive;

function addCell(row, value, className) {
  const cell = document.createElement('td');
  cell.textContent = value;
  cell.className = className;
  row.append(cell);
  return cell;
}

function showHistory() {
  const query = $('history-search').value.trim().toLocaleLowerCase();
  const seasons = championships(archive);
  const matches = seasons.filter(entry => [entry.season, entry.champion.team_name, managers(entry.champion), entry.runner_up?.team_name, managers(entry.runner_up)].join(' ').toLocaleLowerCase().includes(query));
  const rows = document.createDocumentFragment();
  for (const entry of matches) {
    const row = document.createElement('tr');
    row.classList.toggle('latest-champion', entry.season === seasons[0].season);
    addCell(row, entry.season, 'season-cell');
    const champion = addCell(row, '', 'champion-cell');
    const name = document.createElement('strong'); name.textContent = entry.champion.team_name;
    const manager = document.createElement('small'); manager.textContent = managers(entry.champion);
    champion.append(name, manager);
    addCell(row, entry.runner_up?.team_name || '—', 'runner-cell');
    const final = finalScores(entry);
    addCell(row, final ? `${points(final.champion_score)} – ${points(final.runner_up_score)}` : '—', 'number final-score');
    const cell = addCell(row, '', 'number');
    const details = document.createElement('details'); details.className = 'record-details';
    const summary = document.createElement('summary'); summary.textContent = 'Details';
    details.append(summary);
    const source = sourceDetails(entry);
    const label = document.createElement('p'); label.textContent = source.label || 'League records'; details.append(label);
    if (source.note) { const note = document.createElement('p'); note.textContent = source.note; details.append(note); }
    if (source.url && /^https?:\/\//i.test(source.url)) {
      const link = document.createElement('a');
      link.textContent = 'View source ↗'; link.href = source.url;
      link.target = '_blank'; link.rel = 'noopener noreferrer'; link.className = 'source-link';
      link.setAttribute('aria-label', `View source for the ${entry.season} championship`);
      details.append(link);
    }
    cell.append(details); rows.append(row);
  }
  if (!matches.length) {
    const row = document.createElement('tr');
    const cell = addCell(row, 'No championships match that search.', 'loading-cell');
    cell.colSpan = 5; rows.append(row);
  }
  $('history-rows').replaceChildren(rows);
  $('history-count').textContent = `${matches.length} of ${seasons.length} championships shown · Final scores list the champion first.`;
}

async function loadHistory() {
  try {
    const response = await fetch('history.json');
    if (!response.ok) throw new Error('The champions archive could not be loaded. Please reload the page.');
    archive = await response.json();
    const seasons = championships(archive);
    if (!seasons.length) throw new Error('No championship records are available yet.');
    const latest = seasons[0];
    const years = `${seasons.at(-1).season}–${latest.season}`;
    $('archive-coverage').textContent = `${years} · The teams and people who took the title.`;
    const scored = seasons.filter(entry => finalScores(entry));
    if (scored.length) {
      const closest = [...scored].sort((a, b) => (a.final.champion_score - a.final.runner_up_score) - (b.final.champion_score - b.final.runner_up_score))[0];
      $('closest-score').textContent = `${points(closest.final.champion_score - closest.final.runner_up_score)} pts`;
      $('closest-detail').textContent = `${closest.season} · ${closest.champion.team_name}`;
      const highest = [...scored].sort((a, b) => b.final.champion_score - a.final.champion_score)[0];
      $('highest-score').textContent = points(highest.final.champion_score);
      $('highest-detail').textContent = `${highest.season} · ${highest.champion.team_name}`;
    }
    $('championship-count').textContent = String(seasons.length).padStart(2, '0');
    $('championship-years').textContent = `${years} · League history`;
    $('archive-records').hidden = false;
    const gaps = archive.seasons.filter(entry => !entry.champion?.team_name);
    $('history-gaps').textContent = gaps.length ? `Seasons still to add: ${gaps.map(entry => entry.season).join(', ')}.` : '';
    $('history-gaps').hidden = !gaps.length;
    const date = new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'short', day: 'numeric' }).format(new Date(archive.checked_at));
    $('history-checked').textContent = `Record book updated ${date}. The ${archive.current_season} season is still in progress.`;
    showHistory();
  } catch (error) {
    archive = null;
    $('history-error').textContent = error.message;
    $('history-error').hidden = false;
    $('history-rows').replaceChildren();
  }
}

$('history-search').addEventListener('input', () => { if (archive) showHistory(); });
await loadHistory();
