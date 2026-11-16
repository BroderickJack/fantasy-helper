"""Regression tests for normalized scoring, schedule comparisons, and retained trade credit."""
import copy
import json
import unittest
from pathlib import Path

from build_analytics import cents
from research_metrics import season_performance, recover_trades, actual_points, measure_player


def season_fixture():
    def side(tid, points): return {"teamId": tid, "totalPoints": points}
    return {"seasonId": 2025, "scoringPeriodId": 19, "status": {"finalScoringPeriod": 17},
            "teams": [{"id": tid, "name": f"Team {tid}", "owners": [] if tid == 12 else [str(tid)], "rankCalculatedFinal": tid} for tid in (1, 2, 3, 12)],
            "members": [], "settings": {"scheduleSettings": {"matchupPeriods": {"1": [1], "2": [2]}}},
            "schedule": [{"id": 1, "matchupPeriodId": 1, "winner": "HOME", "home": side(1, 100), "away": side(2, 80)},
                         {"id": 2, "matchupPeriodId": 1, "winner": "HOME", "home": side(3, 120), "away": side(12, 0)},
                         {"id": 3, "matchupPeriodId": 2, "winner": "TIE", "home": side(1, 90), "away": side(2, 90)},
                         {"id": 4, "matchupPeriodId": 2, "winner": "HOME", "home": side(3, 60), "away": side(12, 0)}]}


def player_fixture():
    def stat(week, value, team=2): return {"seasonId": 2025, "statSourceId": 0, "statSplitTypeId": 1, "scoringPeriodId": week, "appliedTotal": value, "proTeamId": team}
    wrapper = {"id": 101, "player": {"fullName": "Player", "stats": [stat(2, 10), stat(3, -2), stat(4, 50), stat(5, 8)]}, "transactions": []}
    leg = {"playerId": 101, "fromTeamId": 2, "toTeamId": 1}
    trade = {"id": "deal", "week": 1, "date": 100}
    rosters = {week: {1: {101: {"lineupSlotId": 20 if week == 2 else 0}}} for week in range(2, 6)}
    return wrapper, leg, trade, rosters


class PerformanceTests(unittest.TestCase):
    def test_allplay_includes_the_real_team_facing_the_average_and_ties(self):
        rows = {r["team_id"]: r for r in season_performance(season_fixture())}
        self.assertEqual(set(rows), {1, 2, 3})
        one = rows[1]
        self.assertEqual((one["wins"], one["losses"], one["ties"]), (1, 0, 1))
        self.assertEqual(one["all_play_comparisons"], 4)
        self.assertEqual(one["all_play_wins"], 2.5)
        self.assertEqual(one["expected_wins"], 1.25)
        self.assertEqual(one["schedule_swing"], .25)
        self.assertEqual(one["ppg"], 95)
        self.assertEqual(one["scoring_index"], 106.25)
        self.assertEqual(rows[3]["games"], 2)
        self.assertEqual(rows[3]["expected_wins"], 1)

    def test_missing_weekly_field_is_unknown_instead_of_a_partial_comparison(self):
        data = season_fixture(); data["teams"].append({"id": 4, "name": "Missing team", "owners": ["4"], "rankCalculatedFinal": 4})
        rows = season_performance(data)
        self.assertTrue(all(row["expected_wins"] is None and row["scoring_index"] is None for row in rows))

    def test_current_active_week_and_consolation_are_not_in_performance(self):
        data = season_fixture(); data["seasonId"] = 2026; data["scoringPeriodId"] = 2
        rows = season_performance(data)
        self.assertTrue(all(row["games"] == 1 for row in rows))
        data = season_fixture(); data["schedule"][0]["playoffTierType"] = "LOSERS_CONSOLATION_LADDER"
        self.assertEqual(next(row for row in season_performance(data) if row["team_id"] == 1)["games"], 1)


class TradeTests(unittest.TestCase):
    def test_duplicate_trade_receipts_merge_to_the_full_package(self):
        leg = {"type": "TRADE", "playerId": 101, "fromTeamId": 1, "toTeamId": 2}
        other = {"type": "TRADE", "playerId": 102, "fromTeamId": 2, "toTeamId": 1}
        tx = {"id": "accept", "relatedTransactionId": "deal", "type": "TRADE_ACCEPT", "status": "EXECUTED", "scoringPeriodId": 3, "items": [leg]}
        full = copy.deepcopy(tx); full["items"].append(other)
        records = recover_trades({101: {"transactions": [tx]}, 102: {"transactions": [full]}})
        self.assertEqual(len(records), 1); self.assertEqual(len(records[0]["legs"]), 2)
        full["status"] = "CANCELED"
        self.assertEqual(recover_trades({102: {"transactions": [full]}}), [])

    def test_actual_points_use_week_entries_and_only_confirmed_bye_zeros(self):
        wrapper, _, _, _ = player_fixture(); player = wrapper["player"]
        self.assertEqual(actual_points(player, 2025, 2, {}), (1000, "actual"))
        self.assertEqual(actual_points(player, 2025, 7, {2: {"byeWeek": 7}}), (0, "bye"))
        self.assertEqual(actual_points(player, 2025, 7, {}), (None, "missing"))
        player["stats"][-1]["proTeamId"] = 3
        self.assertEqual(actual_points(player, 2025, 7, {2: {"byeWeek": 7}}), (None, "missing"))

    def test_starter_credit_excludes_bench_trade_week_exit_week_and_reacquisition(self):
        wrapper, leg, trade, rosters = player_fixture()
        wrapper["transactions"] = [{"id": "drop", "type": "DROP", "status": "EXECUTED", "scoringPeriodId": 4, "processDate": 400, "items": [{"type": "DROP", "playerId": 101, "fromTeamId": 1, "toTeamId": 0}]}]
        result = measure_player(leg, trade, {101: wrapper}, rosters, {}, 2025, 5)
        self.assertEqual(result["starter_points"], -2)
        self.assertEqual(result["production_points"], 66)
        self.assertEqual([e["week"] for e in result["evidence"]], [2, 3, 4, 5])
        self.assertEqual([e["starter_credit"] for e in result["evidence"]], [0, -2, 0, 0])

    def test_missing_roster_prevents_an_edge_and_absence_stops_future_credit(self):
        wrapper, leg, trade, rosters = player_fixture()
        del rosters[3]
        self.assertIsNone(measure_player(leg, trade, {101: wrapper}, rosters, {}, 2025, 5)["starter_points"])
        _, _, _, rosters = player_fixture(); del rosters[3][1][101]
        result = measure_player(leg, trade, {101: wrapper}, rosters, {}, 2025, 5)
        self.assertEqual(result["starter_points"], 0)

    def test_starts_without_a_scored_matchup_do_not_receive_credit(self):
        wrapper, leg, trade, rosters = player_fixture()
        result = measure_player(leg, trade, {101: wrapper}, rosters, {}, 2025, 5, {(1, 2)})
        self.assertEqual(result["starter_points"], 0)
        self.assertEqual(result["evidence"][1]["lineup"], "no scored matchup")

    def test_missing_started_points_remain_unknown(self):
        wrapper, leg, trade, rosters = player_fixture()
        wrapper["player"]["stats"] = [s for s in wrapper["player"]["stats"] if s["scoringPeriodId"] != 3]
        result = measure_player(leg, trade, {101: wrapper}, rosters, {}, 2025, 5)
        self.assertIsNone(result["starter_points"])
        self.assertIsNone(result["production_points"])

    def test_published_trade_totals_and_edges_reconcile_to_weekly_receipts(self):
        data = json.loads((Path(__file__).parent / "website/dist/research.json").read_text(encoding="utf-8"))
        self.assertGreater(len(data["trades"]), 0)
        for trade in data["trades"]:
            with self.subTest(trade=trade["id"]):
                received = sorted(p["player_id"] for party in trade["parties"] for p in party["received"])
                sent = sorted(p["player_id"] for party in trade["parties"] for p in party["sent"])
                self.assertEqual(received, sent)
                for party in trade["parties"]:
                    for player in party["received"]:
                        events = player["evidence"]
                        self.assertTrue(all(trade["first_full_week"] <= event["week"] <= trade["through_week"] for event in events))
                        if player["starter_points"] is not None:
                            self.assertEqual(cents(player["starter_points"]), sum(cents(e["starter_credit"]) for e in events))
                        if player["production_points"] is not None:
                            self.assertEqual(cents(player["production_points"]), sum(cents(e["points"]) for e in events))
                        for event in events:
                            if event["lineup"] in ("bench / IR", "exited", "left roster", "no scored matchup"):
                                self.assertEqual(event["starter_credit"], 0)
                if trade["starter_edge"]:
                    a, b = trade["parties"]
                    difference = abs(cents(a["starter_points"]) - cents(b["starter_points"]))
                    self.assertEqual(cents(trade["starter_edge"]["points"]), difference)


if __name__ == "__main__":
    unittest.main()
