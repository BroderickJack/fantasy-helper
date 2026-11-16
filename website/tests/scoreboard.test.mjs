import test from 'node:test';
import assert from 'node:assert/strict';
import { buildScoreboard } from '../dist/scoreboard-data.mjs';

function fixture() {
  const teams = Array.from({ length: 16 }, (_, index) => ({ id: index + 1, name: `Team ${index + 1}` }));
  const side = id => ({ teamId: id, totalPoints: id * 10, totalPointsLive: id * 10, totalProjectedPointsLive: 120 + id });
  return { teams, scoringPeriodId: 10, settings: { scheduleSettings: { matchupPeriods: { 10: [10] } } },
    schedule: Array.from({ length: 8 }, (_, index) => ({ id: index + 1, matchupPeriodId: 10,
      home: side(index * 2 + 1), away: side(index * 2 + 2), winner: 'AWAY' })) };
}

test('preserves ESPN pairings and uses calculated Average in current matchup', () => {
  const data = fixture();
  data.schedule[5].away.totalPointsLive = 99999;
  const result = buildScoreboard(data, 10);
  assert.equal(result.matchups.length, 8);
  assert.equal(result.teams.length, 15);
  assert.deepEqual(result.matchups.map(game => [game.home.id, game.away.id]), data.schedule.map(game => [game.home.teamId, game.away.teamId]));
  const averageGame = result.matchups[5];
  assert.equal(averageGame.home.id, result.averageOpponent);
  assert.equal(averageGame.away.name, 'Laegue Average');
  assert.equal(averageGame.away.current, (1360 - 120) / 15);
  assert.equal(averageGame.away.live, result.live);
  assert.equal(averageGame.status, 'CURRENT WEEK');
  assert.equal(averageGame.winner, null);
});

test('past matchup keeps posted Average score and ESPN outcome separate from mean', () => {
  const data = fixture();
  data.schedule[5].away.totalPoints = 90.04;
  data.schedule[5].away.adjustment = 90.04;
  data.schedule[5].away.totalPointsLive = 0;
  data.schedule[5].winner = 'HOME';
  const result = buildScoreboard(data, 10, 11);
  assert.equal(result.matchups[5].away.current, 90.04);
  assert.notEqual(result.matchups[5].away.current, result.current);
  assert.equal(result.matchups[5].away.scoreBasis, 'recorded');
  assert.equal(result.matchups[5].away.live, null);
  assert.equal(result.matchups[5].winner, 'HOME');
  assert.equal(result.matchups[5].status, 'FINAL');
});

test('unposted historical placeholder zero stays unknown rather than becoming a loss', () => {
  const data = fixture();
  data.schedule[5].away.totalPoints = 0;
  const match = buildScoreboard(data, 10, 11).matchups[5];
  assert.equal(match.away.current, null);
  assert.equal(match.winner, null);
  assert.equal(match.status, 'AWAITING SCORE');
});

test('real zero scores and a zero calculated Average survive', () => {
  const data = fixture();
  for (const game of data.schedule) for (const side of [game.home, game.away]) side.totalPointsLive = side.totalPoints = 0;
  const result = buildScoreboard(data, 10);
  assert.equal(result.current, 0);
  assert.equal(result.matchups[5].away.current, 0);
  assert.equal(result.matchups[0].home.current, 0);
  assert.equal(buildScoreboard(data, 10, 11).matchups[5].away.current, 0);
});

test('missing projection is unknown in matchup and prevents a partial projected mean', () => {
  const data = fixture();
  delete data.schedule[0].home.totalProjectedPointsLive;
  const result = buildScoreboard(data, 10);
  assert.equal(result.matchups[0].home.live, null);
  assert.equal(result.live, null);
  assert.equal(result.matchups[5].away.live, null);
});

test('deduplicates identical matches and rejects conflicting matchup identities', () => {
  const data = fixture();
  data.schedule.push(structuredClone(data.schedule[0]));
  assert.equal(buildScoreboard(data, 10).matchups.length, 8);
  data.schedule.at(-1).home = structuredClone(data.schedule[1].home);
  assert.throws(() => buildScoreboard(data, 10), /conflicting matchup/);
});

test('other periods are excluded from matchup cards', () => {
  const data = fixture();
  const other = structuredClone(data.schedule[0]); other.matchupPeriodId = 9;
  data.schedule.push(other);
  assert.equal(buildScoreboard(data, 10).matchups.length, 8);
});

test('byes have no invented opponent or zero score', () => {
  const data = fixture();
  const away = data.schedule[0].away;
  delete data.schedule[0].away;
  data.schedule.push({ id: 99, matchupPeriodId: 10, away });
  const result = buildScoreboard(data, 10);
  assert.equal(result.teams.length, 15);
  assert.equal(result.matchups[0].away, null);
  assert.equal(result.matchups.at(-1).home, null);
});

test('future scheduled matches are marked upcoming', () => {
  const result = buildScoreboard(fixture(), 10, 9);
  assert.equal(result.matchups[0].status, 'UPCOMING');
  assert.equal(result.matchups[0].winner, null);
});
