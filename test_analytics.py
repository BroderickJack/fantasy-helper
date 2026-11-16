"""Check historical scope, numeric quirks, and every published mined claim."""

import copy
import json
import unittest
from pathlib import Path

from build_analytics import add_previous_games, cents, conditions, extract_games, is_prime, record


def fixture(season=2025):
    return {"seasonId": season, "teams": [{"id": 1, "name": "One", "owners": ["a"]},
                {"id": 2, "name": "Two", "owners": ["b"]},
                {"id": 12, "name": "Average", "owners": []}],
            "settings": {"scheduleSettings": {"matchupPeriods": {"3": [5]}}},
            "schedule": [{"id": 11, "matchupPeriodId": 3, "playoffTierType": "NONE", "winner": "HOME",
                          "home": {"teamId": 1, "totalPoints": 100.12},
                          "away": {"teamId": 2, "totalPoints": 95.1}}]}


class AnalyticsTests(unittest.TestCase):
    def test_scores_use_integer_hundredths_with_correct_week_and_period(self):
        rows, _ = extract_games(fixture())
        self.assertEqual(rows[0]["score"], 10012)
        self.assertEqual(rows[1]["score"], 9510)
        self.assertEqual(rows[0]["week"], 5)
        self.assertEqual(rows[0]["matchup_period"], 3)
        self.assertEqual([row["result"] for row in rows], ["W", "L"])
        self.assertEqual(cents(-2.04), -204)
        self.assertEqual(cents(0), 0)

    def test_team_12_was_real_before_the_placeholder_era(self):
        data = fixture(2021)
        data["teams"][-1]["owners"] = ["real-owner"]
        data["schedule"][0]["away"]["teamId"] = 12
        rows, skipped = extract_games(data)
        self.assertEqual({row["team_id"] for row in rows}, {1, 12})
        self.assertNotIn("placeholder", skipped)

    def test_ownerless_placeholder_excluded_from_2022(self):
        data = fixture(2022); data["schedule"][0]["away"]["teamId"] = 12
        rows, skipped = extract_games(data)
        self.assertEqual(rows, [])
        self.assertEqual(skipped["placeholder"], 1)
        data["teams"][-1]["owners"] = ["unexpected-owner"]
        with self.assertRaisesRegex(ValueError, "review the placeholder rule"):
            extract_games(data)

    def test_current_season_and_invalid_final_scores_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "completed past seasons"):
            extract_games(fixture(2026))
        for value in (None, float("nan"), float("inf"), True):
            data = fixture(); data["schedule"][0]["home"]["totalPoints"] = value
            with self.assertRaises(ValueError): extract_games(data)
        data = fixture(); data["schedule"][0]["winner"] = "AWAY"
        with self.assertRaisesRegex(ValueError, "disagree"): extract_games(data)

    def test_consolation_unfinished_byes_and_multiweek_games_are_excluded(self):
        data = fixture()
        data["schedule"][0]["playoffTierType"] = "LOSERS_CONSOLATION_LADDER"
        self.assertEqual(extract_games(data)[0], [])
        data = fixture(); data["schedule"][0]["winner"] = "UNDECIDED"
        self.assertEqual(extract_games(data)[0], [])
        data = fixture(); del data["schedule"][0]["away"]
        self.assertEqual(extract_games(data)[0], [])
        data = fixture(); data["settings"]["scheduleSettings"]["matchupPeriods"]["3"] = [5, 6]
        self.assertEqual(extract_games(data)[0], [])

    def test_identical_duplicates_count_once_and_conflicts_are_rejected(self):
        data = fixture(); data["schedule"].append(copy.deepcopy(data["schedule"][0]))
        self.assertEqual(len(extract_games(data)[0]), 2)
        data["schedule"][1]["home"]["totalPoints"] = 105
        with self.assertRaisesRegex(ValueError, "Conflicting duplicate"):
            extract_games(data)

    def test_ties_are_kept_without_awarding_a_win(self):
        data = fixture(); data["schedule"][0]["winner"] = "TIE"
        data["schedule"][0]["away"]["totalPoints"] = 100.12
        rows, _ = extract_games(data)
        self.assertEqual(record(rows), {"wins": 0, "losses": 0, "ties": 2})

    def test_previous_game_requires_consecutive_weeks_and_same_season(self):
        rows = [dict(id="a", season=2024, week=16, team_id=1, score=12000, opponent_score=9000, result="W"),
                dict(id="b", season=2025, week=1, team_id=1, score=9000, opponent_score=10000, result="L"),
                dict(id="c", season=2025, week=2, team_id=1, score=11000, opponent_score=10000, result="W"),
                dict(id="d", season=2025, week=4, team_id=1, score=8000, opponent_score=10000, result="L")]
        add_previous_games(rows)
        self.assertIsNone(rows[1]["previous_id"])
        self.assertEqual(rows[2]["previous_id"], "b")
        self.assertEqual(rows[2]["previous_margin"], -1000)
        self.assertIsNone(rows[3]["previous_id"])

    def test_prime_and_score_digits_are_literal(self):
        self.assertFalse(is_prime(1)); self.assertTrue(is_prime(2))
        self.assertTrue(is_prime(17)); self.assertFalse(is_prime(9))
        predicates = {key: predicate for key, _, _, predicate in conditions({})}
        self.assertTrue(predicates["score-last-seven"]({"score": 10782}))
        self.assertTrue(predicates["score-hundredths-two"]({"score": 10782}))
        self.assertTrue(predicates["prime-score"]({"score": 10782}))
        self.assertFalse(predicates["score-hundredths-eight"]({"score": 10782}))

    def test_every_published_stat_matches_all_and_only_its_evidence(self):
        archive = json.loads((Path(__file__).parent / "website/dist/analytics.json").read_text(encoding="utf-8"))
        labels = {team["id"]: team["name"] for team in archive["teams"]}
        definitions = {key: (family, predicate) for key, family, _, predicate in conditions(labels)}
        ids = {game["id"] for game in archive["games"]}
        self.assertEqual(len(ids), len(archive["games"]))
        self.assertEqual(archive["game_count"] * 2, len(archive["games"]))
        self.assertGreater(len(archive["stats"]), 0)
        for stat in archive["stats"]:
            with self.subTest(stat=stat["id"]):
                rows = [row for row in archive["games"] if row["team_id"] == stat["team_id"]]
                matches = [row for row in rows if all(definitions[key][1](row) for key in stat["conditions"])]
                self.assertEqual({row["id"] for row in matches}, set(stat["game_ids"]))
                self.assertEqual(record(matches), stat["record"])
                self.assertEqual(record(rows), stat["overall_record"])
                self.assertEqual(len(matches), stat["sample_size"])
                self.assertGreaterEqual(len(matches), archive["min_sample"])
                self.assertGreaterEqual(len({row["season"] for row in matches}), 2)
                self.assertEqual(len({definitions[key][0] for key in stat["conditions"]}), len(stat["conditions"]))


if __name__ == "__main__":
    unittest.main()
