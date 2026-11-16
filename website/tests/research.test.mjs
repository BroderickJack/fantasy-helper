import test from 'node:test';
import assert from 'node:assert/strict';
import { combineSeasons, headToHead } from '../dist/research-data.mjs';

const rows = () => [
  { team_id: 1, games: 1, wins: 1, losses: 0, ties: 0, points_for: 100, scoring_index: 80, all_play_wins: 1, all_play_comparisons: 3, expected_wins: 1/3, schedule_swing: 2/3 },
  { team_id: 1, games: 3, wins: 1, losses: 1, ties: 1, points_for: 600, scoring_index: 120, all_play_wins: 6, all_play_comparisons: 9, expected_wins: 2, schedule_swing: -.5 },
];
test('all-season aggregation weights points and scoring index by games', () => {
  const result = combineSeasons(rows());
  assert.equal(result.ppg, 175);
  assert.equal(result.scoring_index, 110);
  assert.equal(result.all_play_pct, 7/12);
  assert.equal(result.win_pct, 2.5/4);
  assert.ok(Math.abs(result.expected_wins - 7/3) < 1e-10);
});
test('missing season metrics remain unavailable in the combined model', () => {
  const values = rows(); values[1].scoring_index = null; values[1].expected_wins = null;
  const result = combineSeasons(values);
  assert.equal(result.scoring_index, null);
  assert.equal(result.expected_wins, null);
  assert.equal(combineSeasons([]), null);
});
test('head-to-head counts only the chosen direction and preserves ties', () => {
  const result = headToHead([
    { team_id: 1, opponent_id: 2, result: 'W' }, { team_id: 2, opponent_id: 1, result: 'L' },
    { team_id: 1, opponent_id: 2, result: 'T' }, { team_id: 1, opponent_id: 3, result: 'L' },
  ], 1, 2);
  assert.deepEqual(result, { games: 2, wins: 1, losses: 0, ties: 1 });
});
