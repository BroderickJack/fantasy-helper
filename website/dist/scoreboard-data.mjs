import { summarize, matchupPeriod, AVERAGE_TEAM_ID } from './data.mjs';

export function buildScoreboard(data, week, currentWeek = week) {
  const snapshot = summarize(data, week);
  const period = matchupPeriod(data, week);
  const byTeam = new Map(snapshot.teams.map(team => [team.id, team]));
  const historical = week < currentWeek;
  const matches = new Map();
  for (const game of data.schedule ?? []) {
    if (game.matchupPeriodId !== period) continue;
    function side(key) {
      const raw = game[key];
      if (!raw) return null;
      if (raw.teamId !== AVERAGE_TEAM_ID) {
        const team = byTeam.get(raw.teamId);
        if (!team) throw new Error(`No score is available for matchup team ${raw.teamId}.`);
        return { ...team, isAverage: false };
      }
      const posted = Number.isFinite(raw.totalPoints) && (raw.totalPoints !== 0 || raw.adjustment || snapshot.current === 0) ? raw.totalPoints : null;
      return { id: AVERAGE_TEAM_ID, name: 'Laegue Average', isAverage: true,
        current: historical ? posted : snapshot.current,
        live: historical ? null : snapshot.live, scoreBasis: historical ? 'recorded' : 'calculated' };
    }
    const home = side('home'), away = side('away');
    const completed = historical && ['HOME', 'AWAY', 'TIE'].includes(game.winner)
      && home?.current != null && away?.current != null;
    const match = { id: game.id ?? `${period}:${game.home?.teamId ?? 'bye'}:${game.away?.teamId ?? 'bye'}`,
      home, away, winner: completed ? game.winner : null,
      status: historical ? completed ? 'FINAL' : 'AWAITING SCORE' : week > currentWeek ? 'UPCOMING' : 'CURRENT WEEK',
      historical };
    if (!match.home && !match.away) continue;
    const key = String(match.id);
    const previous = matches.get(key);
    if (previous && JSON.stringify(previous) !== JSON.stringify(match)) throw new Error('ESPN returned conflicting matchup details.');
    matches.set(key, match);
  }
  if (!matches.size) throw new Error(`No scheduled matchups are available for Week ${week}.`);
  return { ...snapshot, historical, matchups: [...matches.values()] };
}
