import test from 'node:test';
import assert from 'node:assert/strict';
import { supporterSnapshot } from '../dist/average-data.mjs';

const snapshot = () => ({ current: 100.25, live: 120, averageOpponent: 3,
  teams: [{ id: 1, name: 'Contributor', current: 150, live: 160 }, { id: 3, name: 'Opponent', current: 90, live: 130 }] });

test('uses the calculated average, with independent current and projected margins', () => {
  const result = supporterSnapshot(snapshot());
  assert.equal(result.opponent.name, 'Opponent');
  assert.equal(result.currentMargin, 10.25);
  assert.equal(result.projectedMargin, -10);
  assert.equal(result.mood, 'ahead');
  assert.equal(result.contributor.id, 1);
});

test('missing projections are unknown, not zero or a pregame fallback', () => {
  const data = snapshot(); data.live = null;
  assert.equal(supporterSnapshot(data).projectedMargin, null);
  data.live = 120; data.teams[1].live = null;
  assert.equal(supporterSnapshot(data).projectedMargin, null);
});

test('a missing opponent cannot produce a claimed lead', () => {
  const data = snapshot(); data.averageOpponent = null;
  const result = supporterSnapshot(data);
  assert.equal(result.opponent, null);
  assert.equal(result.currentMargin, null);
  assert.equal(result.projectedMargin, null);
  assert.equal(result.mood, 'unknown');
});

test('zero scores and negative scores remain valid', () => {
  const data = snapshot(); data.current = 0; data.live = 0; data.teams[1].current = 0; data.teams[1].live = 0;
  assert.equal(supporterSnapshot(data).mood, 'level');
  assert.equal(supporterSnapshot(data).projectedMargin, 0);
  data.current = -2; data.teams[1].current = -3;
  assert.equal(supporterSnapshot(data).mood, 'ahead');
  data.teams[1].current = 5;
  assert.equal(supporterSnapshot(data).mood, 'behind');
});

test('floating-point noise is not presented as a lead', () => {
  const data = snapshot(); data.current = 100.10000000000001; data.teams[1].current = 100.1;
  assert.equal(supporterSnapshot(data).mood, 'level');
});
