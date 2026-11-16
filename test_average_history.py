"""Checks for the Average's own recorded history, rather than its current formula."""
import copy
import json
import unittest
from pathlib import Path

from build_average_history import extract_average_season, summarize_games


def fixture(year=2025):
    return {"seasonId": year, "scoringPeriodId": 19, "status": {"finalScoringPeriod": 17},
            "teams": [{"id": tid, "name": f"Team {tid}", "owners": [str(tid)]} for tid in (1, 2, 3)] +
                     [{"id": 12, "name": "Average", "owners": [], "rankCalculatedFinal": 8,
                       "record": {"overall": {"wins": 1, "losses": 0, "ties": 0}}}],
            "settings": {"scheduleSettings": {"matchupPeriods": {"1": [1], "2": [2], "3": [3]}}},
            "schedule": [{"id": 1, "matchupPeriodId": 1, "playoffTierType": "NONE", "winner": "HOME",
                          "home": {"teamId": 12, "totalPoints": 90.04, "adjustment": 90.04},
                          "away": {"teamId": 1, "totalPoints": 80}},
                         {"id": 2, "matchupPeriodId": 1, "playoffTierType": "NONE", "winner": "HOME",
                          "home": {"teamId": 2, "totalPoints": 100}, "away": {"teamId": 3, "totalPoints": 90}}]}


class AverageHistoryTests(unittest.TestCase):
    def test_history_uses_posted_score_and_recorded_result(self):
        data = fixture()
        data["schedule"][0]["away"]["totalPoints"] = 90.02
        data["schedule"][1]["home"]["totalPoints"] = 90
        result = extract_average_season(data)
        game = result["games"][0]
        self.assertEqual(game["score"], 90.04)
        self.assertLess(game["recalculated_average"], game["opponent_score"])
        self.assertEqual(game["result"], "W")
        self.assertEqual(result["regular"]["wins"], 1)

    def test_player_managed_team_12_is_not_the_average(self):
        data = fixture(2021); data["teams"][-1]["owners"] = ["old-manager"]
        self.assertIsNone(extract_average_season(data))
        data = fixture(); data["teams"][-1]["owners"] = ["real-manager"]
        self.assertIsNone(extract_average_season(data))

    def test_unposted_placeholder_zero_is_not_a_loss(self):
        data = fixture(); data["schedule"][0]["home"].update(totalPoints=0, adjustment=0)
        data["schedule"][0]["winner"] = "AWAY"
        result = extract_average_season(data)
        self.assertEqual(result["regular"]["games"], 0)
        self.assertEqual(result["excluded"]["score_not_posted"], 1)
        self.assertFalse(result["regular_coverage_complete"])

    def test_real_zero_average_and_tie_are_retained(self):
        data = fixture()
        for matchup in data["schedule"]:
            matchup["winner"] = "TIE"
            for side in ("home", "away"): matchup[side]["totalPoints"] = 0
        data["schedule"][0]["home"]["adjustment"] = 0
        result = extract_average_season(data)
        self.assertEqual(result["regular"]["ties"], 1)
        self.assertEqual(result["regular"]["win_pct"], .5)
        self.assertEqual(result["regular"]["ppg"], 0)

    def test_current_week_is_excluded_and_playoff_results_are_separate(self):
        data = fixture(2026); data["scoringPeriodId"] = 2
        playoff = {"id": 3, "matchupPeriodId": 2, "playoffTierType": "WINNERS_BRACKET", "winner": "AWAY",
                   "home": {"teamId": 12, "totalPoints": 70, "adjustment": 70}, "away": {"teamId": 2, "totalPoints": 80}}
        data["schedule"].append(playoff)
        result = extract_average_season(data)
        self.assertEqual(result["through_week"], 1)
        self.assertEqual(result["playoffs"]["games"], 0)
        data["seasonId"] = 2025
        result = extract_average_season(data)
        self.assertEqual(result["regular"]["games"], 1)
        self.assertEqual(result["playoffs"]["losses"], 1)
        self.assertEqual(result["playoffs"]["games"], 1)

    def test_consolation_is_not_added_to_the_competitive_record(self):
        data = fixture(); extra = copy.deepcopy(data["schedule"][0]); extra.update(id=3, matchupPeriodId=3, playoffTierType="LOSERS_CONSOLATION_LADDER")
        data["schedule"].append(extra)
        result = extract_average_season(data)
        self.assertEqual(result["regular"]["games"], 1)
        self.assertEqual(result["playoffs"]["games"], 0)
        self.assertEqual(result["excluded"]["consolation"], 1)

    def test_duplicates_are_not_counted_twice_and_bad_scores_fail(self):
        data = fixture(); data["schedule"].append(copy.deepcopy(data["schedule"][0]))
        self.assertEqual(extract_average_season(data)["regular"]["games"], 1)
        data["schedule"][-1]["home"]["totalPoints"] = 91
        with self.assertRaisesRegex(ValueError, "Conflicting Average"):
            extract_average_season(data)
        data = fixture(); data["schedule"][0]["home"]["totalPoints"] = None
        with self.assertRaises(ValueError): extract_average_season(data)

    def test_published_records_reconcile_to_the_recorded_games(self):
        data = json.loads((Path(__file__).parent / "website/dist/average-history.json").read_text(encoding="utf-8"))
        regular = []
        for season in data["seasons"]:
            self.assertGreaterEqual(season["season"], 2022)
            for phase, key in (("regular", "regular"), ("playoff", "playoffs")):
                games = [game for game in season["games"] if game["phase"] == phase]
                self.assertEqual(season[key]["games"], len(games))
                self.assertEqual(season[key]["wins"], sum(game["result"] == "W" for game in games))
                self.assertEqual(season[key]["losses"], sum(game["result"] == "L" for game in games))
                self.assertTrue(all(game["week"] <= season["through_week"] for game in games))
            self.assertTrue(season["regular_coverage_complete"])
            regular.extend(game for game in season["games"] if game["phase"] == "regular")
        self.assertEqual(data["regular"], summarize_games(regular))
        self.assertEqual(len({game["id"] for game in regular}), len(regular))


if __name__ == "__main__":
    unittest.main()
