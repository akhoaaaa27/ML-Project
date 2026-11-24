"""Same-origin XPECTA FastAPI application."""

from contextlib import asynccontextmanager
import logging
import re
import secrets
from typing import Annotated

from anyio import CapacityLimiter, to_thread
from fastapi import APIRouter, Depends, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException
from starlette.responses import FileResponse, JSONResponse

from scripts.inference.common import InferenceError

from . import schemas as s
from .services import ResearchService
from .settings import APP_VERSION, FRONTEND, PREPARED, Settings

log = logging.getLogger(__name__)
HOST = re.compile(r"(?:localhost|127\.0\.0\.1)(?::[0-9]{1,5})?", re.IGNORECASE)
CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
       "frame-ancestors 'none'; form-action 'none'; base-uri 'none'")
BODY_LIMIT = 2048

ERRORS = {
    "INVALID_REQUEST": (422, "Request fields or parameters are invalid"),
    "INVALID_HOST": (400, "Use the configured service address"),
    "REQUEST_TOO_LARGE": (413, "Request exceeds the configured size limit"),
    "INVALID_CONTENT_TYPE": (415, "Use application/json"),
    "CROSS_ORIGIN_WRITE": (403, "This origin cannot publish forecasts"),
    "OPERATOR_REQUIRED": (401, "An authorized local operator is required"),
    "PUBLICATION_DISABLED": (403, "Forecast publication is disabled"),
    "TEAM_NOT_FOUND": (404, "Team is absent from the selected snapshot"),
    "FIXTURE_NOT_FOUND": (404, "Fixture is absent from the selected snapshot"),
    "FORECAST_NOT_FOUND": (404, "Forecast is absent from this namespace"),
    "SEASON_NOT_FOUND": (404, "Season is absent from the selected snapshot"),
    "INVALID_MATCHUP": (422, "Select two different canonical teams"),
    "INVALID_SIMULATION_TEAMS": (422, "Select two different teams to simulate."),
    "SIMULATION_INSUFFICIENT_DATA": (422, "Insufficient verified historical data for this simulation."),
    "INCOMPATIBLE_FORECASTS": (422, "Choose two revisions of the same fixture in lineage order"),
    "HISTORICAL_ONLY": (409, "Historical reference does not provide forecast publication"),
    "LEDGER_BUSY": (409, "A local operator is already writing the ledger"),
    "STALE_FORECAST_WRITE": (409, "The latest forecast changed. Reload before retrying"),
    "STALE_FORECAST_SNAPSHOT": (409, "Use the published snapshot or its verified successor"),
    "PREVIEW_BINDING_CHANGED": (409, "The forecast inputs changed. Review a new preview before publishing"),
    "SNAPSHOT_BINDING_MISMATCH": (409, "The forecast snapshot lineage could not be verified"),
    "STORAGE_UNAVAILABLE": (503, "Local forecast storage is unavailable"),
    "SERVICE_NOT_READY": (503, "Trusted model or history is unavailable"),
    "FRONTEND_UNAVAILABLE": (503, "Prepare the supplied V9.12 HTML before opening the demo"),
    "NOT_FOUND": (404, "Route not found"),
    "METHOD_NOT_ALLOWED": (405, "HTTP method not allowed"),
    "INTERNAL_ERROR": (500, "The local service could not complete the request"),
}


def error_response(code):
    status, message = ERRORS.get(code, ERRORS["SERVICE_NOT_READY"])
    payload = s.ErrorEnvelope(error=s.ErrorDetail(code=code if code in ERRORS else "SERVICE_NOT_READY",
                                                  message=message))
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return JSONResponse(payload.model_dump(), status_code=status, headers=headers)


class LocalBoundary:
    """Restrict request hosts and bound request bodies before JSON parsing."""

    def __init__(self, app, render_hostname):
        self.app = app
        self.render_hostname = render_hostname.lower()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def hardened_send(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Referrer-Policy"] = "no-referrer"
                headers["Content-Security-Policy"] = CSP
                headers["Cache-Control"] = "no-store"
            await send(message)

        headers = Headers(scope=scope)
        host = headers.get("host", "").lower()
        if not host or (host != self.render_hostname and not HOST.fullmatch(host)):
            await error_response("INVALID_HOST")(scope, receive, hardened_send)
            return
        if len(scope["query_string"]) > BODY_LIMIT:
            await error_response("REQUEST_TOO_LARGE")(scope, receive, hardened_send)
            return
        if scope["method"] == "POST" and scope["path"].startswith("/api/"):
            if headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
                await error_response("INVALID_CONTENT_TYPE")(scope, receive, hardened_send)
                return
            content = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                if len(content) + len(chunk) > BODY_LIMIT:
                    await error_response("REQUEST_TOO_LARGE")(scope, receive, hardened_send)
                    return
                content.extend(chunk)
                if not message.get("more_body", False):
                    break

            async def replay_body():
                nonlocal content
                if content is not None:
                    body, content = bytes(content), None
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            await self.app(scope, replay_body, hardened_send)
            return
        await self.app(scope, receive, hardened_send)


def get_service(request: Request):
    service = request.app.state.service
    if service is None:
        raise InferenceError("SERVICE_NOT_READY", "Trusted startup verification failed")
    return service


def require_operator(request: Request):
    settings = request.app.state.settings
    origin = request.headers.get("origin")
    same_origin = f"{request.url.scheme}://{request.headers['host']}"
    if (origin is not None and origin not in (same_origin, *settings.origins)
            or origin is None and request.headers.get("sec-fetch-site") == "cross-site"):
        raise InferenceError("CROSS_ORIGIN_WRITE", "Disallowed browser origin")
    if not settings.operator_token:
        raise InferenceError("PUBLICATION_DISABLED", "Operator writes disabled")
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(value.encode(), settings.operator_token.encode()):
        raise InferenceError("OPERATOR_REQUIRED", "Operator authorization required")


Service = Annotated[ResearchService, Depends(get_service)]
router = APIRouter(prefix="/api/v1", responses={400: {"model": s.ErrorEnvelope}, 422: {"model": s.ErrorEnvelope},
                                                503: {"model": s.ErrorEnvelope}})


@router.get("/health/live")
def live() -> s.Live:
    return s.Live(api_version=APP_VERSION)


@router.get("/health/ready")
def ready(request: Request, response: Response) -> s.Ready:
    service = request.app.state.service
    settings = request.app.state.settings
    frontend_available = frontend_file(settings).is_file()
    reason = "TRUSTED_INPUT_UNAVAILABLE" if service is None else None
    if service is not None:
        try:
            service._verify_bound_snapshot()
        except (InferenceError, OSError):
            reason = "TRUSTED_INPUT_CHANGED"
    if reason is None and settings.render_hostname and not frontend_available:
        reason = "FRONTEND_UNAVAILABLE"
    if reason:
        response.status_code = 503
    return s.Ready(status="UNAVAILABLE" if reason else "READY", mode=settings.mode,
                   snapshot_version=settings.snapshot_version,
                   model_version=service.metadata["model_version"] if not reason else None,
                   reason=reason,
                   frontend_available=frontend_available)


@router.get("/bootstrap")
def bootstrap(service: Service) -> s.Bootstrap:
    return service.bootstrap()


@router.get("/teams")
def teams(query: Annotated[s.TeamQuery, Query()], service: Service) -> s.Page[s.Team]:
    return service.list_teams(query)


@router.get("/fixtures")
def fixtures(query: Annotated[s.FixtureQuery, Query()], service: Service) -> s.Page[s.Fixture]:
    return service.list_fixtures(query)


@router.get("/eligibility")
async def eligibility(query: Annotated[s.KeyQuery, Query()], service: Service, request: Request) -> s.Eligibility:
    return await to_thread.run_sync(service.eligibility, query.fixture_key, limiter=request.app.state.forecast_slots)


@router.get("/data-status")
def data_status(service: Service) -> s.DataStatus:
    return service.data_status()


@router.post("/forecasts/preview")
async def preview(body: s.ForecastRequest, service: Service, request: Request) -> s.ForecastAction:
    return await to_thread.run_sync(service.preview, body.fixture_key, limiter=request.app.state.forecast_slots)


@router.post("/simulations")
async def simulate(body: s.SimulationRequest, service: Service, request: Request) -> s.Simulation:
    return await to_thread.run_sync(service.simulate, body.home, body.away, limiter=request.app.state.forecast_slots)


@router.post("/forecasts/publish", dependencies=[Depends(require_operator)], responses={
    401: {"model": s.ErrorEnvelope}, 403: {"model": s.ErrorEnvelope}, 409: {"model": s.ErrorEnvelope},
})
def publish(body: s.PublishRequest, service: Service) -> s.ForecastAction:
    return service.publish(body.fixture_key, body.expected)


@router.get("/forecasts")
def forecasts(query: Annotated[s.ForecastQuery, Query()], service: Service) -> s.Page[s.PublishedForecast]:
    return service.published(query)


@router.get("/forecasts/compare")
def compare(query: Annotated[s.CompareQuery, Query()], service: Service) -> s.Comparison:
    return service.compare(query)


@router.get("/forecasts/{forecast_id}")
def forecast(forecast_id: s.ForecastId, service: Service) -> s.PublishedForecast:
    return service.get_published(forecast_id)


@router.get("/historical/team-stats")
def team_stats(query: Annotated[s.TeamStatsQuery, Query()], service: Service) -> s.TeamStats:
    return service.team_stats(query.team, query.season)


@router.get("/historical/season-leaderboard")
def season_leaderboard(query: Annotated[s.SeasonQuery, Query()], service: Service) -> s.SeasonLeaderboard:
    return service.season_leaderboard(query.season)


@router.get("/historical/match-analysis")
def match_analysis(query: Annotated[s.AnalysisQuery, Query()], service: Service) -> s.MatchAnalysis:
    return service.match_analysis(query)


@router.get("/model/summary")
def model(service: Service) -> s.ModelSummary:
    return service.summary


def frontend_file(settings):
    local = PREPARED / "integrated.html"
    if not settings.render_hostname and local.is_file():
        return local
    return FRONTEND / "integrated.html"


def create_app(settings=None):
    settings = Settings.from_env() if settings is None else settings

    @asynccontextmanager
    async def lifespan(app):
        app.state.service = None
        app.state.forecast_slots = CapacityLimiter(2) if settings.render_hostname else None
        try:
            app.state.service = ResearchService(settings)
        except (InferenceError, OSError, ValueError, RuntimeError, KeyError, TypeError):
            log.exception("Trusted XPECTA inputs could not be opened")
        yield
        app.state.service = None

    app = FastAPI(title="XPECTA Research API", version=APP_VERSION, lifespan=lifespan,
                  docs_url=None, redoc_url=None, debug=False)
    app.state.settings = settings
    app.include_router(router)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # Pydantic input and context can contain paths or credentials supplied by callers.
        return error_response("INVALID_REQUEST")

    @app.exception_handler(InferenceError)
    async def domain_error(request, exc):
        return error_response(exc.code)

    @app.exception_handler(OSError)
    async def storage_error(request, exc):
        return error_response("STORAGE_UNAVAILABLE")

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error_response({404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "INTERNAL_ERROR"))

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        log.exception("Unexpected local XPECTA request error", exc_info=exc)
        return error_response("INTERNAL_ERROR")

    @app.get("/", include_in_schema=False)
    def frontend():
        path = frontend_file(settings)
        if not path.is_file():
            return error_response("FRONTEND_UNAVAILABLE")
        return FileResponse(path, media_type="text/html")

    assets = {
        "api.js": (FRONTEND / "api.js", "text/javascript"),
        "app.js": (FRONTEND / "app.js", "text/javascript"),
        "view.js": (FRONTEND / "view.js", "text/javascript"),
        "phase9.css": (FRONTEND / "phase9.css", "text/css"),
        "fixtures.js": (FRONTEND / "fixtures.js", "application/javascript"),
        "team-picker.js": (FRONTEND / "team-picker.js", "text/javascript"),
        "simulations.js": (FRONTEND / "simulations.js", "text/javascript"),
        "evaluation-charts.js": (FRONTEND / "evaluation-charts.js", "text/javascript"),
        "montserrat.ttf": (FRONTEND / "montserrat.ttf", "font/ttf"),
    }

    @app.get("/assets/{asset}", include_in_schema=False)
    def frontend_asset(asset: str):
        if asset not in assets or not assets[asset][0].is_file():
            return error_response("NOT_FOUND")
        path, media_type = assets[asset]
        return FileResponse(path, media_type=media_type)

    app.add_middleware(CORSMiddleware, allow_origins=list(settings.origins), allow_credentials=False,
                       allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])
    app.add_middleware(LocalBoundary, render_hostname=settings.render_hostname)
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8765, proxy_headers=False)
