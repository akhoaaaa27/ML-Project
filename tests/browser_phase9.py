"""Read-only browser integration check against the running REAL_RESEARCH localhost."""

import argparse
from hashlib import sha256 as content_sha256
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

import httpx
from playwright.sync_api import expect, sync_playwright

from scripts.inference.common import sha256
from scripts.xpecta_api.prepare_frontend import REFERENCE_SHA256
from scripts.xpecta_api.settings import FRONTEND, PREPARED, PRIVATE, REAL_SHA256
from tests.browser_phase857 import PAGES, VIEWPORTS, await_page, browser_route, geometry, monitor

LOCAL = "http://127.0.0.1:8765"


def real_inputs():
    with httpx.Client(base_url=LOCAL, timeout=20, trust_env=False) as http:
        def get(path, **params):
            return http.get("/api/v1/" + path, params=params).raise_for_status().json()

        ready = get("health/ready")
        data = get("data-status")
        config = get("bootstrap")
        assert ready["status"] == "READY" and ready["mode"] == "REAL_RESEARCH"
        assert not ready["production_approved"] and not config["operator_writes_enabled"]
        assert data["database_sha256"] == REAL_SHA256
        for asset in ("app.js", "view.js", "phase9.css"):
            content = http.get("/assets/" + asset).raise_for_status().content
            assert content_sha256(content).hexdigest() == sha256(FRONTEND / asset)
        season = config["current_season"]
        fixtures = get("fixtures", season=season, upcoming=True, limit=6)["items"]
        sample = [(row, get("eligibility", fixture_key=row["canonical_fixture_key"])) for row in fixtures]
        completed = get("fixtures", season=season, status="completed", limit=1)["items"][0]
        latest = get("forecasts", limit=1)
    return config, data, sample, completed, latest["total"]


def open_custom(page, row):
    page.locator('[data-pred-mode="custom"]').click()
    page.locator("#customHome").select_option(row["home_team"])
    page.locator("#customAway").select_option(row["away_team"])
    page.locator("#runPrediction").click()


def predictions(page, sample, completed, output, viewport):
    status = page.locator("#predictionOutput [data-readiness]")
    values = page.locator("#predictionOutput [data-xg]")
    blocked = page.locator("#predictionOutput .forecast-placeholder")
    checked = {}
    for expected in ("READY", "EARLY_READY", "WAITING_DATA"):
        selected = next(((row, verdict) for row, verdict in sample if verdict["eligibility_status"] == expected), None)
        if selected is None:
            continue
        row, verdict = selected
        page.locator('[data-pred-mode="fixture"]').click()
        page.locator(f'#presetFixtures [data-fixture="{row["canonical_fixture_key"]}"]').click()
        expect(status).to_have_text(expected.replace("_", " "))
        if expected == "WAITING_DATA":
            expect(values).to_have_count(0)
            expect(blocked).to_have_count(2)
            expect(page.locator("#predictionOutput [role=alert]")).to_have_text(verdict["reason"].replace("_", " "))
        else:
            expect(values).to_have_count(2)
            expect(page.locator("#predictionOutput")).to_contain_text("PREDICTED xG COMPARISON")
        page.locator("#predictionOutput").screenshot(path=str(output/f"{viewport}-{expected.lower()}.png"), animations="disabled")
        checked[expected] = row["canonical_fixture_key"]
    open_custom(page, completed)
    expect(status).to_have_text("UNAVAILABLE")
    expect(values).to_have_count(0)
    expect(blocked).to_have_count(2)
    page.locator("#predictionOutput").screenshot(path=str(output/f"{viewport}-unavailable.png"), animations="disabled")
    checked["UNAVAILABLE"] = completed["canonical_fixture_key"]
    return checked


def historical_controls(page, base_url):
    page.goto(base_url + "/#analysis")
    await_page(page, "analysis")
    page.locator("#analysisSeason").select_option("2025")
    page.locator("#analysisHome").select_option("Valencia")
    page.locator("#analysisAway").select_option("Real Madrid")
    page.locator("#analysisWindow").select_option("10")

    def selected_analysis(response):
        url = urlsplit(response.url)
        return url.path == "/api/v1/historical/match-analysis" and parse_qs(url.query) == {
            "home": ["Valencia"], "away": ["Real Madrid"], "season": ["2025"], "window": ["10"],
        }

    with page.expect_response(selected_analysis) as pending:
        page.locator("#analysisRefresh").click()
    assert pending.value.ok
    expect(page.locator("#analysisOutput")).to_contain_text("Valencia")
    expect(page.locator("#analysisOutput")).to_contain_text("LAST 10")
    page.goto(base_url + "/#stats")
    await_page(page, "stats")
    page.locator("#statsSeason").select_option("2025")
    page.locator("#statsTeam").select_option("Valencia")
    page.locator("#statsRefresh").click()
    expect(page.locator("#statsOutput .section-title").first).to_have_text("VALENCIA")
    expect(page.locator("#statsOutput .metric-grid").first).to_be_visible()


def run(run_id):
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,60}", run_id):
        raise ValueError("Use a short local run ID")
    config, data, sample, completed, ledger_count = real_inputs()
    reference = PREPARED / "reference.html"
    assert sha256(reference) == REFERENCE_SHA256
    output = PRIVATE.parent / "phase9" / "visual" / run_id
    output.mkdir(parents=True, exist_ok=False)
    issues, results, writes = [], {}, []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True, args=["--disable-background-networking"])
        version = browser.version
        for viewport, (w, h) in VIEWPORTS.items():
            context = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1, timezone_id="UTC",
                                          locale="en-GB", reduced_motion="reduce")
            context.route("**/*", browser_route)
            original, live = context.new_page(), context.new_page()
            monitor(live, issues)
            live.on("request", lambda request: writes.append(request.url)
                    if request.url.endswith("/api/v1/forecasts/publish") else None)
            for name in PAGES:
                original.goto(reference.as_uri() + "#" + name)
                live.goto(LOCAL + "/#" + name)
                await_page(original, name)
                if name == "history" and not ledger_count:
                    expect(live.get_by_role("heading", name="No published forecasts yet")).to_be_visible()
                elif name == "predict" and not sample:
                    expect(live.locator("#presetFixtures .empty")).to_be_visible()
                else:
                    await_page(live, name)
                expect(live.locator("#bridgeModeText")).to_have_text("REAL RESEARCH")
                assert live.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
                if name == "analysis":
                    expect(live.locator(".analysis-insights-card")).to_be_visible()
                    expect(live.locator(".analysis-insights-card [data-to-custom]")).to_be_visible()
                if name == "stats":
                    expect(live.locator("[data-team-comparison] .crest")).to_have_count(2)
                if name == "model":
                    expect(live.locator("#featuresList code")).to_have_count(13)
                    expect(live.locator("#modelMetricCards")).to_contain_text("2024-08-15 to 2025-05-25")
                for page in (original, live):
                    page.wait_for_load_state("networkidle")
                    page.evaluate("document.fonts.ready")
                    page.evaluate("scrollTo(0, 0)")
                before, after = geometry(original), geometry(live)
                assert abs(before["height"]-after["height"]) <= 2 and before["width"] == after["width"]
                assert before["background"] == after["background"] and before["filter"] == after["filter"]
                for side, page in (("reference", original), ("real", live)):
                    # The real catalogue can have hundreds of fixtures; preserve a comparable viewport.
                    page.screenshot(path=str(output/f"{viewport}-{name}-{side}.png"), animations="disabled")
            if viewport != "desktop":
                live.locator("#mobileToggle").click()
                expect(live.locator("#mobileToggle")).to_have_attribute("aria-expanded", "true")
                live.locator('#mobileMenu [data-page="predict"]').click()
                expect(live.locator("#mobileToggle")).to_have_attribute("aria-expanded", "false")
            else:
                live.locator('.nav-links [data-page="predict"]').click()
            results[viewport] = predictions(live, sample, completed, output, viewport)
            historical_controls(live, LOCAL)
            context.close()
        browser.close()
    assert not issues, issues
    assert not writes, writes
    with httpx.Client(base_url=LOCAL, timeout=20, trust_env=False) as http:
        assert http.get("/api/v1/forecasts?limit=1").raise_for_status().json()["total"] == ledger_count
    summary = dict(mode=config["mode"],snapshot=config["snapshot_version"],browser=version,viewports=VIEWPORTS,
                   page_pairs=len(VIEWPORTS)*len(PAGES),states=results,console_errors=issues,ledger_count=ledger_count,
                   historical_controls_checked=list(VIEWPORTS), publish_requests=len(writes),
                   schedule_freshness=data["schedule_freshness"],eligible_fixture_in_first_six=any(
                       verdict["eligibility_status"] in ("READY","EARLY_READY") for _,verdict in sample))
    (output/"evidence.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    print(json.dumps(run(parser.parse_args().run_id),indent=2))
