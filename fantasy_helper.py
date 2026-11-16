"""Read ESPN Fantasy Football scores and calculate a weekly league average."""

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"


def fetch_league(league_id, season, week=None, matchup_period=None):
    params = [("view", v) for v in
              ("mTeam", "mSettings", "mMatchupScore", "mScoreboard")]
    if week is not None:
        params.append(("scoringPeriodId", week))
    headers = {"Accept": "application/json", "User-Agent": "fantasy-helper/0.1"}
    if matchup_period is not None:
        headers["X-Fantasy-Filter"] = json.dumps({
            "schedule": {"filterMatchupPeriodIds": {"value": [matchup_period]}}
        })
    cookies = {"espn_s2": os.getenv("ESPN_S2"), "SWID": os.getenv("ESPN_SWID")}
    if any(cookies.values()):
        if not all(cookies.values()):
            raise ValueError("Private leagues need both ESPN_S2 and ESPN_SWID environment variables.")
        if any(c in value for value in cookies.values() for c in "\r\n;"):
            raise ValueError("Invalid ESPN cookie value.")
        headers["Cookie"] = "; ".join(f"{key}={value}" for key, value in cookies.items())
    url = f"{BASE_URL}/seasons/{season}/segments/0/leagues/{league_id}?{urlencode(params)}"
    try:
        with urlopen(Request(url, headers=headers), timeout=30) as response:
            data = json.load(response)
    except HTTPError as error:
        if error.code in (401, 403):
            raise ValueError("ESPN denied access. Check league ID/season; private leagues need ESPN_S2 and ESPN_SWID.") from None
        raise ValueError(f"ESPN returned HTTP {error.code}.") from None
    except (URLError, TimeoutError, OSError):
        raise ValueError("Could not reach ESPN. Check your connection and try again.") from None
    except (ValueError, UnicodeError):
        raise ValueError("ESPN returned an unexpected response instead of league JSON.") from None
    if not isinstance(data, dict) or "teams" not in data:
        raise ValueError("ESPN response is missing league teams.")
    return data


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def team_name(team):
    return team.get("name") or " ".join(
        str(team.get(k, "")) for k in ("location", "nickname")
    ).strip() or f"Team {team['id']}"


def resolve_period(data, week):
    periods = data.get("settings", {}).get("scheduleSettings", {}).get("matchupPeriods", {})
    matches = [(int(period), weeks) for period, weeks in periods.items() if week in weeks]
    if len(matches) != 1:
        raise ValueError(f"Cannot map week {week} to an ESPN matchup period.")
    period, weeks = matches[0]
    if len(weeks) != 1:
        raise ValueError("This prototype supports single-week matchups only; multiweek playoff totals need separate handling.")
    return period


def starter_projection(side, week, season):
    """Pregame projection only. Never substitute this for a live projection."""
    if number(side.get("totalProjectedPoints")):
        return side["totalProjectedPoints"]
    entries = side.get("rosterForCurrentScoringPeriod", {}).get("entries")
    if not entries:
        return None
    values = []
    for entry in entries:
        slot = entry.get("lineupSlotId")
        if slot in (20, 21):  # Bench and injured reserve.
            continue
        if slot is None:
            return None
        stats = entry.get("playerPoolEntry", {}).get("player", {}).get("stats", [])
        projections = [stat.get("appliedTotal") for stat in stats
                       if stat.get("statSourceId") == 1
                       and stat.get("statSplitTypeId") == 1
                       and stat.get("scoringPeriodId") == week
                       and stat.get("seasonId") == season]
        if len(projections) != 1 or not number(projections[0]):
            return None
        values.append(projections[0])
    return math.fsum(values)


def summarize(data, week, season, average_team_id, expected_teams=15, exclude_opponent=False):
    period = resolve_period(data, week)
    teams = {team["id"]: team for team in data["teams"]}
    if average_team_id not in teams:
        raise ValueError(f"Average team ID {average_team_id} is not in the league. Use --list-teams.")
    sides = {}
    opponents = set()
    for matchup in data.get("schedule", []):
        if matchup.get("matchupPeriodId") != period:
            continue
        pair = [matchup[key] for key in ("home", "away") if matchup.get(key)]
        ids = {side["teamId"] for side in pair}
        if average_team_id in ids:
            opponents.update(ids - {average_team_id})
        for side in pair:
            team_id = side["teamId"]
            if team_id in sides and sides[team_id] != side:
                raise ValueError(f"Conflicting score entries for team {team_id}.")
            sides[team_id] = side
    real_ids = set(teams) - {average_team_id}
    if len(real_ids) != expected_teams:
        raise ValueError(f"Expected {expected_teams} real teams; found {len(real_ids)} after excluding the average team.")
    if exclude_opponent:
        if len(opponents) != 1:
            raise ValueError("Could not identify exactly one opponent of the average team.")
        real_ids -= opponents
    if not real_ids:
        raise ValueError("No teams remain in the average.")
    rows = []
    for team_id in sorted(real_ids):
        side = sides.get(team_id)
        if side is None:
            raise ValueError(f"Missing week {week} score for team {team_id}; refusing a partial average.")
        current = side.get("totalPointsLive")
        if not number(current):
            current = side.get("totalPoints")
        if not number(current):
            raise ValueError(f"Missing numeric score for team {team_id}.")
        # Match the ESPN client's live-field guard; missing projections stay unknown.
        live = side.get("totalProjectedPointsLive") if number(side.get("totalPointsLive")) else None
        rows.append({"team_id": team_id, "name": team_name(teams[team_id]),
                     "current": current,
                     "pregame_projected": starter_projection(side, week, season),
                     "live_projected": live if number(live) else None})

    def average(key):
        values = [row[key] for row in rows]
        return math.fsum(values) / len(values) if all(number(v) for v in values) else None

    return {"league_id": data.get("id"), "season": season, "week": week,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "average_team_id": average_team_id,
            "exclude_opponent": exclude_opponent, "teams_counted": len(rows),
            "current_average": average("current"),
            "pregame_projected_average": average("pregame_projected"),
            "live_projected_average": average("live_projected"), "teams": rows}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league-id", type=int, required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, help="Default: ESPN's current scoring period")
    parser.add_argument("--list-teams", action="store_true")
    parser.add_argument("--average-team-id", type=int)
    parser.add_argument("--expected-teams", type=int, default=15, help="Real teams before optional opponent exclusion")
    parser.add_argument("--exclude-opponent", action="store_true", help="Average 14 teams by excluding the placeholder's opponent too")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not args.list_teams and args.average_team_id is None:
        parser.error("--average-team-id is required unless using --list-teams")
    if args.week is not None and args.week < 1:
        parser.error("--week must be positive")
    try:
        data = fetch_league(args.league_id, args.season)
        if args.list_teams:
            for team in sorted(data["teams"], key=lambda t: t["id"]):
                print(f"{team['id']:>3}  {team_name(team)}")
            return 0
        week = args.week if args.week is not None else data.get("scoringPeriodId")
        if not isinstance(week, int) or week < 1:
            raise ValueError("No active scoring period. Supply --week explicitly.")
        period = resolve_period(data, week)
        data = fetch_league(args.league_id, args.season, week, period)
        result = summarize(data, week, args.season, args.average_team_id,
                           args.expected_teams, args.exclude_opponent)
        if args.json:
            print(json.dumps(result, indent=2, allow_nan=False))
        else:
            def fmt(value):
                return "unavailable" if value is None else f"{value:.2f}"
            print(f"Season {args.season} / Week {week} / {result['teams_counted']} real teams counted")
            print(f"Current average:          {fmt(result['current_average'])}")
            print(f"Pregame projected average: {fmt(result['pregame_projected_average'])}")
            print(f"Live projected average:   {fmt(result['live_projected_average'])}")
            print("\n ID  Team                              Current   Pregame      Live")
            for row in result["teams"]:
                print(f"{row['team_id']:>3}  {row['name'][:32]:32} {fmt(row['current']):>9} {fmt(row['pregame_projected']):>9} {fmt(row['live_projected']):>9}")
            print(f"\nFetched at {result['fetched_at']}")
        return 0
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
