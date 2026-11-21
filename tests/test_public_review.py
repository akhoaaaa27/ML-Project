"""Allowlist publication tests: payload/headers/keys/numerical provider data không được lọt ra."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.data_provider.export_public_review import build_public_review,export_review,markdown_review

MOCK_SECRET="mock-private-key-never-publish"
PRIVATE_VALUE=987654.321987


def success_evidence():
    return dict(live_command_executed=True,authentication_succeeded=True,fixture_matched=True,
        get_game_succeeded=True,both_team_perspectives=True,normalization_succeeded=True,
        availability=dict(xg="available_both_teams",xga="derived_from_validated_opponent_xg",goals="available_both_teams",sh="available_both_teams",sot="available_both_teams"),
        xg_source="get_game.published_team_stats.xg",shot_map_called=False,shot_map_required=False,
        comparison_executed=True,principal_blocker="SINGLE_FIXTURE_INSUFFICIENT",missing_fields=[],
        validation_codes=["AUTHENTICATION_CONFIRMED","FIXTURE_MATCH_CONFIRMED","NORMALIZATION_SUCCEEDED","COMPARISON_COMPLETED"],
        calls=[dict(tool="list_games",cost=2,http_status=200,headers={"x-api-key":MOCK_SECRET}),
               dict(tool="get_game",cost=5,http_status=200,raw_response={"xg":PRIVATE_VALUE})],
        cumulative_reserved_credits=7,actual_billed_credits=7,
        api_key=MOCK_SECRET,private_raw_data={"shots":[PRIVATE_VALUE],"provider_match_id":"private-match-id"},
        compatibility_summary={"xg_mean_absolute_difference":PRIVATE_VALUE},production_approved=True)


def context():
    return dict(starting_commit="a"*40,started_at="2026-11-21T00:00:00+00:00",execution_completed_at="2026-11-21T00:01:00+00:00",
        tests=dict(run=160,failures=0,errors=0,skipped=0),protected_research_files_unchanged=True,
        model_and_history_unchanged=True,private_dotenv_ignored_and_untracked=True,
        private_dotenv_sha256=MOCK_SECRET,unrelated_secret=MOCK_SECRET)


class PublicReviewTests(unittest.TestCase):
    def assert_private_absent(self,review):
        serialized=json.dumps(review,ensure_ascii=False)+markdown_review(review)
        for item in [MOCK_SECRET,str(PRIVATE_VALUE),"private-match-id","x-api-key","xg_mean_absolute_difference","private_raw_data"]:
            self.assertNotIn(item,serialized)

    def test_success_exports_status_resource_usage_and_no_private_payload(self):
        review=build_public_review(success_evidence(),context())
        self.assertTrue(review["authentication_succeeded"])
        self.assertEqual(review["api_calls_attempted_or_reserved"],2)
        self.assertEqual(review["cumulative_reserved_credits"],7)
        self.assertFalse(review["production_approved"])
        self.assert_private_absent(review)

    def test_billing_headers_or_private_billing_number_are_not_treated_as_proof(self):
        data=success_evidence();data["credit_headers"]={"x-credits-used":PRIVATE_VALUE}
        review=build_public_review(data,context())
        self.assertIsNone(review["actual_billed_credits"])
        self.assertFalse(review["actual_billed_credits_reliably_confirmed"])
        self.assert_private_absent(review)

    def test_failure_report_remains_safe_and_does_not_invent_success(self):
        data=dict(live_command_executed=True,authentication_succeeded=False,
            calls=[dict(tool="list_games",http_status=401)],cumulative_reserved_credits=2,
            validation_codes=["PROVIDER_AUTH_FAILED"],principal_blocker="PROVIDER_AUTH_FAILED",message=MOCK_SECRET)
        review=build_public_review(data,context())
        self.assertFalse(review["authentication_succeeded"])
        self.assertIsNone(review["normalization_succeeded"])
        self.assertEqual(review["principal_compatibility_blocker"],"PROVIDER_AUTH_FAILED")
        self.assert_private_absent(review)

    def test_no_response_leaves_authentication_unverified(self):
        review=build_public_review(dict(live_command_executed=True,calls=[],validation_codes=["PUBLIC_SCHEMA_UNAVAILABLE"]),context())
        self.assertIsNone(review["authentication_succeeded"])
        self.assertFalse(review["billable_request_attempted"])
        self.assertEqual(review["api_calls_attempted_or_reserved"],0)

    def test_unknown_strings_in_allowed_positions_cannot_smuggle_secrets(self):
        data=success_evidence()
        data.update(authentication_succeeded=MOCK_SECRET,normalization_succeeded=MOCK_SECRET,
            xg_source=MOCK_SECRET,principal_blocker=MOCK_SECRET,validation_codes=[MOCK_SECRET],missing_fields=[MOCK_SECRET])
        data["availability"]["xg"]=MOCK_SECRET
        data["calls"].append(dict(tool=MOCK_SECRET,http_status=200))
        review=build_public_review(data,context())
        self.assertIsNone(review["authentication_succeeded"])
        self.assertEqual(review["field_availability"]["xg"],"not_verified")
        self.assertEqual(review["validation_codes"],["UNRECOGNIZED_VALIDATION_CODE"])
        self.assert_private_absent(review)

    def test_nested_wrong_types_are_not_copied(self):
        data=success_evidence();data.update(xg_source={"secret":MOCK_SECRET},missing_fields=None)
        data["availability"]["xg"]={"secret":MOCK_SECRET};data["calls"].append(dict(tool={"secret":MOCK_SECRET}))
        review=build_public_review(data,context())
        self.assertEqual(review["xg_source"],"not_verified")
        self.assert_private_absent(review)

    def test_context_metadata_is_validated_and_provider_branch_is_ignored(self):
        data=success_evidence();data["branch"]=MOCK_SECRET
        meta=context();meta.update(starting_commit=MOCK_SECRET,started_at=MOCK_SECRET,execution_completed_at=MOCK_SECRET)
        review=build_public_review(data,meta)
        self.assertIsNone(review["source_commit"])
        self.assertIsNone(review["execution_started_at_utc"])
        self.assertEqual(review["branch"],"phase8.5.1-strikerapi-live-audit")
        self.assert_private_absent(review)

    def test_missing_fields_only_publish_known_schema_identifiers(self):
        data=success_evidence();data["missing_fields"]=["home.xg",MOCK_SECRET,"away.shots_on_target"]
        review=build_public_review(data,context())
        self.assertEqual(set(review["missing_fields"]),{"home.xg","away.shots_on_target"})
        self.assert_private_absent(review)

    def test_more_than_one_controlled_attempt_requires_review(self):
        data=success_evidence();data["calls"]*=2
        with self.assertRaises(ValueError):build_public_review(data,context())

    def test_files_are_created_from_allowlisted_projection_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/"private.json").write_text(json.dumps(success_evidence()))
            (root/"context.json").write_text(json.dumps(context()))
            result=export_review(root/"private.json",root/"context.json",json_path=root/"public.json",markdown_path=root/"public.md")
            self.assertEqual(json.loads((root/"public.json").read_text(encoding="utf-8")),result)
            self.assert_private_absent(result)
            self.assertNotIn(MOCK_SECRET,(root/"public.md").read_text(encoding="utf-8"))


if __name__=="__main__":unittest.main()
