// Reuse the league-average snapshot; the placeholder's ESPN zero is never its score.
export function supporterSnapshot(snapshot) {
  const opponent = snapshot.teams.find(team => team.id === snapshot.averageOpponent) ?? null;
  const currentMargin = opponent ? snapshot.current - opponent.current : null;
  const projectedMargin = opponent && snapshot.live != null && opponent.live != null ? snapshot.live - opponent.live : null;
  const mood = currentMargin == null ? 'unknown' : Math.abs(currentMargin) < 1e-9 ? 'level' : currentMargin > 0 ? 'ahead' : 'behind';
  const contributor = snapshot.teams.reduce((top, team) => !top || team.current > top.current ? team : top, null);
  return { opponent, currentMargin, projectedMargin, mood, contributor };
}
