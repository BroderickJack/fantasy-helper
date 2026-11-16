export const LEAGUE_ID = 666462;
export const SEASON = 2026;
export const AVERAGE_TEAM_ID = 12;
export const DEFAULT_TEAM_ID = 16;
const BASE = `https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/${SEASON}/segments/0/leagues/${LEAGUE_ID}`;
const numeric = value => typeof value === 'number' && Number.isFinite(value);
export const nameOf = team => team.name || [team.location, team.nickname].filter(Boolean).join(' ') || `Team ${team.id}`;

export async function fetchLeague(week, signal) {
  const url = new URL(BASE);
  for (const view of ['mTeam', 'mSettings', 'mMatchupScore', 'mScoreboard']) url.searchParams.append('view', view);
  if (week != null) url.searchParams.set('scoringPeriodId', week);
  const response = await fetch(url, { signal, credentials: 'omit' });
  if (!response.ok) throw new Error(response.status === 401 || response.status === 403
    ? 'ESPN denied access to this league. It may no longer be public.' : `ESPN is unavailable (HTTP ${response.status}). Try refreshing shortly.`);
  const data = await response.json();
  if (!Array.isArray(data.teams)) throw new Error('ESPN returned an unexpected response. Try again shortly.');
  return data;
}

export function matchupPeriod(data, week) {
  const periods = data.settings?.scheduleSettings?.matchupPeriods ?? {};
  const matches = Object.entries(periods).filter(([, weeks]) => weeks.includes(week));
  if (matches.length !== 1) throw new Error(`No matchup is available for Week ${week}.`);
  if (matches[0][1].length !== 1) throw new Error('This week uses a multiweek matchup. Weekly averages are not supported for that format yet.');
  return Number(matches[0][0]);
}

function pregameProjection(side, week) {
  if (numeric(side.totalProjectedPoints)) return side.totalProjectedPoints;
  const entries = side.rosterForCurrentScoringPeriod?.entries;
  if (!entries?.length) return null;
  let sum = 0;
  for (const entry of entries) {
    if ([20, 21].includes(entry.lineupSlotId)) continue;
    if (entry.lineupSlotId == null) return null;
    const stats = entry.playerPoolEntry?.player?.stats ?? [];
    const projected = stats.filter(stat => stat.statSourceId === 1 && stat.statSplitTypeId === 1 && stat.seasonId === SEASON && stat.scoringPeriodId === week);
    if (projected.length !== 1 || !numeric(projected[0].appliedTotal)) return null;
    sum += projected[0].appliedTotal;
  }
  return sum;
}

export function summarize(data, week) {
  const period = matchupPeriod(data, week);
  const realTeams = data.teams.filter(team => team.id !== AVERAGE_TEAM_ID);
  if (realTeams.length !== 15 || !data.teams.some(team => team.id === AVERAGE_TEAM_ID)) throw new Error('The league team list changed. Expected 15 real teams and average placeholder #12.');
  const sides = new Map();
  let averageOpponent = null;
  for (const matchup of data.schedule ?? []) {
    if (matchup.matchupPeriodId !== period) continue;
    const pair = [matchup.home, matchup.away].filter(Boolean);
    if (pair.some(side => side.teamId === AVERAGE_TEAM_ID)) averageOpponent = pair.find(side => side.teamId !== AVERAGE_TEAM_ID)?.teamId ?? null;
    for (const side of pair) {
      const existing = sides.get(side.teamId);
      if (existing && ['totalPoints', 'totalPointsLive', 'totalProjectedPoints', 'totalProjectedPointsLive'].some(key => existing[key] !== side[key])) throw new Error(`ESPN returned conflicting scores for team ${side.teamId}.`);
      sides.set(side.teamId, side);
    }
  }
  const teams = realTeams.map(team => {
    const side = sides.get(team.id);
    if (!side) throw new Error(`Missing Week ${week} score for ${nameOf(team)}. A partial league average would be misleading.`);
    const current = numeric(side.totalPointsLive) ? side.totalPointsLive : side.totalPoints;
    if (!numeric(current)) throw new Error(`ESPN has not provided a score for ${nameOf(team)} yet.`);
    const live = numeric(side.totalPointsLive) && numeric(side.totalProjectedPointsLive) ? side.totalProjectedPointsLive : null;
    return { id: team.id, name: nameOf(team), current, live, pregame: pregameProjection(side, week) };
  });
  const average = key => teams.every(team => numeric(team[key])) ? teams.reduce((sum, team) => sum + team[key], 0) / teams.length : null;
  return { week, teams, averageOpponent, current: average('current'), live: average('live'), pregame: average('pregame'), fetchedAt: new Date().toISOString() };
}
