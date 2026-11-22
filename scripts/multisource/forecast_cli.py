"""Local research CLI with snapshot version identifiers and the actual UTC clock."""

import argparse

from scripts.inference.common import InferenceError
from .composite_history import dumps
from .forecast_service import ForecastService


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command",required=True)
    for name in ("eligibility","generate","list-fixtures","data-status"):
        command = commands.add_parser(name)
        command.add_argument("--snapshot",required=True)
        if name in ("eligibility","generate"):
            command.add_argument("--fixture",required=True)
        if name == "list-fixtures":
            command.add_argument("--season",type=int)
            command.add_argument("--include-unavailable",action="store_true")
    commands.add_parser("get").add_argument("forecast_id")
    commands.add_parser("list-forecasts").add_argument("--fixture",required=True)
    compare = commands.add_parser("compare")
    compare.add_argument("--fixture",required=True)
    compare.add_argument("first")
    compare.add_argument("second")
    args = parser.parse_args(argv)
    service = ForecastService()
    try:
        if args.command == "eligibility":
            result = service.evaluate_forecast_eligibility(args.fixture,args.snapshot)
        elif args.command == "generate":
            result = service.generate_forecast(args.fixture,args.snapshot)
        elif args.command == "list-fixtures":
            result = service.list_eligible_fixtures(args.snapshot,season=args.season,
                                                    include_unavailable=args.include_unavailable)
        elif args.command == "data-status":
            result = service.get_forecast_data_status(args.snapshot)
        elif args.command == "get":
            result = service.get_forecast(args.forecast_id)
        elif args.command == "list-forecasts":
            result = service.list_fixture_forecasts(args.fixture)
        else:
            result = service.compare_forecasts(args.fixture,args.first,args.second)
    except InferenceError as exc:
        print(dumps(dict(status="FORECAST_ERROR", error=exc.code)))
        return 1
    except (OSError, ValueError, KeyError, TypeError):
        print(dumps(dict(status="FORECAST_ERROR", error="LOCAL_DATA_UNAVAILABLE")))
        return 1
    print(dumps(result))
    return int(isinstance(result,dict) and result.get("status") in {"WAITING_DATA","UNAVAILABLE","FORECAST_ERROR"})


if __name__ == "__main__":
    raise SystemExit(main())
