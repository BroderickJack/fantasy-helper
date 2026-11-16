# QRFFL · League home

A static website with no dependencies, build step, backend, database, or API keys.
It fetches the public ESPN league directly from each visitor's browser. CORS
support was verified against ESPN. An internet connection and continued public
league access are required.

The home page features the latest champion, followed by current-week matchup
cards and a sortable team-versus-average list at the bottom. Live scores uses
the same order, with a week picker and selected-team details. Both sections share
one ESPN snapshot and refresh every 60 seconds while visible. The
searchable champions archive has its own page at `champions.html`, and the full
live dashboard is at `scores.html`. Deliberately over-specific historical records
have their own `analytics.html` page. All pages remain plain static files with no
build or dependency installation.

## Releases

The current release is **v1.0.0**, shown in every page footer. The version in
`package.json` is the source for the footer labels and the portable ZIP.
`website/dist` contains the website source and bundled archives and is tracked
in Git so each release tag preserves the complete site.

From the repository root, prepare the next release:

```powershell
python prepare_release.py 1.0.1
# Update CHANGELOG.md, then run the applicable checks.
git add website/package.json website/dist CHANGELOG.md
git commit -m "Release v1.0.1"
git tag -a v1.0.1 -m "QRFFL v1.0.1"
```

Use patch versions for fixes, minor versions for new features, and major versions
for incompatible changes. Tags remain local until pushed. To share a release,
push its commit and tag: `git push --atomic origin main v1.0.1`.
Run `python prepare_release.py` without a version to rebuild the ZIP for the
current release. The generated `qrffl-site.zip` stays outside Git; it can be
uploaded as a release artifact or deployed on a static host.

## Analytics: franchise research and trade impact

The serious **Analytics** department is at `research.html`, alongside the separate
Q-alytics page. It includes:

- Franchise season histories, managers, regular-season records, scoring, and finishes.
- A scoring-index trajectory chart with optional franchise comparisons.
- Season/all-season leaderboards, recorded titles, all-play results, and schedule swing.
- Computed findings for the selected data and recorded head-to-head results.
- A trade lab with received/sent players, receiving managers, recorded starter points,
  player production, pre/post regular-season context, and weekly receipts.

The bundled `research.json` initially covers 119 franchise-season rows from
2019–2026, with 2026 measured through completed Week 9. The trade study recovered
13 executed deals in 2025 and 8 in 2026. Eighteen have a full post-trade week and
complete starter comparisons; three are too recent for that window. The page
shows its actual cutoffs and counts from the archive rather than assuming a
trade is fully measured. Head-to-head coverage uses the 2019–2025 game archive.

Rebuild from the repository root:

```powershell
python build_research.py
# Force fresh ESPN requests rather than the one-day local response cache.
python build_research.py --refresh
# Expand trade discovery to other available ESPN seasons.
python build_research.py --trade-seasons 2024 2025 2026
```

The builder scans every player in ESPN's season pool, including free agents, so
discovery is not limited to current rosters. It deduplicates executed player-card
trade receipts, fetches actual weekly production and historical lineups, and
uses NFL bye schedules to distinguish known zeroes from missing data. Raw API
responses are cached in ignored `.research-cache/`; only the derived archive
is shipped with the site. No cookies, API keys, runtime server, or paid service
is required. A failed import preserves the previous published JSON file.

Starter credit begins the week after the deal, counts only recorded starting
slots in scored matchups, and stops before the first exit week or at the first
roster absence. It never restarts after reacquisition. Player output is a
separate total that continues after roster exits. This is a first-stint player
comparison, not a full trade-chain valuation or a counterfactual estimate of
wins caused. Associated drops, replacement players, and future flips are not
credited to the original package. Recent deals have no measured edge yet.

Performance comparisons include the real team facing the placeholder in the
weekly scoring field, unlike a head-to-head-only archive. Recorded results
include scheduled average-team games; all-play comparisons exclude the placeholder
from 2022 onward. Ties count as half a win. Scoring index is weekly points divided
by the real-team mean times 100. Expected wins sum all-play win fractions; schedule
swing is recorded win equivalents minus expected wins. Neither schedule swing nor
pre/post trade splits establish causality. Franchise slots can span owner changes;
each season's managers and team names are shown instead of silently treating all
slot history as one person's performance.

Tests cover these formulas and boundaries, including missing weekly fields,
weighted all-season metrics, historical roster exits, NFL and fantasy byes,
bench/IR treatment, and reconciliation of every generated trade total to its
week-by-week receipts.

## Laegue Average: current matchup and history

`average.html` keeps the club crest and a restrained identity, with a live matchup,
season-by-season results, regular-season scoring comparisons, and a filterable game
log. Chants, the cheer counter, and exaggerated commentary have been removed from
the interface. The homepage invitation links to the results above the weekly
matchups and the team-versus-average list.

The live matchup still uses the shared all-15-team ESPN average and scheduled
opponent. It refreshes every 60 seconds while visible and marks retained snapshots
stale after failures. Historical performance loads independently from bundled
`average-history.json`, so it can display when the live API is unavailable.

Rebuild the recorded history from the repository root:

```powershell
python build_average_history.py
python build_average_history.py --refresh
```

History covers the ownerless Average seasons from 2022 onward. Slot #12 had real
managers in the older 2019–2021 archives; their results are not attributed to the
Average. Historical results use ESPN's posted scores and declared outcomes, rather
than applying today's recalculated mean to change old results. Regular-season and
championship-bracket records are separate, and consolation games are excluded from
those records. ESPN's final placing can include consolation results. The active
current week is excluded, and unposted placeholder zeroes are not counted as losses.
Each game links to the original ESPN scoreboard. Record highlights use completed
seasons for best regular-season record and final finish; current-year figures are
clearly marked YTD with their measured cutoff.

The importer reuses the ignored local public-response cache. A failed import leaves
the existing JSON untouched. Tests cover recorded-versus-recomputed results, source
identity, active-week cutoffs, actual zeroes and ties, unposted scores, phase
separation, duplicate games, and reconciliation of the bundled record to its games.

## Q-alytics: statistical notes

Q-alytics presents unusually specific QRFFL records in the tone of broadcast
research notes. The humor comes from the detailed conditions themselves. The
page shows each record with its sample size, overall context, and matching game
log. Featured notes, category filters, and copied stats use the same factual
presentation. The `analytics.html` URL and Q-alytics navigation label are retained.
There is no additional service or API dependency.

`analytics.html` offers team, category, and specificity filters, a random deep-cut
button, copying a featured stat, and expandable game logs for every selected claim.
It reads bundled `analytics.json`, so there are no runtime API calls or hosting
functions on this page. Refresh its source data from the repository root with:

```powershell
python build_analytics.py
python -m unittest -v
```

The builder mines combinations of week-number properties, season parity,
home/away labels, whole-score and decimal-digit properties, previous-week
results, and opponents. It selects one-sided W–L–T records with at least five
matching games across at least two seasons. These are intentionally selected
coincidences; no predictive or causal significance is claimed. All matching
games are stored with the condition IDs, baseline team record, and source data,
and the tests recompute every published claim from its actual conditions.

Coverage is completed 2019–2025 regular-season and championship-bracket matchups.
Consolation games, byes, ownerless placeholder #12 from 2022 onward, unfinished
games, and multiweek games are excluded. Team #12 was a real team in 2019–2021
and is included for those seasons. Team-slot identities can span ownership and
name changes; each evidence row retains the season's team names. Previous-game
conditions require the immediately prior included week of the same season.
Scores use integer hundredths, preventing floating-point errors in digit rules.

The existing 2018 archive gap and in-progress 2026 season are not used for these
records. The generated archive records included seasons, source URLs, exclusions,
and when it was checked. New imports fail on inconsistent final scores or unknown
team-12 ownership instead of silently changing scope.

## Championship history

`dist/history.json` contains seven championship records (2019–2025), with team
names, managers, runners-up, final scores, and links to each season's ESPN source.
The 2018 season is listed by ESPN, but its archive returned 401/404 and remains
unverified. Earlier records are being researched by the league owner. No champion
is assigned to the in-progress 2026 season, and no founding date is inferred.

To refresh the ESPN archive, from the repository root:

```powershell
python import_history.py
python -m unittest -v
```

The importer discovers past seasons from ESPN's current league metadata. A
champion requires unique final ranks 1 and 2, a matchup between those teams in the
last winners-bracket round, a declared winner matching final rank 1, and numeric
final scores. A regular-season seed alone is never treated as a championship.
Previously verified records are retained if a later import temporarily fails.
The original ESPN manager name `adam d` is preserved in the data, with the
league-owner-approved display name `Adam`. Team names remain season-specific.

History is bundled locally; it still loads when live ESPN scores are unavailable.
Any record highlights refer only to the verified 2019–2025 championship finals.

### Adding the early years

Add league-supplied seasons to the repository's `league_history.json`, then run
`python import_history.py`. They merge into the same chronological archive and
the same homepage/champions presentation. The importer preserves these records
on future ESPN refreshes. A league-supplied season can also fill an existing gap
or replace an ESPN season when the commissioner provides a correction.

Each supplied season needs `season` and `champion.team_name`. Optional fields
are `champion.managers` (a list), `runner_up` (the same team shape), `final`
with both `champion_score` and `runner_up_score`, and `source` with `label`,
`note`, and an optional web `url`. Missing details display as dashes and do not
prevent a champion from appearing. Score highlights use only finals with scores.
Source notes live in each row's expandable Details; the site uses no verification
labels or ESPN-specific eligibility rule for displaying championship history.

Analytics still requires underlying matchups; adding an older champion alone
does not invent older game-level statistics.

## Run locally

From this directory:

```powershell
python -m http.server 8080 --directory dist
```

Open http://localhost:8080. Use an HTTP server rather than opening the HTML file
directly, because browser JavaScript modules require an origin. Run calculation
checks with `node --test tests/*.test.mjs` (Node 22+).

## Hosting

The complete website is the contents of `dist/`. Serve those files unchanged on
any static host. No install or build command is required. The `.openai/hosting.json`
file binds the Sites deployment; it isn't needed by other hosts.

Cloudflare Pages also offers free static asset requests:
https://developers.cloudflare.com/pages/functions/pricing/
Use the free provider subdomain to avoid buying a domain. Sites billing and
availability depend on your ChatGPT workspace; this project adds no paid external
services. Nothing runs when the page is closed.

### Easiest free hosting: Cloudflare Pages direct upload

The ready-to-upload `qrffl-site.zip` contains the static assets with `index.html`
at the archive root. In a free Cloudflare account:

1. Open **Workers & Pages**, then **Create application**.
2. Choose the Pages **Drag and drop your files** option (under **Get started**).
3. Name the project, upload `qrffl-site.zip`, and choose **Deploy site**.
4. Cloudflare supplies a `pages.dev` address. No custom domain purchase is needed.

Official instructions: https://developers.cloudflare.com/pages/get-started/direct-upload/

Direct Upload updates are manual. For automatic updates on Git pushes, create a
Git-integrated Pages project instead, with `website/dist` as the output directory
and no build command. A Direct Upload project cannot be converted to Git integration.

### Verification and deployment status

Offline website tests cover averages, scheduled pairings, byes, duplicate games,
missing projections, and posted historical Average scores. Current-week matchup
cards calculate the Average from all 15 real teams. Past-week cards retain its
posted score and recorded outcome; the comparison list uses the calculated mean.
The website's current, projected,
and pregame averages were also compared against the Python prototype using the
exact same live ESPN payload and matched. JavaScript syntax was checked.

Browser visual verification could not complete: the installed headless Chrome
exited before loading the page. A Sites project was registered, but no version
was published: Windows could not start the interactive terminal required to pass
the short-lived publishing credential securely. Reuse the existing project ID in
`.openai/hosting.json` when resuming; do not register another Site for this project.

The history importer has seven additional tests for final-rank versus seed
selection, championship-round verification, missing scores, current-season
rejection, and the approved manager display name. The generated archive and
all home-page asset links are checked when packaging.

## Behavior

- Current, live projected final, and pregame average over all 15 real teams.
- Placeholder team #12 excluded; Vortex Escapees (#16) selected by default.
- Team selection saved locally on the device; week selection stays in memory.
- Switch weeks, sort scores, refresh manually, or refresh every 60 seconds while visible.
- Missing scores reject the snapshot. Missing projections stay unavailable.
- Fetch errors leave the previous snapshot visible and explicitly marked stale.
- Scores are snapshots; the timestamp is fetch time, not ESPN's update time.
- Multiweek matchups are explicitly unsupported rather than using an incorrect average.
- The JavaScript data module mirrors the Python prototype's averaging rules.
- No cookies, accounts, tracking scripts, remote fonts, or third-party dependencies.

Private Sites publication is intended for the owner. Sharing with league members
requires an explicit access change or deploying `dist/` to a public static host.
