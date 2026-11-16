"""Serious QRFFL metrics, kept independent of fetching and page rendering."""
import math
from collections import defaultdict
from statistics import pstdev

from build_analytics import cents, name_of
from import_history import CURRENT_SEASON, team_info


def season_performance(data, cutoff=None):
    year = data["seasonId"]
    cutoff = cutoff if cutoff is not None else (data["scoringPeriodId"] - 1 if year == CURRENT_SEASON else data["status"]["finalScoringPeriod"])
    teams = {t["id"]: t for t in data["teams"] if not (year >= 2022 and t["id"] == 12 and not t.get("owners"))}
    members = {m["id"]: m for m in data.get("members", [])}
    periods = data["settings"]["scheduleSettings"]["matchupPeriods"]
    weeks = defaultdict(dict)
    records = defaultdict(dict)
    for matchup in data.get("schedule", []):
        if matchup.get("playoffTierType", "NONE") != "NONE" or matchup.get("winner") not in ("HOME", "AWAY", "TIE"):
            continue
        scores = periods.get(str(matchup["matchupPeriodId"]), [])
        if len(scores) != 1 or scores[0] > cutoff:
            continue
        week = scores[0]
        for venue in ("home", "away"):
            side = matchup.get(venue)
            if not side or side["teamId"] not in teams:
                continue
            tid = side["teamId"]
            score = cents(side.get("totalPoints"))
            previous = weeks[week].get(tid)
            if previous is not None and previous != score:
                raise ValueError("Conflicting weekly scores")
            weeks[week][tid] = score
            outcome = "T" if matchup["winner"] == "TIE" else "W" if matchup["winner"].lower() == venue else "L"
            row = {"week": week, "score": score, "result": outcome,
                   "source_url": f"https://fantasy.espn.com/football/scoreboard?leagueId=666462&seasonId={year}&matchupPeriodId={matchup['matchupPeriodId']}"}
            if week in records[tid] and records[tid][week] != row:
                raise ValueError("Conflicting recorded matchup results")
            records[tid][week] = row
    output = []
    for tid, team in teams.items():
        observations = sorted(records[tid].values(), key=lambda r: r["week"])
        if not observations:
            continue
        complete = all(set(weeks[row["week"]]) == set(teams) for row in observations)
        comparisons = []
        indexes = []
        for row in observations:
            field = weeks[row["week"]]
            if set(field) != set(teams):
                continue
            others = [score for other, score in field.items() if other != tid]
            win_equivalent = sum(row["score"] > score for score in others) + sum(row["score"] == score for score in others) / 2
            row["all_play"] = win_equivalent / len(others)
            mean = sum(field.values()) / len(field)
            row["scoring_index"] = row["score"] / mean * 100 if mean > 0 else None
            comparisons.append((win_equivalent, len(others)))
            if row["scoring_index"] is not None:
                indexes.append(row["scoring_index"])
        count = len(observations)
        wins = sum(r["result"] == "W" for r in observations)
        losses = sum(r["result"] == "L" for r in observations)
        ties = count - wins - losses
        expected = sum(r["all_play"] for r in observations) if complete else None
        info = team_info(team, members)
        output.append({"season": year, "team_id": tid, "team_name": name_of(team),
                       "managers": info["manager_display_names"], "final_rank": team.get("rankCalculatedFinal") or None,
                       "wins": wins, "losses": losses, "ties": ties, "games": count,
                       "points_for": sum(r["score"] for r in observations) / 100,
                       "ppg": sum(r["score"] for r in observations) / count / 100,
                       "volatility": pstdev(r["score"] / 100 for r in observations),
                       "all_play_wins": sum(w for w, _ in comparisons) if complete else None,
                       "all_play_comparisons": sum(n for _, n in comparisons) if complete else None,
                       "expected_wins": expected,
                       "schedule_swing": wins + ties / 2 - expected if expected is not None else None,
                       "scoring_index": sum(indexes) / count if complete and len(indexes) == count else None,
                       "weekly": observations,
                       "standings_url": f"https://fantasy.espn.com/football/standings?leagueId=666462&seasonId={year}"})
    return output


def transaction_key(tx):
    return str(tx.get("relatedTransactionId") or tx.get("id") or "")


def transaction_date(tx):
    return next((tx[key] for key in ("processDate", "acceptedDate", "proposedDate") if isinstance(tx.get(key), (int, float))), None)


def recover_trades(players):
    best = {}
    for wrapper in players.values():
        for tx in wrapper.get("transactions", wrapper.get("player", {}).get("transactions", [])):
            if tx.get("type") != "TRADE_ACCEPT" or tx.get("status") != "EXECUTED":
                continue
            legs = [i for i in tx.get("items", []) if i.get("type") == "TRADE"]
            if not legs:
                continue
            key = transaction_key(tx)
            if not key:
                continue
            signature = {(i.get("playerId"), i.get("fromTeamId"), i.get("toTeamId")) for i in legs}
            old = best.get(key)
            if old:
                prior = {(i.get("playerId"), i.get("fromTeamId"), i.get("toTeamId")) for i in old["legs"]}
                if not signature <= prior and not prior <= signature:
                    raise ValueError("Conflicting trade receipts need review")
                if len(prior) >= len(signature):
                    continue
            if any(not isinstance(i.get("playerId"), int) or not i["playerId"] or not i.get("fromTeamId") or not i.get("toTeamId") or i["fromTeamId"] == i["toTeamId"] for i in legs):
                raise ValueError("Unsupported player or pick trade receipt")
            if len({i["playerId"] for i in legs}) != len(legs):
                raise ValueError("A trade moves one player more than once")
            best[key] = {"id": key, "week": tx["scoringPeriodId"], "date": transaction_date(tx), "legs": legs,
                         "associated_drops": [i["playerId"] for i in tx.get("items", []) if i.get("type") == "DROP"]}
    return sorted(best.values(), key=lambda tx: (tx["week"], tx["id"]))


def actual_points(player, season, week, pro_teams):
    actual = [s for s in player.get("stats", []) if s.get("seasonId") == season and s.get("statSourceId") == 0 and s.get("statSplitTypeId") == 1]
    matches = [s for s in actual if s.get("scoringPeriodId") == week]
    if matches:
        values = {cents(s.get("appliedTotal")) for s in matches}
        if len(values) != 1:
            raise ValueError("Conflicting player-week scores")
        return values.pop(), "actual"
    # A missing row is zero only when an unchanged NFL team has a documented bye.
    ids = {s.get("proTeamId") for s in actual if s.get("proTeamId")}
    if len(ids) == 1:
        team = pro_teams.get(next(iter(ids)), {})
        if team.get("byeWeek") == week:
            return 0, "bye"
    return None, "missing"


def exit_week(wrapper, trade, recipient):
    found = []
    for tx in wrapper.get("transactions", wrapper.get("player", {}).get("transactions", [])):
        if tx.get("status") != "EXECUTED" or transaction_key(tx) == trade["id"]:
            continue
        exits = [i for i in tx.get("items", []) if i.get("playerId") == wrapper["id"] and i.get("type") in ("TRADE", "DROP") and i.get("fromTeamId") == recipient and i.get("toTeamId") != recipient]
        if not exits:
            continue
        when = transaction_date(tx)
        if trade.get("date") is not None and when is not None:
            later = when > trade["date"]
        else:
            later = tx.get("scoringPeriodId", 0) > trade["week"]
        if later:
            found.append(tx["scoringPeriodId"])
        elif when is None and tx.get("scoringPeriodId") == trade["week"]:
            found.append(trade["week"])  # No full-week credit for an ambiguous same-week exit.
    return min(found) if found else None


def measure_player(leg, trade, players, rosters, pro_teams, season, through, active_weeks=None):
    wrapper = players.get(leg["playerId"])
    if not wrapper:
        return {"player_id": leg["playerId"], "name": f"Player #{leg['playerId']}", "starter_points": None,
                "production_points": None, "evidence": [], "coverage": "Player card unavailable"}
    player = wrapper["player"]
    stop = exit_week(wrapper, trade, leg["toTeamId"])
    starter_total = production_total = 0
    starter_complete = production_complete = True
    retained = True
    evidence = []
    for week in range(trade["week"] + 1, through + 1):
        value, reason = actual_points(player, season, week, pro_teams)
        if value is None:
            production_complete = False
        else:
            production_total += value
        state = "exited" if stop is not None and week >= stop else "active"
        credit = 0
        slot = None
        if state == "active" and retained:
            roster = rosters.get(week)
            if roster is None or leg["toTeamId"] not in roster:
                state = "roster unavailable"; starter_complete = False; credit = None
            else:
                entry = roster[leg["toTeamId"]].get(leg["playerId"])
                if entry is None:
                    retained = False; state = "left roster"
                else:
                    slot = entry.get("lineupSlotId")
                    if slot in (20, 21):
                        state = "bench / IR"
                    elif isinstance(slot, int) and slot >= 0:
                        if active_weeks is not None and (leg["toTeamId"], week) not in active_weeks:
                            state = "no scored matchup"
                        else:
                            state = "started"
                            credit = value
                            if value is None:
                                starter_complete = False
                    else:
                        state = "lineup unavailable"; credit = None; starter_complete = False
        elif state == "active":
            state = "left roster"
        if credit is not None:
            starter_total += credit
        evidence.append({"week": week, "points": value / 100 if value is not None else None,
                         "score_source": reason, "lineup": state, "slot": slot,
                         "starter_credit": credit / 100 if credit is not None else None})
    return {"player_id": leg["playerId"], "name": player["fullName"],
            "starter_points": starter_total / 100 if starter_complete else None,
            "production_points": production_total / 100 if production_complete else None,
            "exit_week": stop, "evidence": evidence,
            "coverage": "complete" if starter_complete else "Incomplete lineup or point coverage"}


def measure_trade(trade, players, rosters, pro_teams, data, performance, through):
    year = data["seasonId"]
    teams = {t["id"]: t for t in data["teams"]}
    members = {m["id"]: m for m in data.get("members", [])}
    periods = data["settings"]["scheduleSettings"]["matchupPeriods"]
    active_weeks = set()
    for game in data.get("schedule", []):
        weeks = periods.get(str(game["matchupPeriodId"]), [])
        if len(weeks) == 1 and game.get("home") and game.get("away") and game.get("winner") in ("HOME", "AWAY", "TIE"):
            active_weeks.update((game[side]["teamId"], weeks[0]) for side in ("home", "away"))
    party_ids = sorted({leg["fromTeamId"] for leg in trade["legs"]} | {leg["toTeamId"] for leg in trade["legs"]})
    parties = []
    for tid in party_ids:
        incoming = [leg for leg in trade["legs"] if leg["toTeamId"] == tid]
        outgoing = [leg for leg in trade["legs"] if leg["fromTeamId"] == tid]
        info = team_info(teams[tid], members)
        received = [measure_player(leg, trade, players, rosters, pro_teams, year, through, active_weeks) for leg in incoming]
        sent = [{"player_id": leg["playerId"], "name": players.get(leg["playerId"], {}).get("player", {}).get("fullName", f"Player #{leg['playerId']}")} for leg in outgoing]
        weekly = next((row["weekly"] for row in performance if row["season"] == year and row["team_id"] == tid), [])
        def split(rows):
            return {"games": len(rows), "wins": sum(r["result"] == "W" for r in rows),
                    "losses": sum(r["result"] == "L" for r in rows), "ties": sum(r["result"] == "T" for r in rows),
                    "ppg": sum(r["score"] for r in rows) / len(rows) / 100 if rows else None}
        parties.append({"team_id": tid, "team_name": name_of(teams[tid]), "managers": info["manager_display_names"],
                        "received": received, "sent": sent,
                        "starter_points": sum(cents(p["starter_points"]) for p in received) / 100 if all(p["starter_points"] is not None for p in received) else None,
                        "production_points": sum(cents(p["production_points"]) for p in received) / 100 if all(p["production_points"] is not None for p in received) else None,
                        "before": split([r for r in weekly if r["week"] < trade["week"]]),
                        "after": split([r for r in weekly if r["week"] > trade["week"]])})
    edge = None
    if len(parties) == 2 and through > trade["week"] and all(p["starter_points"] is not None for p in parties):
        difference = cents(parties[0]["starter_points"]) - cents(parties[1]["starter_points"])
        edge = {"team_id": parties[0]["team_id"] if difference >= 0 else parties[1]["team_id"], "points": abs(difference) / 100}
    return {"id": f"{year}:{trade['id']}", "season": year, "week": trade["week"], "date": trade["date"],
            "through_week": through, "first_full_week": trade["week"] + 1, "parties": parties,
            "period_by_week": {str(week): int(period) for period, weeks in periods.items() for week in weeks},
            "starter_edge": edge, "associated_drops": [players.get(pid, {}).get("player", {}).get("fullName", f"Player #{pid}") for pid in trade["associated_drops"]],
            "source_url": f"https://fantasy.espn.com/football/recentactivity?leagueId=666462&seasonId={year}"}
