import test from 'node:test';
import assert from 'node:assert/strict';
import { championships, managers, finalScores, sourceDetails } from '../dist/history-data.mjs';

test('league and ESPN championships appear in one chronological archive', () => {
  const archive = { seasons: [
    { season: 2017, status: 'recorded', champion: { team_name: 'Early winner' }, source: { type: 'league', label: 'League records' } },
    { season: 2025, status: 'verified', champion: { team_name: 'Recent winner' } },
    { season: 2016, champion: { team_name: 'Another early winner' } },
    { season: 2018, status: 'unavailable' },
  ] };
  assert.deepEqual(championships(archive).map(entry => entry.season), [2025, 2017, 2016]);
});

test('an older champion does not require a runner-up, manager, score, or ESPN link', () => {
  const entry = { season: 2017, champion: { team_name: 'Early winner' } };
  assert.equal(championships({ seasons: [entry] }).length, 1);
  assert.equal(managers(entry.runner_up), '');
  assert.equal(finalScores(entry), null);
  assert.equal(sourceDetails(entry).label, 'League records');
  assert.equal(sourceDetails(entry).url, undefined);
});

test('original records and optional source notes remain available in details', () => {
  const source = { type: 'league', label: 'League scrapbook', note: 'Recorded by the commissioner.' };
  assert.deepEqual(sourceDetails({ source }), source);
  assert.equal(sourceDetails({ scoreboard_url: 'https://fantasy.espn.com/final' }).label, 'ESPN');
  assert.equal(managers({ managers: ['adam d'], manager_display_names: ['Adam'] }), 'Adam');
});

test('score highlights require both final scores, with zero preserved', () => {
  assert.equal(finalScores({ final: { champion_score: 100 } }), null);
  assert.equal(finalScores({ final: { champion_score: 100, runner_up_score: null } }), null);
  assert.deepEqual(finalScores({ final: { champion_score: 0, runner_up_score: 0 } }), { champion_score: 0, runner_up_score: 0 });
});
