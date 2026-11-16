const points = value => value == null ? '—' : value.toFixed(2);
const signed = value => `${value > 0 ? '+' : value < 0 ? '−' : ''}${Math.abs(value).toFixed(2)}`;
const element = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
};

export function renderMatchups(snapshot, target, { selectedTeam, stale = false } = {}) {
  const fragment = document.createDocumentFragment();
  snapshot.matchups.forEach((match, index) => {
    const card = element('article', 'matchup-card');
    card.classList.toggle('selected-matchup', [match.home?.id, match.away?.id].includes(selectedTeam));
    const header = element('div', 'matchup-card-header');
    header.append(element('h3', '', `Matchup ${index + 1}`), element('span', '', stale ? 'STALE SNAPSHOT' : !match.home || !match.away ? 'BYE' : match.status));
    card.append(header);
    for (const [key, team, opponent] of [['away', match.away, match.home], ['home', match.home, match.away]]) {
      const row = element('div', 'matchup-team');
      if (!team) { row.append(element('span', 'matchup-team-name', 'Bye')); card.append(row); continue; }
      const info = element('div', 'matchup-team-info');
      const name = element('span', 'matchup-team-name', team.name);
      if (team.isAverage) name.append(element('span', 'matchup-average-tag', match.historical ? 'AVG · RECORDED' : 'AVG'));
      if (team.id === selectedTeam) name.append(element('span', 'matchup-you-tag', 'YOU'));
      info.append(name);
      if (!match.historical) info.append(element('span', 'matchup-projected', `Projected ${points(team.live)}`));
      const leading = match.historical ? match.winner?.toLowerCase() === key
        : opponent && team.current != null && opponent.current != null && team.current - opponent.current > 1e-9;
      row.classList.toggle('matchup-leading', Boolean(leading));
      row.append(info, element('strong', 'matchup-score', points(team.current)));
      card.append(row);
    }
    if ([match.home, match.away].some(team => team?.isAverage)) card.append(element('p', 'matchup-card-note', match.historical ? 'Average score as posted for this matchup.' : `Average score calculated from all ${snapshot.teams.length} real teams.`));
    fragment.append(card);
  });
  target.replaceChildren(fragment);
}

export function renderComparison(snapshot, target, { selectedTeam, sortKey = 'current' } = {}) {
  const rows = [...snapshot.teams].sort((a, b) => {
    const key = sortKey === 'margin' ? 'current' : sortKey;
    return (b[key] ?? -Infinity) - (a[key] ?? -Infinity) || a.name.localeCompare(b.name);
  });
  const scale = Math.max(1, ...snapshot.teams.flatMap(team => [team.current, team.live ?? 0]), snapshot.current) * 1.08;
  const fragment = document.createDocumentFragment();
  for (const team of rows) {
    const row = document.createElement('tr');
    row.classList.toggle('selected', team.id === selectedTeam);
    const rank = 1 + snapshot.teams.filter(other => other.current > team.current).length;
    row.append(element('td', 'rank', String(rank).padStart(2, '0')));
    const name = element('td', 'team-name', team.name);
    if (team.id === selectedTeam) name.append(element('span', '', 'YOU'));
    if (team.id === snapshot.averageOpponent) name.append(element('span', 'average-opponent', 'VS AVG'));
    row.append(name, element('td', 'number scored', points(team.current)), element('td', 'number projected-score', points(team.live)));
    const delta = team.current - snapshot.current;
    row.append(element('td', `number delta ${delta > 0 ? 'positive' : delta < 0 ? 'negative' : ''}`, signed(delta)));
    const trackCell = element('td', 'track-col');
    const track = element('div', 'score-track'); track.setAttribute('aria-hidden', 'true');
    track.title = `Scored ${points(team.current)} · projected ${points(team.live)} · calculated average ${points(snapshot.current)}`;
    for (const [className, value] of [['forecast', team.live], ['actual', team.current], ['average-marker', snapshot.current]]) {
      if (value == null) continue;
      const bar = element('span', className);
      bar.style[className === 'average-marker' ? 'left' : 'width'] = `${Math.max(0, value / scale * 100)}%`;
      track.append(bar);
    }
    trackCell.append(track); row.append(trackCell); fragment.append(row);
  }
  target.replaceChildren(fragment);
}

export function showScoreboardUnavailable(matchups, comparison, message) {
  matchups.replaceChildren(element('p', 'matchups-empty', message));
  const row = document.createElement('tr'); const cell = element('td', 'loading-cell', message); cell.colSpan = 6; row.append(cell); comparison.replaceChildren(row);
}

export function bindComparisonSort(scope, handler) {
  const buttons = [...scope.querySelectorAll('[data-sort]')];
  for (const button of buttons) button.addEventListener('click', () => {
    for (const other of buttons) {
      other.setAttribute('aria-pressed', String(other === button));
      other.textContent = ({ current: 'SCORED', live: 'PROJECTED', margin: 'VS AVG' })[other.dataset.sort] + (other === button ? ' ↓' : '');
    }
    handler(button.dataset.sort);
  });
}
