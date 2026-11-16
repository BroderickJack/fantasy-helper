import { fetchLeague, DEFAULT_TEAM_ID } from './data.mjs';
import { buildScoreboard } from './scoreboard-data.mjs';
import { renderMatchups, renderComparison, showScoreboardUnavailable, bindComparisonSort } from './scoreboard-view.mjs';

const $ = id => document.getElementById(id);
const points = value => value == null ? '—' : value.toFixed(2);
const signed = value => value == null ? '—' : `${value > 0 ? '+' : value < 0 ? '−' : ''}${Math.abs(value).toFixed(2)}`;
let snapshot = null;
let selectedTeam = DEFAULT_TEAM_ID;
let selectedWeek = null;
let currentWeek = null;
let sortKey = 'current';
let controller;
let loading = false;
let lastAttemptFailed = false;
try { selectedTeam = Number(localStorage.getItem('qrffl-team')) || DEFAULT_TEAM_ID; } catch { /* Browser storage is optional. */ }

function fillWeeks(data) {
  const weeks = [...new Set(Object.values(data.settings?.scheduleSettings?.matchupPeriods ?? {}).flat())]
    .filter(week => Number.isInteger(week) && week > 0).sort((a, b) => a - b);
  const desired = selectedWeek ?? data.scoringPeriodId;
  if (!weeks.includes(desired)) throw new Error('ESPN has no active scoring week. Pick an available week to continue.');
  selectedWeek = desired;
  $('week').replaceChildren(...weeks.map(week => {
    const option = new Option(`Week ${week}${week === currentWeek ? ' · Current' : ''}`, String(week));
    option.selected = week === desired;
    return option;
  }));
  $('week').disabled = false;
}

function fillTeams() {
  if (!snapshot.teams.some(team => team.id === selectedTeam)) selectedTeam = DEFAULT_TEAM_ID;
  $('team').replaceChildren(...[...snapshot.teams].sort((a, b) => a.name.localeCompare(b.name)).map(team => {
    const option = new Option(team.name, String(team.id));
    option.selected = team.id === selectedTeam;
    return option;
  }));
  $('team').disabled = false;
}

function tone(element, value) {
  element.classList.toggle('positive', value != null && value > 0);
  element.classList.toggle('negative', value != null && value < 0);
}

function render() {
  if (!snapshot) return;
  const active = snapshot.teams.find(team => team.id === selectedTeam);
  $('average-current').textContent = points(snapshot.current);
  $('average-live').textContent = snapshot.live == null ? 'Unavailable' : points(snapshot.live);
  $('pregame-average').textContent = snapshot.pregame == null ? 'Unavailable' : `${points(snapshot.pregame)} points`;
  $('team-current').textContent = points(active.current);
  $('team-live').textContent = active.live == null ? 'Unavailable' : points(active.live);
  const margin = active.current - snapshot.current;
  $('team-margin').textContent = `${signed(margin)} vs average`;
  tone($('team-margin'), margin);
  const projectedMargin = active.live != null && snapshot.live != null ? active.live - snapshot.live : null;
  $('team-live-margin').textContent = projectedMargin == null ? 'Projection unavailable' : `${signed(projectedMargin)} vs average`;
  tone($('team-live-margin'), projectedMargin);
  const rank = 1 + snapshot.teams.filter(team => team.current > active.current).length;
  $('team-rank').textContent = `${rank} / 15 BY SCORE`;
  $('team-note').textContent = active.id === snapshot.averageOpponent
    ? `Facing the league-average team in Week ${snapshot.week}. This is the number to beat.`
    : `Following ${active.name}. ${snapshot.teams.find(team => team.id === snapshot.averageOpponent)?.name ?? 'A league team'} faces the average this week.`;
  $('snapshot-state').textContent = lastAttemptFailed ? 'STALE SNAPSHOT' : snapshot.week === currentWeek ? 'CURRENT WEEK' : `WEEK ${snapshot.week}`;
  renderMatchups(snapshot, $('matchups'), { selectedTeam, stale: lastAttemptFailed });
  renderComparison(snapshot, $('teams'), { selectedTeam, sortKey });
  $('matchup-context').textContent = snapshot.historical
    ? 'Past matchup scores. Laegue Average uses its posted score; the comparison below uses the calculated all-team mean.'
    : 'Actual matchup scores, with projected final totals underneath. Laegue Average is calculated from all 15 real teams.';
  const time = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit', second: '2-digit' }).format(new Date(snapshot.fetchedAt));
  $('updated').textContent = `${lastAttemptFailed ? 'Last successful fetch' : 'Fetched from ESPN'} at ${time} · Week ${snapshot.week}`;
}

async function refresh() {
  if (loading) return;
  loading = true;
  controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 25000);
  $('refresh').disabled = true;
  $('week').disabled = true;
  $('refresh').textContent = 'Refreshing…';
  $('scoreboard').setAttribute('aria-busy', 'true');
  $('matchups').setAttribute('aria-busy', 'true');
  try {
    let data = await fetchLeague(null, controller.signal);
    currentWeek = data.scoringPeriodId;
    fillWeeks(data);
    $('week').disabled = true;
    data = await fetchLeague(selectedWeek, controller.signal);
    const next = buildScoreboard(data, selectedWeek, currentWeek);
    snapshot = next;
    lastAttemptFailed = false;
    fillTeams();
    render();
    $('error').hidden = true;
  } catch (error) {
    lastAttemptFailed = true;
    const message = error.name === 'AbortError' ? 'ESPN took too long to respond. Try refreshing again.'
      : error instanceof TypeError ? 'Could not connect to ESPN. Check your internet connection and try again.' : error.message;
    $('error').textContent = `${message}${snapshot ? ` Showing the last successful Week ${snapshot.week} snapshot below.` : ''}`;
    $('error').hidden = false;
    if (snapshot) render();
    else {
      $('snapshot-state').textContent = 'UNAVAILABLE';
      $('updated').textContent = 'No scores loaded yet. Refresh to retry.';
      showScoreboardUnavailable($('matchups'), $('teams'), 'Scores could not be loaded. Use Refresh to try again.');
    }
  } finally {
    clearTimeout(timeout);
    loading = false;
    $('refresh').disabled = false;
    $('week').disabled = $('week').options.length === 0 || !Number.isInteger(selectedWeek);
    $('refresh').textContent = '↻ Refresh';
    $('scoreboard').setAttribute('aria-busy', 'false');
    $('matchups').setAttribute('aria-busy', 'false');
  }
}

$('refresh').addEventListener('click', refresh);
$('week').addEventListener('change', () => { selectedWeek = Number($('week').value); refresh(); });
$('team').addEventListener('change', () => {
  selectedTeam = Number($('team').value);
  try { localStorage.setItem('qrffl-team', String(selectedTeam)); } catch { /* Optional preference. */ }
  render();
});
bindComparisonSort($('league-comparison'), key => { sortKey = key; render(); });
setInterval(() => { if ($('auto-refresh').checked && !document.hidden) refresh(); }, 60000);
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && $('auto-refresh').checked && (!snapshot || Date.now() - Date.parse(snapshot.fetchedAt) > 60000)) refresh();
});
refresh();
