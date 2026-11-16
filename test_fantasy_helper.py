"""Offline checks for the averaging rules and ESPN's scoring edge cases."""

import copy
import unittest
from unittest.mock import patch

from fantasy_helper import fetch_league, resolve_period, starter_projection, summarize


def fixture():
    data = {"id": 666462, "scoringPeriodId": 10,
            "settings": {"scheduleSettings": {"matchupPeriods": {"10": [10]}}},
            "teams": [{"id": i, "name": f"Team {i}"} for i in range(1, 17)],
            "schedule": []}
    for i in range(1, 17, 2):
        sides = [{"teamId": j, "totalPoints": 0, "totalPointsLive": j * 10,
                  "totalProjectedPoints": 100 + j,
                  "totalProjectedPointsLive": 120 + j} for j in (i, i + 1)]
        data["schedule"].append({"matchupPeriodId": 10, "home": sides[0], "away": sides[1]})
    return data


class AverageTests(unittest.TestCase):
    def test_all_15_real_teams_and_live_fields(self):
        data = fixture()
        data["schedule"][5]["away"]["totalPointsLive"] = 999999  # Placeholder must never count.
        result = summarize(data, 10, 2026, 12)
        self.assertEqual(result["teams_counted"], 15)
        self.assertAlmostEqual(result["current_average"], (1360 - 120) / 15)
        self.assertAlmostEqual(result["live_projected_average"], (16 * 120 + 136 - 132) / 15)
        self.assertAlmostEqual(result["pregame_projected_average"], (1600 + 136 - 112) / 15)

    def test_optional_opponent_exclusion(self):
        result = summarize(fixture(), 10, 2026, 12, exclude_opponent=True)
        self.assertEqual(result["teams_counted"], 14)
        self.assertNotIn(11, [row["team_id"] for row in result["teams"]])

    def test_missing_team_refuses_partial_average(self):
        data = fixture()
        del data["schedule"][0]["away"]
        with self.assertRaisesRegex(ValueError, "Missing week"):
            summarize(data, 10, 2026, 12)

    def test_wrong_team_count_is_rejected(self):
        data = fixture()
        data["teams"].pop()
        with self.assertRaisesRegex(ValueError, "Expected 15"):
            summarize(data, 10, 2026, 12)

    def test_missing_projection_is_unknown_instead_of_zero(self):
        data = fixture()
        del data["schedule"][0]["home"]["totalProjectedPointsLive"]
        result = summarize(data, 10, 2026, 12)
        self.assertIsNone(result["live_projected_average"])
        self.assertIsNotNone(result["pregame_projected_average"])

    def test_zero_and_negative_scores_are_preserved(self):
        data = fixture()
        side = data["schedule"][0]["home"]
        side.update(totalPointsLive=-2, totalProjectedPointsLive=0)
        row = summarize(data, 10, 2026, 12)["teams"][0]
        self.assertEqual(row["current"], -2)
        self.assertEqual(row["live_projected"], 0)

    def test_historical_score_fallback(self):
        data = fixture()
        side = data["schedule"][0]["home"]
        del side["totalPointsLive"]
        side["totalPoints"] = 101.25
        result = summarize(data, 10, 2026, 12)
        self.assertEqual(result["teams"][0]["current"], 101.25)
        self.assertIsNone(result["live_projected_average"])

    def test_duplicate_matchups_do_not_count_teams_twice(self):
        data = fixture()
        data["schedule"].append(copy.deepcopy(data["schedule"][0]))
        self.assertEqual(summarize(data, 10, 2026, 12)["teams_counted"], 15)

    def test_multiweek_matchup_is_rejected(self):
        data = fixture()
        data["settings"]["scheduleSettings"]["matchupPeriods"]["10"] = [10, 11]
        with self.assertRaisesRegex(ValueError, "multiweek"):
            resolve_period(data, 10)

    def test_roster_projection_uses_only_starters_and_requested_week(self):
        def entry(slot, value):
            return {"lineupSlotId": slot, "playerPoolEntry": {"player": {"stats": [
                {"statSourceId": 1, "statSplitTypeId": 1, "scoringPeriodId": 10,
                 "seasonId": 2026, "appliedTotal": value},
                {"statSourceId": 0, "statSplitTypeId": 1, "scoringPeriodId": 10,
                 "seasonId": 2026, "appliedTotal": 999},
                {"statSourceId": 1, "statSplitTypeId": 1, "scoringPeriodId": 9,
                 "seasonId": 2026, "appliedTotal": 999}]}}}
        side = {"rosterForCurrentScoringPeriod": {"entries": [
            entry(0, 20.12345), entry(2, 10.12345), entry(20, 99), entry(21, 99)]}}
        self.assertAlmostEqual(starter_projection(side, 10, 2026), 30.2469)

    @patch("fantasy_helper.urlopen")
    @patch.dict("os.environ", {"ESPN_S2": "", "ESPN_SWID": ""})
    def test_request_contains_week_and_matchup_filter(self, open_url):
        import json
        from io import BytesIO
        open_url.return_value.__enter__.return_value = BytesIO(json.dumps(fixture()).encode())
        fetch_league(666462, 2026, 10, 10)
        request = open_url.call_args.args[0]
        self.assertIn("scoringPeriodId=10", request.full_url)
        self.assertEqual(json.loads(request.get_header("X-fantasy-filter")),
                         {"schedule": {"filterMatchupPeriodIds": {"value": [10]}}})
        self.assertIsNone(request.get_header("Cookie"))


if __name__ == "__main__":
    unittest.main()
