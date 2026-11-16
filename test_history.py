"""Verify that the archive importer awards playoff titles, not regular-season seeds."""
import copy
import unittest
from import_history import extract_champion, merge_league_records


def fixture():
    return {"seasonId": 2025,
            "members": [{"id": "owner", "firstName": "adam", "lastName": "d"}],
            "teams": [{"id": 1, "name": "Playoff Champion", "rankCalculatedFinal": 1, "playoffSeed": 8, "owners": ["owner"], "record": {"overall": {"wins": 6, "losses": 8, "ties": 0}}},
                      {"id": 2, "name": "Top Seed", "rankCalculatedFinal": 2, "playoffSeed": 1, "owners": []}],
            "schedule": [{"id": 1, "matchupPeriodId": 2, "playoffTierType": "NONE", "winner": "AWAY", "home": {"teamId": 1, "totalPoints": 60}, "away": {"teamId": 2, "totalPoints": 100}},
                         {"id": 2, "matchupPeriodId": 17, "playoffTierType": "WINNERS_BRACKET", "winner": "HOME", "home": {"teamId": 1, "totalPoints": 134.2}, "away": {"teamId": 2, "totalPoints": 97.94}}]}


class HistoryTests(unittest.TestCase):
    def test_champion_uses_final_rank_and_final_winner_not_seed(self):
        entry = extract_champion(fixture(), "https://example.com/source")
        self.assertEqual(entry["champion"]["team_id"], 1)
        self.assertEqual(entry["final"]["matchup_period"], 17)
        self.assertEqual(entry["final"]["champion_score"], 134.2)
        self.assertEqual(entry["champion"]["regular_season_record"]["wins"], 6)

    def test_user_display_name_preserves_the_original_manager(self):
        entry = extract_champion(fixture(), "source")
        self.assertEqual(entry["champion"]["managers"], ["adam d"])
        self.assertEqual(entry["champion"]["manager_display_names"], ["Adam"])

    def test_current_season_is_never_given_a_champion(self):
        data = fixture(); data["seasonId"] = 2026
        with self.assertRaisesRegex(ValueError, "in progress"):
            extract_champion(data, "source")

    def test_disagreement_between_standings_and_matchup_is_rejected(self):
        data = fixture(); data["schedule"][-1]["winner"] = "AWAY"
        with self.assertRaisesRegex(ValueError, "disagrees"):
            extract_champion(data, "source")

    def test_regular_season_pairing_cannot_substitute_for_final(self):
        data = fixture(); data["schedule"].pop()
        with self.assertRaisesRegex(ValueError, "No championship bracket"):
            extract_champion(data, "source")

    def test_unfinished_and_missing_final_scores_are_rejected(self):
        for value in (None, float("nan")):
            data = fixture(); data["schedule"][-1]["home"]["totalPoints"] = value
            with self.assertRaisesRegex(ValueError, "scores are missing"):
                extract_champion(data, "source")
        data = fixture(); data["schedule"][-1]["winner"] = "UNDECIDED"
        with self.assertRaisesRegex(ValueError, "disagrees"):
            extract_champion(data, "source")

    def test_later_championship_round_prevents_earlier_pair_being_final(self):
        data = fixture()
        later = copy.deepcopy(data["schedule"][-1]); later["matchupPeriodId"] = 18; later["away"]["teamId"] = 3
        data["schedule"].append(later)
        with self.assertRaisesRegex(ValueError, "unique championship"):
            extract_champion(data, "source")

    def test_pre_espn_champion_joins_existing_history_without_espn_fields(self):
        espn = extract_champion(fixture(), "source")
        older = {"season": 2017, "champion": {"team_name": "Early winner", "managers": ["League manager"]}}
        records = merge_league_records([espn], [older])
        self.assertEqual([entry["season"] for entry in records], [2025, 2017])
        self.assertEqual(records[1]["source"]["type"], "league")
        self.assertNotIn("final", records[1])

    def test_league_records_can_fill_an_archive_gap(self):
        records = merge_league_records([{"season": 2018, "status": "unavailable"}],
                                      [{"season": 2018, "champion": {"team_name": "League supplied champion"},
                                        "source": {"note": "From the commissioner"}}])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["champion"]["team_name"], "League supplied champion")
        self.assertEqual(records[0]["source"]["note"], "From the commissioner")

    def test_duplicate_or_incomplete_manual_seasons_fail_instead_of_overwriting(self):
        entry = {"season": 2017, "champion": {"team_name": "Early winner"}}
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            merge_league_records([], [entry, entry])
        with self.assertRaisesRegex(ValueError, "team name"):
            merge_league_records([], [{"season": 2017, "champion": {"team_name": ""}}])
        with self.assertRaisesRegex(ValueError, "completed season"):
            merge_league_records([], [{**entry, "season": 2026}])


if __name__ == "__main__":
    unittest.main()
