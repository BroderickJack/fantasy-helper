"""Import verified QRFFL champions from public ESPN season archives.

Run: python import_history.py
The generated file is bundled with the static site, so history needs no live API.
"""

import json
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LEAGUE_ID = 666462
CURRENT_SEASON = 2026
BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
OUTPUT = Path(__file__).parent / "website" / "dist" / "history.json"
LEAGUE_RECORDS = Path(__file__).parent / "league_history.json"
VIEWS = "view=mTeam&view=mSettings&view=mStandings&view=mMatchupScore"
MANAGER_DISPLAY_NAMES = {"adam d": "Adam"}  # Confirmed by the league owner.


def read_json(url, season):
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "qrffl-history/1.0"})
    with urlopen(request, timeout=25) as response:
        data = json.load(response)
    if isinstance(data, list):
        data = next((item for item in data if item.get("seasonId") == season), None)
    if not isinstance(data, dict) or data.get("seasonId") != season or data.get("id") != LEAGUE_ID:
        raise ValueError("ESPN did not return the requested league and season.")
    return data


def team_info(team, members):
    names = []
    for owner in team.get("owners", []):
        member = members.get(owner, {})
        name = " ".join(str(member.get(key, "")).strip() for key in ("firstName", "lastName")).strip()
        name = name or member.get("displayName")
        if name and name not in names:
            names.append(name)
    overall = team.get("record", {}).get("overall", {})
    return {
        "team_id": team["id"],
        "team_name": (team.get("name") or " ".join(team.get(key, "") for key in ("location", "nickname"))).strip(),
        "managers": names,
        "manager_display_names": [MANAGER_DISPLAY_NAMES.get(name, name) for name in names],
        "final_rank": team["rankCalculatedFinal"],
        "regular_season_record": {key: overall.get(key) for key in ("wins", "losses", "ties")},
    }


def extract_champion(data, source_url):
    year = data["seasonId"]
    if year >= CURRENT_SEASON:
        raise ValueError("The current season is still in progress; no champion can be assigned.")
    teams = data.get("teams", [])
    champions = [team for team in teams if team.get("rankCalculatedFinal") == 1]
    runners = [team for team in teams if team.get("rankCalculatedFinal") == 2]
    if len(champions) != 1 or len(runners) != 1:
        raise ValueError("ESPN has not supplied unique final first and second places.")
    champion, runner = champions[0], runners[0]
    bracket = [match for match in data.get("schedule", []) if match.get("playoffTierType") == "WINNERS_BRACKET"]
    if not bracket:
        raise ValueError("No championship bracket is available to confirm final standings.")
    last_period = max(match["matchupPeriodId"] for match in bracket)
    finals = [match for match in bracket if match["matchupPeriodId"] == last_period
              and {match.get("home", {}).get("teamId"), match.get("away", {}).get("teamId")} == {champion["id"], runner["id"]}]
    if len(finals) != 1:
        raise ValueError("The final-ranked teams do not have a unique championship game.")
    final = finals[0]
    winner = final.get("winner", "").lower()
    if winner not in ("home", "away") or final[winner]["teamId"] != champion["id"]:
        raise ValueError("The championship winner disagrees with final standings.")
    loser = "away" if winner == "home" else "home"
    champion_score, runner_score = final[winner].get("totalPoints"), final[loser].get("totalPoints")
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
               for value in (champion_score, runner_score)):
        raise ValueError("Championship final scores are missing.")
    if champion_score < runner_score:
        raise ValueError("The recorded winner has a lower score; commissioner review is needed.")
    members = {member["id"]: member for member in data.get("members", [])}
    return {
        "season": year, "status": "verified", "champion": team_info(champion, members),
        "runner_up": team_info(runner, members),
        "final": {"champion_score": champion_score, "runner_up_score": runner_score,
                  "matchup_id": final["id"], "matchup_period": last_period, "reported_winner": final["winner"]},
        "verification": "Final rank 1 confirmed against the last winners-bracket matchup and ESPN's declared winner.",
        "source_url": source_url,
        "standings_url": f"https://fantasy.espn.com/football/standings?leagueId={LEAGUE_ID}&seasonId={year}",
        "scoreboard_url": f"https://fantasy.espn.com/football/scoreboard?leagueId={LEAGUE_ID}&seasonId={year}&matchupPeriodId={last_period}",
    }


def import_season(year):
    urls = [f"{BASE}/seasons/{year}/segments/0/leagues/{LEAGUE_ID}?{VIEWS}",
            f"{BASE}/leagueHistory/{LEAGUE_ID}?seasonId={year}&{VIEWS}"]
    failures = []
    for url in urls:
        try:
            return extract_champion(read_json(url, year), url)
        except HTTPError as error:
            failures.append(f"HTTP {error.code}")
        except (URLError, TimeoutError, ValueError, OSError) as error:
            failures.append(str(error))
    return {"season": year, "status": "unavailable", "reason": "Listed in ESPN league history, but its archive could not be retrieved or independently verified.", "attempts": failures,
            "standings_url": f"https://fantasy.espn.com/football/standings?leagueId={LEAGUE_ID}&seasonId={year}"}


def merge_league_records(espn_records, league_records):
    """League-supplied history joins the same chronological archive; it needs no ESPN fields."""
    records = {entry["season"]: entry for entry in espn_records}
    seen = set()
    for entry in league_records:
        season = entry.get("season")
        if isinstance(season, bool) or not isinstance(season, int) or season < 1900 or season >= CURRENT_SEASON:
            raise ValueError("League records need a completed season year.")
        if season in seen:
            raise ValueError(f"Duplicate league-supplied season: {season}")
        seen.add(season)
        if not isinstance(entry.get("champion", {}).get("team_name"), str) or not entry["champion"]["team_name"].strip():
            raise ValueError(f"League records need a champion's team name for {season}.")
        final = entry.get("final")
        if final is not None:
            scores = [final.get(key) for key in ("champion_score", "runner_up_score")]
            if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in scores):
                raise ValueError(f"Supply both final scores for {season}, or leave final out.")
            if scores[0] < scores[1]:
                raise ValueError(f"The champion's final score is lower for {season}.")
        source = {"type": "league", "label": "League records", **entry.get("source", {})}
        records[season] = {**entry, "status": "recorded", "source": source}
    return [records[year] for year in sorted(records, reverse=True)]


def main():
    current_url = f"{BASE}/seasons/{CURRENT_SEASON}/segments/0/leagues/{LEAGUE_ID}?view=mSettings"
    current = read_json(current_url, CURRENT_SEASON)
    seasons = sorted({year for year in current.get("status", {}).get("previousSeasons", []) if year < CURRENT_SEASON}, reverse=True)
    if not seasons:
        raise ValueError("ESPN returned no previous seasons; existing history has been preserved.")
    with ThreadPoolExecutor(max_workers=3) as pool:
        records = list(pool.map(import_season, seasons))
    # Never replace a previously verified season with a transient fetch failure.
    if OUTPUT.exists():
        previous = {entry["season"]: entry for entry in json.loads(OUTPUT.read_text(encoding="utf-8"))["seasons"]}
        for index, entry in enumerate(records):
            old = previous.get(entry["season"])
            if entry["status"] != "verified" and old and old.get("status") == "verified":
                records[index] = old
    league_records = json.loads(LEAGUE_RECORDS.read_text(encoding="utf-8"))["seasons"] if LEAGUE_RECORDS.exists() else []
    records = merge_league_records(records, league_records)
    archive = {"league_id": LEAGUE_ID, "league_name": current.get("settings", {}).get("name", "QRFFL"),
               "current_season": CURRENT_SEASON, "checked_at": datetime.now(timezone.utc).isoformat(),
               "discovery_source_url": current_url, "seasons": records}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pending = OUTPUT.with_suffix(".json.tmp")
    pending.write_text(json.dumps(archive, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    pending.replace(OUTPUT)
    for entry in records:
        print(f"{entry['season']}: " + (f"{entry['champion']['team_name']} ({', '.join(entry['champion'].get('managers', []))})" if entry.get("champion") else "not yet recorded"))
    print(f"Saved {OUTPUT}")


if __name__ == "__main__":
    main()
