import { fetchLeague, summarize } from './data.mjs';
import { supporterSnapshot } from './average-data.mjs';
import { loadAverageHistory } from './average-history.mjs';

const $ = id => document.getElementById(id);
const points = value => value == null ? 'Unavailable' : value.toFixed(2);
const margin = value => Math.abs(value) < .005 && Math.abs(value) > 1e-9 ? 'less than 0.01' : Math.abs(value).toFixed(2);
let snapshot;
let loading = false;

function render(stale = false) {
  const state = supporterSnapshot(snapshot);
  $('average-week').textContent = `WEEK ${snapshot.week}`;
  $('club-score').textContent = points(snapshot.current);
  $('club-projected').textContent = points(snapshot.live);
  $('club-opponent').textContent = state.opponent?.name ?? 'Opponent not assigned';
  $('opponent-score').textContent = state.opponent ? points(state.opponent.current) : '—';
  $('opponent-projected').textContent = state.opponent ? points(state.opponent.live) : '—';
  const messages = {
    ahead: ['LEADING', `The Average leads by ${margin(state.currentMargin)} points.`],
    behind: ['TRAILING', `The Average trails by ${margin(state.currentMargin)} points.`],
    level: ['LEVEL', 'The matchup is level on points.'],
    unknown: ['UNASSIGNED', 'No opponent is assigned in this snapshot.'],
  };
  $('matchday-state').textContent = stale ? 'STALE SNAPSHOT' : messages[state.mood][0];
  $('matchday-hype').textContent = messages[state.mood][1];
  $('projected-edge').textContent = state.projectedMargin == null ? 'Projected margin unavailable.'
    : Math.abs(state.projectedMargin) < 1e-9 ? 'Projected level on points.'
    : `Projected ${state.projectedMargin > 0 ? 'lead' : 'deficit'}: ${margin(state.projectedMargin)} pts`;
  if (state.contributor) {
    $('mean-contributor').textContent = `Largest current contribution: ${state.contributor.name}, adding ${(state.contributor.current / snapshot.teams.length).toFixed(2)} points to the ${points(snapshot.current)} average.`;
  }
  const time = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit', second: '2-digit' }).format(new Date(snapshot.fetchedAt));
  $('average-updated').textContent = `${stale ? 'Last successful fetch' : 'Fetched from ESPN'} at ${time} · Updates every 60s while visible`;
}

async function refresh() {
  if (loading) return;
  loading = true;
  $('average-refresh').disabled = true;
  $('average-scoreboard').setAttribute('aria-busy', 'true');
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 25000);
  try {
    const meta = await fetchLeague(null, controller.signal);
    const data = await fetchLeague(meta.scoringPeriodId, controller.signal);
    snapshot = summarize(data, meta.scoringPeriodId);
    render();
    $('average-error').hidden = true;
  } catch {
    $('average-error').textContent = `Live scores are temporarily unavailable.${snapshot ? ` Showing the last successful Week ${snapshot.week} snapshot.` : ' Refresh to try again.'}`;
    $('average-error').hidden = false;
    if (snapshot) render(true);
    else {
      $('club-opponent').textContent = 'Opponent unavailable';
      $('matchday-state').textContent = 'LIVE DATA UNAVAILABLE';
      $('matchday-hype').textContent = 'Current matchup data could not be loaded.';
      $('average-updated').textContent = 'No scores loaded yet. Refresh to retry.';
    }
  } finally {
    clearTimeout(timeout);
    loading = false;
    $('average-refresh').disabled = false;
    $('average-scoreboard').setAttribute('aria-busy', 'false');
  }
}

$('average-refresh').addEventListener('click', refresh);
setInterval(() => { if (!document.hidden) refresh(); }, 60000);
document.addEventListener('visibilitychange', () => { if (!document.hidden && (!snapshot || Date.now() - Date.parse(snapshot.fetchedAt) > 60000)) refresh(); });
await Promise.allSettled([refresh(), loadAverageHistory()]);
