"""Mine reproducible, deliberately over-specific QRFFL records from ESPN archives."""

import itertools
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from import_history import BASE, CURRENT_SEASON, LEAGUE_ID, VIEWS, read_json

DIST = Path(__file__).parent / "website" / "dist"
MIN_SAMPLE = 5
MAX_SAMPLE = 30
PLACEHOLDER_SEASONS = set(range(2022, CURRENT_SEASON + 1))


def cents(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Missing numeric final score")
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("Nonfinite final score")
    return int((number * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def name_of(team):
    return (team.get("name") or " ".join(team.get(key, "") for key in ("location", "nickname"))).strip()


def extract_games(data):
    """One observation per real team, per completed competitive matchup."""
    season = data["seasonId"]
    if season >= CURRENT_SEASON:
        raise ValueError("Use completed past seasons only.")
    teams = {team["id"]: team for team in data["teams"]}
    periods = data["settings"]["scheduleSettings"]["matchupPeriods"]
    result = {}
    skipped = defaultdict(int)
    for game in data.get("schedule", []):
        tier = game.get("playoffTierType", "NONE")
        if tier not in ("NONE", "WINNERS_BRACKET"):
            skipped["consolation"] += 1
            continue
        if game.get("winner") not in ("HOME", "AWAY", "TIE"):
            skipped["unfinished"] += 1
            continue
        home, away = game.get("home"), game.get("away")
        if not home or not away or home.get("teamId") not in teams or away.get("teamId") not in teams:
            skipped["bye_or_missing_team"] += 1
            continue
        if season in PLACEHOLDER_SEASONS and 12 in (home["teamId"], away["teamId"]):
            if teams[12].get("owners"):
                raise ValueError(f"Team #12 in {season} has owners; review the placeholder rule.")
            skipped["placeholder"] += 1
            continue
        weeks = periods.get(str(game["matchupPeriodId"]), [])
        if len(weeks) != 1:
            skipped["multiweek"] += 1
            continue
        # Bad completed scores fail the import, rather than silently changing records.
        home_score, away_score = cents(home.get("totalPoints")), cents(away.get("totalPoints"))
        if ((game["winner"] == "HOME" and home_score < away_score)
                or (game["winner"] == "AWAY" and away_score < home_score)
                or (game["winner"] == "TIE" and home_score != away_score)):
            raise ValueError(f"Final winner and scores disagree: {season}, matchup {game['id']}")
        for side, opponent, score, opponent_score, venue in (
                (home, away, home_score, away_score, "HOME"),
                (away, home, away_score, home_score, "AWAY")):
            row = {"id": f"{season}:{game['id']}:{side['teamId']}", "season": season,
                   "week": weeks[0], "matchup_period": game["matchupPeriodId"],
                   "matchup_id": game["id"], "team_id": side["teamId"],
                   "team_name": name_of(teams[side["teamId"]]), "opponent_id": opponent["teamId"],
                   "opponent_name": name_of(teams[opponent["teamId"]]), "score": score,
                   "opponent_score": opponent_score, "venue": venue,
                   "phase": "regular" if tier == "NONE" else "playoff",
                   "result": "T" if game["winner"] == "TIE" else "W" if game["winner"] == venue else "L"}
            if row["id"] in result and result[row["id"]] != row:
                raise ValueError("Conflicting duplicate matchup")
            result[row["id"]] = row
    return list(result.values()), dict(skipped)


def add_previous_games(rows):
    lookup = {}
    for row in rows:
        key = (row["season"], row["team_id"], row["week"])
        if key in lookup:
            raise ValueError("Multiple games for one team in one week require explicit handling.")
        lookup[key] = row
    for row in rows:
        previous = lookup.get((row["season"], row["team_id"], row["week"] - 1))
        row["previous_id"] = previous["id"] if previous else None
        row["previous_result"] = previous["result"] if previous else None
        row["previous_margin"] = previous["score"] - previous["opponent_score"] if previous else None


def is_prime(value):
    return value >= 2 and all(value % divisor for divisor in range(2, int(value ** .5) + 1))


def conditions(labels):
    # Different families prevent redundant combinations such as odd AND prime weeks.
    values = [
        ("odd-week", "week", "in odd-numbered weeks", lambda r: r["week"] % 2 == 1),
        ("even-week", "week", "in even-numbered weeks", lambda r: r["week"] % 2 == 0),
        ("prime-week", "week", "in prime-numbered weeks", lambda r: is_prime(r["week"])),
        ("third-week", "week", "in weeks divisible by three", lambda r: r["week"] % 3 == 0),
        ("early-week", "week", "in Weeks 1–4", lambda r: r["week"] <= 4),
        ("late-week", "week", "in Week 10 or later", lambda r: r["week"] >= 10),
        ("odd-year", "year", "in odd-numbered seasons", lambda r: r["season"] % 2 == 1),
        ("even-year", "year", "in even-numbered seasons", lambda r: r["season"] % 2 == 0),
        ("home", "venue", "as ESPN’s designated home team", lambda r: r["venue"] == "HOME"),
        ("away", "venue", "as ESPN’s designated away team", lambda r: r["venue"] == "AWAY"),
        ("odd-whole-score", "score", "with an odd whole-number part of its score", lambda r: r["score"] // 100 % 2 == 1),
        ("even-whole-score", "score", "with an even whole-number part of its score", lambda r: r["score"] // 100 % 2 == 0),
        ("prime-score", "score", "with a prime whole-number part of its score", lambda r: is_prime(r["score"] // 100)),
        ("score-last-seven", "score", "with a whole-number score ending in 7", lambda r: r["score"] // 100 % 10 == 7),
        ("score-last-three", "score", "with a whole-number score ending in 3", lambda r: r["score"] // 100 % 10 == 3),
        ("score-hundredths-two", "score", "with a two-decimal score ending in 2", lambda r: r["score"] % 10 == 2),
        ("score-hundredths-eight", "score", "with a two-decimal score ending in 8", lambda r: r["score"] % 10 == 8),
        ("after-loss", "previous", "the week after a loss", lambda r: r["previous_result"] == "L"),
        ("after-win", "previous", "the week after a win", lambda r: r["previous_result"] == "W"),
        ("after-big-loss", "previous", "the week after losing by at least 20 points", lambda r: r["previous_result"] == "L" and r["previous_margin"] <= -2000),
        ("after-big-win", "previous", "the week after winning by at least 20 points", lambda r: r["previous_result"] == "W" and r["previous_margin"] >= 2000),
        ("after-close-loss", "previous", "the week after losing by fewer than 5 points", lambda r: r["previous_result"] == "L" and r["previous_margin"] > -500),
        ("regular", "phase", "in the regular season", lambda r: r["phase"] == "regular"),
        ("playoff", "phase", "in the championship bracket", lambda r: r["phase"] == "playoff"),
    ]
    for team_id, label in labels.items():
        values.append((f"opponent-{team_id}", "opponent", f"against {label}", lambda r, opponent=team_id: r["opponent_id"] == opponent))
    return values


def record(rows):
    return {"wins": sum(row["result"] == "W" for row in rows),
            "losses": sum(row["result"] == "L" for row in rows),
            "ties": sum(row["result"] == "T" for row in rows)}


def mine_stats(rows, labels, limit=48):
    definitions = conditions(labels)
    by_team = defaultdict(list)
    for row in rows:
        by_team[row["team_id"]].append(row)
    candidates = []
    for team_id, observations in sorted(by_team.items()):
        indexes = [{index for index, row in enumerate(observations) if predicate(row)}
                   for _, _, _, predicate in definitions]
        unique = {}
        for length in (2, 3):
            for combo in itertools.combinations(range(len(definitions)), length):
                families = [definitions[index][1] for index in combo]
                if len(set(families)) != length:
                    continue
                matches = set.intersection(*(indexes[index] for index in combo))
                if not MIN_SAMPLE <= len(matches) <= MAX_SAMPLE or len(observations) - len(matches) < 10:
                    continue
                if len({observations[index]["season"] for index in matches}) < 2:
                    continue
                sample = [observations[index] for index in sorted(matches)]
                counts = record(sample)
                rate = (counts["wins"] + counts["ties"] / 2) / len(sample)
                if .15 < rate < .85:
                    continue
                # One claim per exact evidence set; keep the simpler wording.
                signature = tuple(sorted(matches))
                if signature in unique:
                    continue
                category = "Rivalries" if "opponent" in families else "Bouncebacks" if "previous" in families else "Score quirks" if "score" in families else "Week math"
                unique[signature] = {"team_id": team_id, "team": labels[team_id],
                    "category": category, "conditions": [definitions[index][0] for index in combo],
                    "clauses": [definitions[index][2] for index in combo], "record": counts,
                    "sample_size": len(sample), "overall_record": record(observations),
                    "overall_sample_size": len(observations), "game_ids": [row["id"] for row in sample],
                    "_rank": (abs(rate - .5), len(sample), length)}
        candidates.extend(unique.values())
    candidates.sort(key=lambda value: value["_rank"], reverse=True)
    selected = []
    def choose(candidate):
        evidence = set(candidate["game_ids"])
        for existing in selected:
            if existing["team_id"] != candidate["team_id"]:
                continue
            other = set(existing["game_ids"])
            if len(evidence & other) / len(evidence | other) > .6:
                return False
        selected.append(candidate)
        return True
    # Show a mix of categories and team slots, rather than 48 variants of one stat.
    for category in ("Week math", "Score quirks", "Bouncebacks", "Rivalries"):
        for candidate in [item for item in candidates if item["category"] == category][:20]:
            if choose(candidate):
                break
    for team_id in sorted(by_team):
        for candidate in [item for item in candidates if item["team_id"] == team_id]:
            if choose(candidate):
                break
    for candidate in candidates:
        if len(selected) >= limit:
            break
        if sum(item["team_id"] == candidate["team_id"] for item in selected) < 4:
            choose(candidate)
    for index, candidate in enumerate(selected):
        candidate.pop("_rank")
        candidate["id"] = f"deep-cut-{index + 1}"
    return selected


def main():
    history = json.loads((DIST / "history.json").read_text(encoding="utf-8"))
    seasons = sorted(entry["season"] for entry in history["seasons"] if entry["status"] == "verified")
    current = read_json(f"{BASE}/seasons/{CURRENT_SEASON}/segments/0/leagues/{LEAGUE_ID}?view=mTeam&view=mSettings", CURRENT_SEASON)
    def fetch_season(year):
        url = f"{BASE}/seasons/{year}/segments/0/leagues/{LEAGUE_ID}?{VIEWS}"
        data = read_json(url, year)
        rows, skipped = extract_games(data)
        if not rows:
            raise ValueError(f"No usable games in {year}; existing analytics have been preserved.")
        return year, rows, skipped, url
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(fetch_season, seasons))
    rows = sorted([row for _, games, _, _ in results for row in games], key=lambda row: (row["season"], row["week"], row["team_id"]))
    add_previous_games(rows)
    labels = {row["team_id"]: row["team_name"] for row in rows}
    for team in current["teams"]:
        if team["id"] in labels and team["id"] != 12:
            labels[team["id"]] = name_of(team)
    stats = mine_stats(rows, labels)
    if not stats:
        raise ValueError("No qualifying deep cuts; existing analytics have been preserved.")
    output = {"league_id": LEAGUE_ID, "checked_at": datetime.now(timezone.utc).isoformat(),
              "seasons": seasons, "min_sample": MIN_SAMPLE,
              "game_count": len({(row["season"], row["matchup_id"]) for row in rows}),
              "team_observations": len(rows), "teams": [{"id": team_id, "name": label} for team_id, label in sorted(labels.items())],
              "coverage": [{"season": year, "excluded": skipped, "source_url": url} for year, _, skipped, url in results],
              "stats": stats, "games": rows}
    path = DIST / "analytics.json"
    pending = path.with_suffix(".json.tmp")
    pending.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    pending.replace(path)
    print(f"Mined {len(stats)} stats from {output['game_count']} completed matchups ({len(rows)} team observations).")
    for stat in stats[:8]:
        print(f"{stat['team']}: {stat['record']} / {stat['sample_size']} games / {', '.join(stat['clauses'])}")


if __name__ == "__main__":
    main()
