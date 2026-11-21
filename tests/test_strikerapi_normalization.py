"""Adapter tests bằng dữ liệu tổng hợp, không gọi API hoặc coi mocks là bằng chứng live."""

import copy
import unittest

from scripts.data_provider.normalize_strikerapi import normalize_game
from scripts.data_provider.sample_selector import match_fixture,provider_identity,canonical_team
from scripts.data_provider.strikerapi_client import POCError
from strikerapi_fixtures import REFERENCE,game_fixture,listing_fixture,shot_fixture

FETCHED="2026-11-21T00:00:00+00:00"


class StrikerAPINormalizationTests(unittest.TestCase):
    def normalize(self,data=None,shots=None):
        return normalize_game(game_fixture() if data is None else data,REFERENCE,provider_game_id="synthetic-game",fetched_at=FETCHED,shot_map=shots)

    def test_two_consistent_perspectives_and_provenance(self):
        table,diag=self.normalize()
        self.assertEqual(len(table),2);self.assertEqual(table.is_home.tolist(),[1,0])
        self.assertEqual(table.xg.tolist(),[1.,1.5]);self.assertEqual(table.xga.tolist(),[1.5,1.])
        self.assertEqual(table.gf.tolist(),[1,2]);self.assertEqual(table.ga.tolist(),[2,1])
        self.assertTrue(table.quality_status.eq("verified").all())
        self.assertTrue(table.statistics_version.str.startswith("response_sha256:").all())
        self.assertEqual(diag["xg_source"],"get_game.published_team_stats.xg")
        self.assertFalse(diag["production_approved"])

    def test_zero_xg_is_valid_but_missing_xg_is_not_zero(self):
        game=game_fixture();game["team_stats"][0]["xg"]=0
        table,_=self.normalize(game);self.assertEqual(table.xg.iloc[0],0.)
        game["team_stats"][0]["xg"]=None
        table,diag=self.normalize(game);self.assertIsNone(table);self.assertTrue(diag["needs_shot_map"])

    def test_missing_sot_never_inferred_from_outcome_or_season_average(self):
        game=game_fixture();game["team_stats"][0].pop("shots_on_target")
        table,diag=self.normalize(game,shot_fixture())
        self.assertIsNone(table);self.assertIn("home.shots_on_target",diag["missing_fields"])
        self.assertFalse(diag["needs_shot_map"])

    def test_invalid_stats_and_shots_less_than_sot_rejected(self):
        for field,value in [("xg",float("nan")),("xg",-1),("shots",1.1),("shots_on_target",10)]:
            game=game_fixture();game["team_stats"][0][field]=value
            table,diag=self.normalize(game)
            self.assertIsNone(table);self.assertTrue(diag["invalid_fields"])

    def test_stats_must_match_verified_team_ids_and_roles(self):
        for change in ["team_id","home"]:
            game=game_fixture();game["team_stats"][0][change]="wrong" if change=="team_id" else False
            table,diag=self.normalize(game);self.assertIsNone(table);self.assertEqual(diag["error_code"],"INVALID_STATS_SCHEMA")

    def test_shot_map_sums_by_both_teams_and_not_combined_totals(self):
        game=game_fixture();game["team_stats"][0]["xg"]=None;game["team_stats"][1]["xg"]=None
        table,diag=self.normalize(game,shot_fixture())
        self.assertAlmostEqual(table.xg.iloc[0],.6);self.assertAlmostEqual(table.xg.iloc[1],.9)
        self.assertEqual(diag["xg_source"],"raw_shot_aggregation_both_teams")
        self.assertFalse(diag["shot_coverage"]["sot_inferred_from_outcome"])

    def test_unlocated_truncated_or_missing_shots_rejected(self):
        game=game_fixture();game["team_stats"][0]["xg"]=None
        for mode in ["unlocated","truncated","missing_xg","missing_record","goals_only"]:
            shots=shot_fixture()
            if mode=="unlocated":shots["unlocated_shots"]=1
            elif mode=="truncated":shots["truncated"]=True
            elif mode=="missing_xg":shots["shots"][0]["xg"]=None
            elif mode=="missing_record":shots["shots"].pop()
            else:shots["goals_only"]={"goals":3,"matches":1}
            table,diag=self.normalize(game,shots)
            self.assertIsNone(table);self.assertEqual(diag["error_code"],"INCOMPLETE_SHOTS")

    def test_duplicate_shots_or_unverified_team_rejected(self):
        game=game_fixture();game["team_stats"][0]["xg"]=None
        shots=shot_fixture();shots["shots"][1]=copy.deepcopy(shots["shots"][0])
        table,diag=self.normalize(game,shots);self.assertIsNone(table);self.assertEqual(diag["error_code"],"DUPLICATE_SHOT")
        shots=shot_fixture();shots["shots"][0]["team"]="unverified-team"
        table,diag=self.normalize(game,shots);self.assertIsNone(table);self.assertEqual(diag["error_code"],"UNVERIFIED_SHOT_TEAM")

    def test_shot_from_other_fixture_not_accepted(self):
        game=game_fixture();game["team_stats"][0]["xg"]=None
        shots=shot_fixture();shots["shots"][0]["game_id"]="another-match"
        table,diag=self.normalize(game,shots);self.assertIsNone(table);self.assertEqual(diag["error_code"],"INCOMPLETE_SHOTS")

    def test_exact_fixture_match_and_aliases(self):
        self.assertEqual(canonical_team("Atlético Madrid"),"Atletico Madrid")
        self.assertEqual(match_fixture(listing_fixture(),REFERENCE)["identity"]["provider_match_id"],"synthetic-game")
        with self.assertRaises(POCError):canonical_team("Barcelona perhaps")

    def test_wrong_fixture_dates_scores_seasons_and_teams_rejected(self):
        for mode in ["date","score","season","team"]:
            listing=listing_fixture();game=listing["games"][0]
            if mode=="date":game["date"]="2023-10-29"
            elif mode=="score":game["home"]["score"]=9
            elif mode=="season":game["season"]=2022
            else:game["home"]["name"]="Getafe"
            with self.assertRaises(POCError):match_fixture(listing,REFERENCE)

    def test_duplicate_provider_game_id_rejected(self):
        listing=listing_fixture();listing["games"]*=2;listing["count"]=2
        with self.assertRaises(POCError) as error:match_fixture(listing,REFERENCE)
        self.assertEqual(error.exception.code,"DUPLICATE_FIXTURE")

    def test_timezone_boundary_ambiguity_and_naive_kickoff_rejected(self):
        for stamp in ["2023-10-28T23:30:00Z","2023-10-28T14:00:00"]:
            game=game_fixture()["game"];game["starts_at"]=stamp
            with self.assertRaises(POCError) as error:provider_identity(game,REFERENCE)
            self.assertEqual(error.exception.code,"TIMEZONE_AMBIGUOUS")


if __name__=="__main__":unittest.main()
