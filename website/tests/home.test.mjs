import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const archive = JSON.parse(await readFile(new URL('../dist/history.json', import.meta.url), 'utf8'));

// Only the DOM operations used by the homepage; requests and timers stay controlled.
class Element {
  constructor() {
    this.children = []; this.attributes = {}; this.listeners = {}; this.style = {};
    this.dataset = {}; this.hidden = true; this.checked = true;
    this.classList = { toggle() {} };
  }
  set textContent(value) { this.text = String(value); this.children = []; }
  get textContent() { return (this.text ?? '') + this.children.map(child => child.textContent).join(''); }
  append(...nodes) { this.children.push(...nodes.flatMap(node => node.fragment ? node.children : [node])); }
  replaceChildren(...nodes) { this.children = []; this.text = ''; this.append(...nodes); }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(key, handler) { this.listeners[key] = handler; }
  querySelectorAll() { return this.sortButtons ?? []; }
}

function league() {
  const side = id => ({ teamId: id, totalPoints: 0, totalPointsLive: id * 10, totalProjectedPointsLive: 120 + id });
  return { teams: Array.from({ length: 16 }, (_, index) => ({ id: index + 1, name: `Team ${index + 1}` })),
    scoringPeriodId: 10, settings: { scheduleSettings: { matchupPeriods: { 10: [10] } } },
    schedule: Array.from({ length: 8 }, (_, index) => ({ id: index + 1, matchupPeriodId: 10, home: side(index * 2 + 1), away: side(index * 2 + 2) })) };
}

async function homepage(t, { scores = async () => league(), history } = {}) {
  const html = await readFile(new URL('../dist/index.html', import.meta.url), 'utf8');
  const nodes = new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(([, id]) => [id, new Element()]));
  const $ = id => nodes.get(id);
  $('home-comparison').sortButtons = ['current', 'live', 'margin'].map(key => {
    const button = new Element(); button.dataset.sort = key; return button;
  });
  const timers = new Map(), requests = [];
  let nextTimer = 0;
  const original = new Map(['document', 'fetch', 'localStorage', 'setTimeout', 'clearTimeout', 'setInterval'].map(key => [key, globalThis[key]]));
  t.after(() => { for (const [key, value] of original) { if (value === undefined) delete globalThis[key]; else globalThis[key] = value; } });
  globalThis.document = { getElementById: $, hidden: false, addEventListener() {},
    createElement: () => new Element(), createDocumentFragment: () => Object.assign(new Element(), { fragment: true }) };
  globalThis.localStorage = { getItem: () => null };
  globalThis.setTimeout = (callback, delay) => { const id = ++nextTimer; timers.set(id, { callback, delay }); return id; };
  globalThis.clearTimeout = id => timers.delete(id);
  globalThis.setInterval = () => 0;
  globalThis.fetch = async (url, options) => {
    requests.push(String(url));
    if (String(url) === 'history.json') {
      if (history) return history(options);
      return { ok: true, json: async () => archive };
    }
    const data = await scores(options);
    return { ok: true, json: async () => data };
  };
  await import(`../dist/home.mjs?test=${encodeURIComponent(t.name)}`);
  // Let the page's independent async jobs finish.
  for (let i = 0; i < 5; i++) await new Promise(resolve => setImmediate(resolve));
  return { $, timers, requests, flush: async () => { for (let i = 0; i < 5; i++) await new Promise(resolve => setImmediate(resolve)); } };
}

test('homepage renders champion, eight matchups, and 15 comparisons with one ESPN request', async t => {
  const { $, requests } = await homepage(t);
  assert.equal(requests.filter(url => url.startsWith('https://')).length, 1);
  assert.equal($('home-matchups').children.length, 8);
  assert.equal($('home-teams').children.length, 15);
  assert.equal($('home-current').textContent, '82.67');
  assert.equal($('home-average-score').textContent, '82.67');
  assert.equal($('home-average-projected').textContent, '128.27');
  assert.equal($('home-average-opponent').textContent, 'Team 11');
  assert.equal($('home-average-opponent-score').textContent, '110.00');
  assert.equal($('home-average-opponent-projected').textContent, '131.00');
  assert.equal($('home-average-title').textContent, 'Laegue Average vs. Team 11');
  assert.equal($('home-average-state').textContent, 'TRAILING');
  assert.match($('home-average-note').textContent, /trails by 27.33/);
  assert.equal($('home-average-scoreboard').attributes['aria-busy'], 'false');
  assert.equal($('home-matchups').attributes['aria-busy'], 'false');
  assert.equal($('home-refresh').disabled, false);
  assert.equal($('home-scores-error').hidden, true);
  assert.match($('home-live-status').textContent, /Fetched from ESPN/);
  assert.equal($('defending-card').attributes['aria-busy'], 'false');
  assert.match($('champion-season').textContent, /2025 QRFFL CHAMPION/);
});

test('ESPN failure exits loading and leaves a usable retry button', async t => {
  const { $ } = await homepage(t, { scores: async () => { throw new TypeError('Network failed'); } });
  assert.equal($('home-scores-error').hidden, false);
  assert.match($('home-matchups').textContent, /could not be loaded/);
  assert.match($('home-teams').textContent, /could not be loaded/);
  assert.equal($('home-comparison').attributes['aria-busy'], 'false');
  assert.equal($('home-refresh').disabled, false);
  assert.equal($('home-average-state').textContent, 'UNAVAILABLE');
  assert.equal($('home-average-scoreboard').attributes['aria-busy'], 'false');
});

test('a stalled ESPN request times out and clears both loading sections', async t => {
  const { $, timers, flush } = await homepage(t, { scores: ({ signal }) => new Promise((resolve, reject) => {
    signal.addEventListener('abort', () => reject(signal.reason), { once: true });
  }) });
  assert.equal($('home-refresh').disabled, true);
  const deadline = [...timers.values()].find(timer => timer.delay === 12000);
  assert.ok(deadline, 'Live data must have a bounded wait.');
  deadline.callback();
  await flush();
  assert.match($('home-scores-error').textContent, /too long/);
  assert.equal($('home-matchups').attributes['aria-busy'], 'false');
  assert.equal($('home-comparison').attributes['aria-busy'], 'false');
  assert.equal($('home-average-scoreboard').attributes['aria-busy'], 'false');
  assert.equal($('home-refresh').disabled, false);
});

test('failed refresh preserves the last complete scoreboard and labels it stale', async t => {
  let fail = false;
  const { $ } = await homepage(t, { scores: async () => {
    if (fail) throw new TypeError('Offline');
    return league();
  } });
  fail = true;
  await $('home-refresh').listeners.click();
  assert.equal($('home-matchups').children.length, 8);
  assert.equal($('home-teams').children.length, 15);
  assert.match($('home-matchups').textContent, /STALE SNAPSHOT/);
  assert.match($('home-live-status').textContent, /Last successful fetch/);
  assert.equal($('home-average-state').textContent, 'STALE SNAPSHOT');
  assert.equal($('home-average-score').textContent, '82.67');
  assert.equal($('home-average-opponent-score').textContent, '110.00');
  assert.equal($('home-refresh').disabled, false);
});

test('a stalled championship archive does not hold up the scoreboard or module startup', async t => {
  const { $ } = await homepage(t, { history: () => new Promise(() => {}) });
  assert.equal($('home-matchups').children.length, 8);
  assert.equal($('home-teams').children.length, 15);
  assert.equal($('home-refresh').disabled, false);
});
