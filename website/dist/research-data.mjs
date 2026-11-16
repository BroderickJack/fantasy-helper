export function combineSeasons(rows) {
  if (!rows.length) return null;
  const sum = key => rows.reduce((total, row) => total + row[key], 0);
  const games = sum('games');
  const complete = key => rows.every(row => Number.isFinite(row[key]));
  return { team_id: rows[0].team_id, seasons: rows.length, games,
    wins: sum('wins'), losses: sum('losses'), ties: sum('ties'),
    ppg: sum('points_for') / games,
    win_pct: (sum('wins') + sum('ties') / 2) / games,
    all_play_pct: complete('all_play_wins') && complete('all_play_comparisons') ? sum('all_play_wins') / sum('all_play_comparisons') : null,
    expected_wins: complete('expected_wins') ? sum('expected_wins') : null,
    schedule_swing: complete('schedule_swing') ? sum('schedule_swing') : null,
    scoring_index: complete('scoring_index') ? rows.reduce((total, row) => total + row.scoring_index * row.games, 0) / games : null,
  };
}

export function headToHead(rows, teamId, opponentId) {
  const games = rows.filter(row => row.team_id === teamId && row.opponent_id === opponentId);
  return { games: games.length, wins: games.filter(row => row.result === 'W').length,
    losses: games.filter(row => row.result === 'L').length, ties: games.filter(row => row.result === 'T').length };
}
