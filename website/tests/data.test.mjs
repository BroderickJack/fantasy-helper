import test from 'node:test';
import assert from 'node:assert/strict';
import { summarize, matchupPeriod } from '../dist/data.mjs';

function fixture() {
  const teams = Array.from({ length: 16 }, (_, index) => ({ id: index + 1, name: `Team ${index + 1}` }));
  const side = id => ({ teamId: id, totalPoints: 0, totalPointsLive: id * 10, totalProjectedPoints: 100 + id, totalProjectedPointsLive: 120 + id });
  return { teams, scoringPeriodId: 10, settings: { scheduleSettings: { matchupPeriods: { 10: [10] } } }, schedule: Array.from({ length: 8 }, (_, index) => ({ matchupPeriodId: 10, home: side(index * 2 + 1), away: side(index * 2 + 2) })) };
}
test('averages all 15 real teams, never placeholder; uses live scores', () => {
  const data = fixture();
  data.schedule[5].away.totalPointsLive = 999999;
  const result = summarize(data, 10);
  assert.equal(result.teams.length, 15);
  assert.equal(result.current, (1360 - 120) / 15);
  assert.equal(result.live, (1920 + 136 - 132) / 15);
  assert.equal(result.pregame, (1600 + 136 - 112) / 15);
  assert.equal(result.averageOpponent, 11);
});
test('missing scores and wrong team counts refuse partial averages', () => {
  const data = fixture();
  delete data.schedule[0].away;
  assert.throws(() => summarize(data, 10), /Missing Week/);
  const other = fixture(); other.teams.pop();
  assert.throws(() => summarize(other, 10), /team list changed/);
});
test('missing live projections remain unknown; zero scores and projections survive', () => {
  const data = fixture();
  data.schedule[0].home.totalPointsLive = 0;
  data.schedule[0].home.totalProjectedPointsLive = 0;
  assert.equal(summarize(data, 10).teams[0].live, 0);
  delete data.schedule[0].home.totalProjectedPointsLive;
  assert.equal(summarize(data, 10).live, null);
});
test('historical fallback and negative points are preserved', () => {
  const data = fixture();
  delete data.schedule[0].home.totalPointsLive;
  data.schedule[0].home.totalPoints = -2;
  assert.equal(summarize(data, 10).teams[0].current, -2);
  assert.equal(summarize(data, 10).teams[0].live, null);
});
test('other weeks are excluded and identical duplicates count once', () => {
  const data = fixture();
  data.schedule.push(structuredClone(data.schedule[0]));
  const other = structuredClone(data.schedule[0]); other.matchupPeriodId = 9; other.home.totalPointsLive = 999;
  data.schedule.push(other);
  assert.equal(summarize(data, 10).current, (1360 - 120) / 15);
});
test('conflicting duplicates are rejected', () => {
  const data = fixture();
  const duplicate = structuredClone(data.schedule[0]); duplicate.home.totalPointsLive = 999;
  data.schedule.push(duplicate);
  assert.throws(() => summarize(data, 10), /conflicting scores/);
});
test('multiweek totals are never mistaken for a weekly average', () => {
  const data = fixture(); data.settings.scheduleSettings.matchupPeriods[10] = [10, 11];
  assert.throws(() => matchupPeriod(data, 10), /multiweek/);
});
