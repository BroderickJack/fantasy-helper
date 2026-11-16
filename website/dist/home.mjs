import { fetchLeague, DEFAULT_TEAM_ID } from './data.mjs';
import { buildScoreboard } from './scoreboard-data.mjs';
import { renderMatchups, renderComparison, showScoreboardUnavailable, bindComparisonSort } from './scoreboard-view.mjs';
import { championships, managers, finalScores } from './history-data.mjs';

const $ = id => document.getElementById(id);
const points = value => value == null ? '—' : value.toFixed(2);

async function loadChampion() {
  try {
    const response = await fetch('history.json', { signal: AbortSignal.timeout(10000) });
    if (!response.ok) throw new Error('Could not load the reigning champion.');
    const archive = await response.json();
    const latest = championships(archive)[0];
    if (!latest) throw new Error('No championship records are available.');
    $('champion-season').textContent = `${latest.season} QRFFL CHAMPION`;
    $('defending-title').textContent = latest.champion.team_name;
    $('champion-manager').textContent = managers(latest.champion);
    const final = finalScores(latest);
    $('defending-score').textContent = final ? `${points(final.champion_score)} – ${points(final.runner_up_score)}` : '—';
    $('defending-opponent').textContent = latest.runner_up?.team_name ? `over ${latest.runner_up.team_name}` : '';
  } catch {
    $('defending-title').textContent = 'The record books are unavailable.';
    $('champion-manager').textContent = 'Visit the champions page or reload to try again.';
  } finally {
    $('defending-card').setAttribute('aria-busy', 'false');
  }
}

let snapshot = null;
let loading = false;
let lastAttemptFailed = false;
let sortKey = 'current';
let selectedTeam = DEFAULT_TEAM_ID;
try { selectedTeam = Number(localStorage.getItem('qrffl-team')) || DEFAULT_TEAM_ID; } catch { /* Optional preference. */ }

function renderLiveSnapshot() {
  if (!snapshot) return;
  $('home-week').textContent = `WEEK ${snapshot.week}`;
  $('home-current').textContent = points(snapshot.current);
  $('home-projected').textContent = points(snapshot.live);
  renderMatchups(snapshot, $('home-matchups'), { selectedTeam, stale: lastAttemptFailed });
  renderComparison(snapshot, $('home-teams'), { selectedTeam, sortKey });
  const time = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit', second: '2-digit' }).format(new Date(snapshot.fetchedAt));
  $('home-live-status').textContent = `${lastAttemptFailed ? 'Last successful fetch' : 'Fetched from ESPN'} at ${time} · Week ${snapshot.week}`;
}

async function loadLiveSnapshot() {
  if (loading) return;
  loading = true;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
  $('home-refresh').disabled = true;
  $('home-refresh').textContent = 'Refreshing…';
  $('home-matchups').setAttribute('aria-busy', 'true');
  $('home-comparison').setAttribute('aria-busy', 'true');
  try {
    const data = await fetchLeague(null, controller.signal);
    const next = buildScoreboard(data, data.scoringPeriodId);
    snapshot = next;
    lastAttemptFailed = false;
    renderLiveSnapshot();
    $('home-scores-error').hidden = true;
  } catch (error) {
    lastAttemptFailed = true;
    const message = error.name === 'AbortError' ? 'ESPN took too long to respond. Try refreshing again.' : 'Live scores are temporarily unavailable. Use Refresh to try again.';
    $('home-scores-error').textContent = `${message}${snapshot ? ` Showing the last successful Week ${snapshot.week} snapshot below.` : ''}`;
    $('home-scores-error').hidden = false;
    if (snapshot) renderLiveSnapshot();
    else {
      showScoreboardUnavailable($('home-matchups'), $('home-teams'), 'Scores could not be loaded. Use Refresh to try again.');
      $('home-live-status').textContent = 'No scores loaded yet. Refresh to retry.';
    }
  } finally {
    clearTimeout(timeout);
    loading = false;
    $('home-refresh').disabled = false;
    $('home-refresh').textContent = '↻ Refresh';
    $('home-matchups').setAttribute('aria-busy', 'false');
    $('home-comparison').setAttribute('aria-busy', 'false');
  }
}

$('home-refresh').addEventListener('click', loadLiveSnapshot);
bindComparisonSort($('home-comparison'), key => { sortKey = key; renderLiveSnapshot(); });
setInterval(() => { if ($('home-auto-refresh').checked && !document.hidden) loadLiveSnapshot(); }, 60000);
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && $('home-auto-refresh').checked && (!snapshot || Date.now() - Date.parse(snapshot.fetchedAt) > 60000)) loadLiveSnapshot();
});

Promise.allSettled([loadChampion(), loadLiveSnapshot()]);
