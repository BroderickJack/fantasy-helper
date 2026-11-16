// League history uses the same presentation regardless of where a season was recorded.
export function championships(archive) {
  return archive.seasons.filter(entry => entry.champion?.team_name && entry.status !== 'unavailable')
    .sort((a, b) => b.season - a.season);
}

export function managers(team) {
  return (team?.manager_display_names ?? team?.managers ?? []).join(' & ');
}

export function finalScores(entry) {
  const final = entry.final;
  return final && Number.isFinite(final.champion_score) && Number.isFinite(final.runner_up_score) ? final : null;
}

export function sourceDetails(entry) {
  if (entry.source) return entry.source;
  const url = entry.scoreboard_url || entry.standings_url;
  return { label: url ? 'ESPN' : 'League records', url, note: '' };
}
