"""Build the Average's recorded results from its ownerless ESPN team seasons."""
import argparse
import json
import build_research
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from build_analytics import cents
from build_research import league_url, request
from import_history import CURRENT_SEASON, VIEWS

DIST = Path(__file__).parent / "website" / "dist"


def summarize_games(games):
    total = len(games)
    wins = sum(game["result"] == "W" for game in games)
    losses = sum(game["result"] == "L" for game in games)
    ties = total - wins - losses
    points = sum(cents(game["score"]) for game in games) / 100
    against = sum(cents(game["opponent_score"]) for game in games) / 100
    return {"games": total, "wins": wins, "losses": losses, "ties": ties,
            "points_for": points, "points_against": against,
            "ppg": points / total if total else None, "opponent_ppg": against / total if total else None,
            "win_pct": (wins + ties / 2) / total if total else None}


def extract_average_season(data):
    year = data["seasonId"]
    teams = {team["id"]: team for team in data["teams"]}
    average = teams.get(12)
    # Slot 12 was a real, player-managed team in the older archives.
    if year < 2022 or not average or average.get("owners"):
        return None
    cutoff = min(data["status"]["finalScoringPeriod"], data["scoringPeriodId"] - 1) if year == CURRENT_SEASON else data["status"]["finalScoringPeriod"]
    periods = data["settings"]["scheduleSettings"]["matchupPeriods"]
    fields = {}
    for matchup in data.get("schedule", []):
        if matchup.get("winner") not in ("HOME", "AWAY", "TIE"):
            continue
        for venue in ("home", "away"):
            side = matchup.get(venue)
            if side and side["teamId"] != 12:
                field = fields.setdefault(matchup["matchupPeriodId"], {})
                score = cents(side.get("totalPoints"))
                if side["teamId"] in field and field[side["teamId"]] != score:
                    raise ValueError("Conflicting real-team scores in Average history")
                field[side["teamId"]] = score
    games = {}
    exclusions = {"consolation": 0, "multiweek": 0, "score_not_posted": 0}
    for matchup in data.get("schedule", []):
        pair = [(venue, matchup[venue]) for venue in ("home", "away") if matchup.get(venue)]
        mine = next(((venue, side) for venue, side in pair if side["teamId"] == 12), None)
        if not mine or len(pair) != 2 or matchup.get("winner") not in ("HOME", "AWAY", "TIE"):
            continue
        weeks = periods.get(str(matchup["matchupPeriodId"]), [])
        if len(weeks) != 1:
            exclusions["multiweek"] += 1; continue
        week = weeks[0]
        if week > cutoff:
            continue
        tier = matchup.get("playoffTierType", "NONE")
        if tier not in ("NONE", "WINNERS_BRACKET"):
            exclusions["consolation"] += 1; continue
        venue, side = mine
        opponent = next(side for _, side in pair if side["teamId"] != 12)
        score = cents(side.get("totalPoints"))
        other_score = cents(opponent.get("totalPoints"))
        field = fields.get(matchup["matchupPeriodId"], {})
        mean = sum(field.values()) / len(field) / 100 if set(field) == set(teams) - {12} else None
        # A completed calendar week can still await a commissioner's Average entry.
        if score == 0 and not side.get("adjustment") and mean != 0:
            exclusions["score_not_posted"] += 1; continue
        result = "T" if matchup["winner"] == "TIE" else "W" if matchup["winner"].lower() == venue else "L"
        game = {"id": f"{year}:{matchup['id']}", "season": year, "week": week,
                "phase": "regular" if tier == "NONE" else "playoff",
                "opponent_id": opponent["teamId"], "opponent_name": teams[opponent["teamId"]].get("name") or f"Team {opponent['teamId']}",
                "score": score / 100, "opponent_score": other_score / 100,
                "margin": (score - other_score) / 100, "result": result,
                "recalculated_average": mean,
                "source_url": f"https://fantasy.espn.com/football/scoreboard?leagueId=666462&seasonId={year}&matchupPeriodId={matchup['matchupPeriodId']}"}
        if game["id"] in games and games[game["id"]] != game:
            raise ValueError("Conflicting Average matchup results")
        games[game["id"]] = game
    games = sorted(games.values(), key=lambda game: game["week"])
    official = average.get("record", {}).get("overall", {})
    expected = sum(official.get(key, 0) for key in ("wins", "losses", "ties"))
    regular = summarize_games([game for game in games if game["phase"] == "regular"])
    return {"season": year, "name": average.get("name"), "through_week": cutoff,
            "regular": regular, "playoffs": summarize_games([game for game in games if game["phase"] == "playoff"]),
            "regular_games_in_standings": expected,
            "regular_coverage_complete": regular["games"] == expected,
            "final_rank": average.get("rankCalculatedFinal") or None, "games": games, "excluded": exclusions,
            "source_url": f"https://fantasy.espn.com/football/standings?leagueId=666462&seasonId={year}"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Refresh the public ESPN season responses")
    args = parser.parse_args()
    build_research.REFRESH = args.refresh
    research = json.loads((DIST / "research.json").read_text(encoding="utf-8"))
    years = research["seasons"]
    def fetch_year(year):
        return extract_average_season(request(league_url(year) + "?" + VIEWS)["data"])
    with ThreadPoolExecutor(max_workers=3) as pool:
        seasons = [row for row in pool.map(fetch_year, years) if row and row["games"]]
    if not seasons:
        raise ValueError("No Average history found; previous archive preserved")
    seasons.sort(key=lambda row: row["season"])
    regular = [game for season in seasons for game in season["games"] if game["phase"] == "regular"]
    summary = summarize_games(regular)
    completed = [row for row in seasons if row["season"] < CURRENT_SEASON and row["regular_coverage_complete"] and row["regular"]["games"]]
    best = max(completed, key=lambda row: row["regular"]["win_pct"]) if completed else None
    output = {"current_season": CURRENT_SEASON, "checked_at": datetime.now(timezone.utc).isoformat(),
              "seasons": seasons, "regular": summary,
              "best_season": best["season"] if best else None,
              "high_score": max(regular, key=lambda game: game["score"]) if regular else None}
    path = DIST / "average-history.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(output, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)
    for row in seasons:
        r = row["regular"]; p = row["playoffs"]
        print(f"{row['season']}: regular {r['wins']}-{r['losses']}-{r['ties']} ({r['games']} games); playoffs {p['wins']}-{p['losses']}-{p['ties']}; finish {row['final_rank']}")
    print(f"Recorded regular-season total: {summary['wins']}-{summary['losses']}-{summary['ties']} across {summary['games']} games")


if __name__ == "__main__":
    main()
