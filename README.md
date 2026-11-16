# Fantasy Helper

A small, read-only ESPN Fantasy Football API prototype. Python 3.10+; no dependencies.

## Website

The [`QRFFL website`](website/README.md) now has a league home page and a
searchable champions archive, with seven confirmed championship results from
2019–2025. Each result is checked against both ESPN final standings and the
championship-game winner. The 2018 archive remains unavailable; earlier league
records are being researched.

The live dashboard at `scores.html` provides current and projected league averages,
your team's margin, sortable scores, week selection, and optional automatic
refresh every 60 seconds while the page is visible.

The `analytics.html` page mines deliberately over-specific QRFFL records from
completed historical games, with filters and every matching game listed as
evidence. Rebuild its bundled archive with `python build_analytics.py`.

The separate serious **Analytics** department at `research.html` includes
franchise trajectories, season and all-season comparisons, all-play results,
schedule swing, and recovered trade packages with actual starter production.
Rebuild its archive with `python build_research.py`. Initial trade coverage is
2025–2026; franchise performance covers 2019–2026 with current-year cutoffs shown.

```powershell
python -m http.server 8080 --directory website/dist
```

Open http://localhost:8080. The browser reads the public ESPN league directly;
no backend, database, API key, or dependency installation is needed. The portable
`website/qrffl-site.zip` contains the complete static site for direct upload to
a static host. Hosting instructions and verification limits are in the website README.

## This league

- League: **QRFFL**, ID `666462`, season `2026`.
- Your team: **Vortex Escapees**, ID `16`.
- Average placeholder: **I will consume Delly's Soul**, ID `12` (confirmed).
- Average: all **15 real teams**, including the placeholder's opponent.

```powershell
python fantasy_helper.py --league-id 666462 --season 2026 --average-team-id 12
```

The output shows each real team's current score, pregame projection, and live
projected final score, plus the corresponding league averages. ESPN supplies the
default week. Each run fetches a fresh snapshot; rerun to refresh.

```powershell
# Explore team IDs.
python fantasy_helper.py --league-id 666462 --season 2026 --list-teams

# Select a week and get machine-readable output for future tools.
python fantasy_helper.py --league-id 666462 --season 2026 --average-team-id 12 --week 10 --json

# Optional alternative: exclude the real team facing the average as well.
python fantasy_helper.py --league-id 666462 --season 2026 --average-team-id 12 --exclude-opponent

# Offline checks.
python -m unittest -v
```

## ESPN API findings

This league was successfully read without authentication. The endpoint used is:

```text
GET https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/segments/0/leagues/666462
    ?view=mTeam&view=mSettings&view=mMatchupScore&view=mScoreboard&scoringPeriodId=10
```

The tool first reads league metadata, then fetches the selected week using:

```json
{"X-Fantasy-Filter": "{\"schedule\":{\"filterMatchupPeriodIds\":{\"value\":[10]}}}"}
```

`settings.scheduleSettings.matchupPeriods` maps weeks to matchup periods. These
can differ during multiweek playoffs, which this initial prototype explicitly
rejects instead of mixing weekly and matchup totals.

For the selected matchup period, each `schedule[]` entry contains `home` and
`away` objects with:

| Field | Meaning / use |
| --- | --- |
| `teamId` | Identify and deduplicate teams; exclude ID 12. |
| `totalPointsLive` | Current score; preferred when present, including zero. |
| `totalPoints` | Score fallback when no live score is supplied. Observed as zero during active matchups, even when live points were nonzero. |
| `totalProjectedPoints` | ESPN's pregame projection for the lineup. |
| `totalProjectedPointsLive` | ESPN's live projected final total; already includes points scored. Do not add the current score again. |
| `rosterForCurrentScoringPeriod.entries` | Player and lineup data; fallback source of pregame projections if the team total is missing. |

Use ESPN's league-scored totals, so scoring settings such as half-PPR are already
accounted for. Bench (slot 20) and IR (slot 21) are excluded from the player-level
projection fallback. The fallback requires matching season/week projection stats
(`statSourceId=1`, `statSplitTypeId=1`) for every occupied starter slot.

ESPN does not supply the calculated average in the placeholder's zero score. We
calculate `sum(real team scores) / 15`, and apply the same formula to projections.
Missing team scores fail explicitly. Missing projections produce `unavailable`
(`null` in JSON), rather than a misleading average over fewer teams. Calculations
retain precision until display, where scores are rounded to two decimal places.

These are unofficial endpoints used by ESPN's fantasy application and may change.
The implementation was cross-checked against the
[espn-api request implementation](https://github.com/cwendt94/espn-api/blob/master/espn_api/requests/espn_requests.py)
and [football box score implementation](https://github.com/cwendt94/espn-api/blob/master/espn_api/football/box_score.py),
then exercised against this league. No ESPN writes are performed.

## Why including your score doesn't change whether you win

If the other 14 teams average `A` and you score `S`, the 15-team average is
`(14*A + S)/15`. Your margin against it is `14/15 * (S-A)`: the same sign as
your margin against the other 14. The numerical average and margin differ, but
the win/loss/tie outcome is the same before any league-specific rounding rules.
This also holds when comparing projected scores from the same snapshot.

## Private leagues

This league did not require cookies. For another league that returns 401/403, set
`ESPN_S2` and `ESPN_SWID` from your own logged-in ESPN browser session as local
environment variables. They are sent only as cookies to the fixed ESPN endpoint.
No password is needed; do not commit cookies or paste them into chat. The tool
reads environment variables directly and does not load `.env` files.

## Current scope

Single-week scores and projections, a terminal table, and JSON output. Live values
are snapshots and may lag ESPN's website. The reported timestamp is when the fetch
completed, not ESPN's source-update time. No UI, automatic polling, probability
model, or historical persistence in the Python tool. The website described above
provides the UI and optional refresh.
