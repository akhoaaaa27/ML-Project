"""Kiểm tra môi trường và dry-run; chỉ --execute mới gọi list_games tính credits."""

import argparse
from pathlib import Path
import subprocess

from dotenv import dotenv_values

from scripts.inference.common import ROOT,write_json
from .sample_selector import select_reference,discovery_params
from .strikerapi_client import BASE_URL,POC_DIR,StrikerAPIClient,load_credentials,run_cli


def environment_report(root=ROOT):
    root=Path(root)
    key=load_credentials(root)
    example=root/".env.example"
    sample=dotenv_values(example,interpolate=False) if example.is_file() else {}
    ignored=subprocess.run(["git","check-ignore","-q","--",".env"],cwd=root,capture_output=True).returncode==0
    tracked=bool(subprocess.check_output(["git","ls-files","--",".env"],cwd=root).strip())
    return dict(repository_root_found=(root/"data/laliga_processed_normalized.csv").is_file(),
        dotenv_exists=(root/".env").is_file(),credential_present=key is not None,private_dotenv_ignored=ignored,
        private_dotenv_tracked=tracked,env_example_safe=sample=={"STRIKERAPI_API_KEY":""},
        base_url=BASE_URL,credential_value_or_auth_headers_recorded=False)


def connection_check(*,execute=False,max_credits=25,output_dir=POC_DIR):
    reference=select_reference()
    client=StrikerAPIClient(execute=execute,max_credits=max_credits,output_dir=output_dir)
    report=dict(status="dry_run" if not execute else "not_connected",environment=environment_report(),
        execute=execute,max_credits=max_credits,reference=reference,params=discovery_params(reference))
    response=client.call("list_games",report["params"])
    if execute:
        report.update(status="connected",http_status=response["http_status"],cache_hit=response["cache_hit"],
            fetched_at=response["fetched_at"],credit_headers=response["credit_headers"],
            returned_games=response["data"]["count"],compatibility_established=False)
    else:report["plan"]=response["plan"]
    report.update(billable_posts_this_run=client.billable_posts,public_schema_gets_this_run=client.public_schema_gets,
                  cumulative_conservative_reserved_credits=client.spent())
    write_json(Path(output_dir)/"reports/connection_report.json",report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute",action="store_true")
    parser.add_argument("--max-credits",type=int,default=25)
    args=parser.parse_args()
    return run_cli(lambda:connection_check(execute=args.execute,max_credits=args.max_credits))


if __name__=="__main__":raise SystemExit(main())
