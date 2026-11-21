"""HTTP/budget/security tests dùng mock; không dùng key thật hoặc credits."""

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import requests

from scripts.data_provider.strikerapi_client import StrikerAPIClient,POCError,load_credentials,sanitize,safe_credit_headers
from strikerapi_fixtures import TEST_CREDENTIAL,listing_fixture,mock_response,session_fixture

PARAMS=dict(league="laliga",season=2023,date="2023-10-28",timezone="Europe/Madrid",limit=20,status="final")


class StrikerAPIClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        (self.root/".env").write_text("STRIKERAPI_API_KEY="+TEST_CREDENTIAL+"\n",encoding="utf-8")
        self.env=patch.dict(os.environ,{},clear=False);self.env.start()
        os.environ.pop("STRIKERAPI_API_KEY",None)
        self.session=session_fixture();self.logs=[]

    def tearDown(self):self.env.stop();self.tmp.cleanup()

    def client(self,**kwargs):
        return StrikerAPIClient(root=self.root,output_dir=self.root/"outputs",session=self.session,logger=self.logs.append,**kwargs)

    def test_dotenv_loaded_without_disclosure_or_mutation(self):
        original=(self.root/".env").read_bytes()
        self.assertEqual(load_credentials(self.root),TEST_CREDENTIAL)
        client=self.client(execute=True);record=client.call("list_games",PARAMS)
        self.assertEqual(original,(self.root/".env").read_bytes())
        self.assertNotIn(TEST_CREDENTIAL,repr(client)+json.dumps(record)+json.dumps(self.logs))
        self.assertEqual(self.session.post.call_args.kwargs["headers"]["x-api-key"],TEST_CREDENTIAL)

    def test_missing_key_no_network(self):
        (self.root/".env").write_text("STRIKERAPI_API_KEY=\n")
        with self.assertRaises(POCError) as error:self.client(execute=True).call("list_games",PARAMS)
        self.assertEqual(error.exception.code,"MISSING_CREDENTIAL")
        self.session.get.assert_not_called();self.session.post.assert_not_called()

    def test_dry_run_never_calls_network(self):
        result=self.client().call("list_games",PARAMS)
        self.assertEqual(result["status"],"dry_run")
        self.session.get.assert_not_called();self.session.post.assert_not_called()
        self.assertFalse((self.root/"outputs/raw/credit_ledger.sqlite3").exists())

    def test_public_schema_gets_carry_no_auth(self):
        self.client(execute=True).call("list_games",PARAMS)
        self.assertEqual(self.session.get.call_count,2)
        for call in self.session.get.call_args_list:
            self.assertNotIn("headers",call.kwargs)
            self.assertFalse(call.kwargs["allow_redirects"])

    def test_http_errors_are_distinct_and_never_retried(self):
        for status,code in [(400,"PROVIDER_BAD_REQUEST"),(401,"PROVIDER_AUTH_FAILED"),(402,"PROVIDER_INSUFFICIENT_CREDITS"),
                            (403,"PROVIDER_FORBIDDEN"),(429,"PROVIDER_RATE_LIMIT"),(503,"PROVIDER_SERVER_ERROR")]:
            with self.subTest(status=status),tempfile.TemporaryDirectory() as directory:
                session=session_fixture(status=status)
                client=StrikerAPIClient(root=self.root,output_dir=directory,session=session,execute=True,logger=self.logs.append)
                with self.assertRaises(POCError) as error:client.call("list_games",PARAMS)
                self.assertEqual(error.exception.code,code);self.assertEqual(error.exception.http_status,status)
                self.assertEqual(session.post.call_count,1)
                self.assertEqual(client.spent(),2)  # Không giả định refund đã xảy ra.

    def test_timeout_redacts_exception_and_reserves_uncertain_charge(self):
        self.session.post.side_effect=requests.Timeout("unsafe echo "+TEST_CREDENTIAL)
        client=self.client(execute=True)
        with self.assertRaises(POCError) as error:client.call("list_games",PARAMS)
        self.assertEqual(error.exception.code,"TRANSPORT_ERROR")
        self.assertNotIn(TEST_CREDENTIAL,str(error.exception))
        with self.assertRaises(POCError) as again:client.call("list_games",PARAMS)
        self.assertEqual(again.exception.code,"PREVIOUS_ATTEMPT_UNRESOLVED")
        self.assertEqual(self.session.post.call_count,1)

    def test_invalid_json_rejected_without_error_body_logging(self):
        self.session.post.return_value.json.side_effect=ValueError(TEST_CREDENTIAL)
        with self.assertRaises(POCError) as error:self.client(execute=True).call("list_games",PARAMS)
        self.assertEqual(error.exception.code,"INVALID_JSON")
        self.assertNotIn(TEST_CREDENTIAL,str(error.exception))

    def test_data_wrapper_required_and_unexpected_response_schema_rejected(self):
        self.session.post.return_value=mock_response(listing_fixture())
        with self.assertRaises(POCError) as error:self.client(execute=True).call("list_games",PARAMS)
        self.assertEqual(error.exception.code,"SCHEMA_MISMATCH")

    def test_budget_refuses_before_network(self):
        with self.assertRaises(POCError) as error:self.client(execute=True,max_credits=1).call("list_games",PARAMS)
        self.assertEqual(error.exception.code,"BUDGET_EXCEEDED")
        self.session.get.assert_not_called();self.session.post.assert_not_called()

    def test_cumulative_budget_persists_across_clients(self):
        client=self.client(execute=True,max_credits=2);client.call("list_games",PARAMS)
        second=self.client(execute=True,max_credits=2)
        with self.assertRaises(POCError) as error:second.call("list_games",dict(PARAMS,date="2023-10-29"))
        self.assertEqual(error.exception.code,"BUDGET_EXCEEDED")
        self.assertEqual(self.session.post.call_count,1)

    def test_cache_avoids_all_duplicate_network_calls(self):
        first=self.client(execute=True).call("list_games",PARAMS)
        second=self.client(execute=True,max_credits=0).call("list_games",PARAMS)
        self.assertFalse(first["cache_hit"]);self.assertTrue(second["cache_hit"])
        self.assertEqual(self.session.post.call_count,1)

    def test_corrupt_cache_does_not_trigger_paid_retry(self):
        client=self.client(execute=True);client.call("list_games",PARAMS)
        path=next((self.root/"outputs/raw").glob("*.json"));path.write_text("{}")
        with self.assertRaises(POCError) as error:client.call("list_games",PARAMS)
        self.assertEqual(error.exception.code,"CACHE_CORRUPT");self.assertEqual(self.session.post.call_count,1)

    def test_league_and_extra_request_parameters_rejected(self):
        for params in [dict(PARAMS,league="soccer"),dict(PARAMS,secret="not-a-real-secret")]:
            with self.assertRaises(POCError):self.client(execute=True).call("list_games",params)
        self.session.post.assert_not_called()

    def test_contract_or_cost_drift_stops_before_paid_request(self):
        first=list(self.session.get.side_effect)
        self.session.get.side_effect=first
        tools=first[0].json.return_value
        tools["tools"][0]["credits"]=999
        with self.assertRaises(POCError) as error:self.client(execute=True).call("list_games",PARAMS)
        self.assertEqual(error.exception.code,"SCHEMA_DRIFT");self.session.post.assert_not_called()

    def test_public_schema_unavailable_stops_before_paid_request(self):
        self.session.get.side_effect=requests.ConnectionError(TEST_CREDENTIAL)
        with self.assertRaises(POCError) as error:self.client(execute=True).call("list_games",PARAMS)
        self.assertEqual(error.exception.code,"PUBLIC_SCHEMA_UNAVAILABLE")
        self.assertNotIn(TEST_CREDENTIAL,str(error.exception));self.session.post.assert_not_called()

    def test_credit_header_whitelist_and_response_redaction(self):
        payload=listing_fixture();payload["note"]="unsafe "+TEST_CREDENTIAL
        self.session.post.return_value=mock_response({"data":payload},headers={"x-credits-remaining":"400","x-api-key":TEST_CREDENTIAL,"credit-debug":TEST_CREDENTIAL})
        result=self.client(execute=True).call("list_games",PARAMS)
        self.assertEqual(result["credit_headers"],{"x-credits-remaining":"400"})
        self.assertNotIn(TEST_CREDENTIAL,json.dumps(result))
        self.assertNotIn(TEST_CREDENTIAL,"".join(p.read_text() for p in (self.root/"outputs/raw").glob("*.json")))

    def test_budget_above_25_and_invalid_limits_rejected(self):
        for budget in [26,-1,1.5,True]:
            with self.assertRaises(POCError):self.client(max_credits=budget)

    def test_unreadable_credit_ledger_stops_before_network(self):
        client=self.client(execute=True)
        client.ledger_path.parent.mkdir(parents=True)
        client.ledger_path.write_bytes(b"not-a-sqlite-database")
        with self.assertRaises(POCError) as error:client.call("list_games",PARAMS)
        self.assertEqual(error.exception.code,"BUDGET_UNVERIFIABLE")
        self.session.get.assert_not_called();self.session.post.assert_not_called()


if __name__=="__main__":unittest.main()
