"""Read-only browser integration check against the running REAL_RESEARCH localhost."""

import argparse
from datetime import datetime
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
        for asset in ("app.js", "view.js", "phase9.css", "fixtures.js"):
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
            before = values.all_text_contents()
            page.locator("#predictionOutput [data-analyze]").click()
            await_page(page, "analysis")
            expect(page.locator(".analysis-overview-card")).to_contain_text(row["home_team"])
            expect(page.locator(".analysis-overview-card")).to_contain_text(row["away_team"])
            with page.expect_request("**/api/v1/forecasts/preview") as repeat:
                page.locator(".analysis-insights-card [data-to-custom]").click()
            assert repeat.value.post_data_json == {"fixture_key": row["canonical_fixture_key"]}
            expect(status).to_have_text(expected.replace("_", " "))
            assert values.all_text_contents() == before
        page.locator("#predictionOutput").screenshot(path=str(output/f"{viewport}-{expected.lower()}.png"), animations="disabled")
        checked[expected] = row["canonical_fixture_key"]
    open_custom(page, completed)
    expect(status).to_have_text("UNAVAILABLE")
    expect(values).to_have_count(0)
    expect(blocked).to_have_count(2)
    page.locator("#predictionOutput").screenshot(path=str(output/f"{viewport}-unavailable.png"), animations="disabled")
    checked["UNAVAILABLE"] = completed["canonical_fixture_key"]
    return checked


def discovery(page, data, sample, output, viewport):
    search = page.get_by_role("searchbox", name="Search teams")
    expect(search).to_be_visible()
    cards = page.locator("#presetFixtures .fixture-card")
    buttons = page.locator("#presetFixtures [data-fixture]")
    count = page.locator("#fixtureResults")
    total = data["upcoming_fixtures"]
    expect(cards).to_have_count(min(12, total))
    expect(page.locator("#fixtureDataStatus")).not_to_contain_text("Checking schedule")
    if data["schedule_freshness"] == "VERIFIED":
        expect(page.locator("#fixtureDataStatus")).to_have_text("Recent schedule evidence")
    if total > 12:
        first = buttons.evaluate_all("(items) => items.map(item => item.dataset.fixture)")
        page.get_by_role("button", name="Next").press("Enter")
        expect(count).to_be_focused()
        expect(count).to_contain_text(f"13–{min(24, total)} of {total} matches")
        second = buttons.evaluate_all("(items) => items.map(item => item.dataset.fixture)")
        assert not set(first) & set(second)
        page.get_by_role("button", name="Previous").click()
        expect(page.locator("#fixturePage")).to_contain_text("Page 1 of")
    search.fill("no match in this catalogue")
    expect(cards).to_have_count(0)
    expect(count).to_contain_text("0 matches")
    page.get_by_role("button", name="Clear filters").click()
    expect(search).to_have_value("")
    expect(cards).to_have_count(min(12, total))
    if sample:
        row, _ = next(((row, verdict) for row, verdict in sample if row["kickoff_utc"]), sample[0])
        team = row["home_team"]
        page.get_by_role("form", name="Filter fixture catalogue").get_by_label("Team", exact=True).select_option(team)
        search.fill(" " + team.upper().replace(" ", "   ") + " ")
        candidate = page.locator(f'#presetFixtures [data-fixture="{row["canonical_fixture_key"]}"]')
        if row["kickoff_utc"]:
            day = row["kickoff_utc"][:10]
            page.get_by_label("From (UTC)").fill(day)
            page.get_by_label("Through (UTC)").fill(day)
            expect(cards).to_have_count(1)
        with page.expect_request("**/api/v1/forecasts/preview") as call:
            candidate.press("Enter")
        assert call.value.post_data_json == {"fixture_key": row["canonical_fixture_key"]}
        expect(page.locator("#predictionOutput")).to_be_focused()
        page.locator("#backToFixtures").click()
        expect(candidate).to_be_focused()
        expect(search).to_have_value(" " + team.upper().replace(" ", "   ") + " ")
        page.get_by_role("button", name="Clear filters").click()
        expect(cards).to_have_count(min(12, total))
    page.get_by_label("Catalogue status").select_option("completed")
    expect(cards.first).to_be_visible()
    expect(cards.first).to_contain_text("completed")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    page.get_by_role("button", name="Clear filters").click()
    expect(cards).to_have_count(min(12, total))
    expect(count).to_contain_text(f"of {total} matches" if total else "0 matches")
    page.evaluate("scrollTo(0, 0)")
    page.screenshot(path=str(output / f"{viewport}-fixture-discovery.png"), animations="disabled")


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


def schedule_expiry(browser, output, issues, writes):
    with browser.new_context(viewport={"width": 1440, "height": 900}, timezone_id="UTC") as context:
        context.route("**/*", browser_route)
        page = context.new_page()
        monitor(page, issues)
        page.on("request", lambda request: writes.append(request.url)
                if request.url.endswith("/api/v1/forecasts/publish") else None)
        page.clock.install()
        with page.expect_response("**/api/v1/data-status") as status:
            page.goto(LOCAL + "/#predict")
        data = status.value.json()
        label = page.locator("#fixtureDataStatus")
        gaps = [
            (datetime.fromisoformat(group["expires_at_utc"]) - datetime.fromisoformat(data["evaluated_at_utc"])).total_seconds()
            for group in data["schedule_evidence"] if group["status"] == "VALID"
        ]
        if not gaps:
            if data["expired_review_upcoming_fixtures"]:
                expect(label).to_have_text("Schedule evidence is stale")
            return "NO_VALID_GROUP_AT_ACTUAL_CHECK"
        expect(label).to_have_text("Recent schedule evidence" if data["schedule_freshness"] == "VERIFIED"
                                  else "Some fixtures lack recent schedule evidence")
        first_fixture = page.locator("#presetFixtures .fixture-card").first
        expect(first_fixture).to_be_visible()
        first_key = first_fixture.locator("[data-fixture]").get_attribute("data-fixture")
        first_kickoff = first_fixture.locator("time").get_attribute("datetime")
        boundary = max(datetime.fromisoformat(group["expires_at_utc"])
                       for group in data["schedule_evidence"] if group["status"] == "VALID")
        # Only this isolated browser view advances time. Replay the genuine initial HTTP result
        # to prove a delayed pre-expiry response cannot turn the clock-projected label fresh again.
        page.route("**/api/v1/data-status", lambda route: route.fulfill(json=data))
        with page.expect_response("**/api/v1/data-status") as replay:
            page.clock.fast_forward(round(max(gaps) * 1000) + 100)
        assert replay.value.json()["evaluated_at_utc"] == data["evaluated_at_utc"]
        expect(label).to_have_text("Schedule evidence is stale")
        if "T" in first_kickoff and datetime.fromisoformat(first_kickoff) <= boundary:
            expect(page.locator(f'#presetFixtures [data-fixture="{first_key}"]')).to_have_count(0)
        expect(page.locator("#predictionOutput [data-xg]")).to_have_count(0)
        expect(page.locator("#homeSchedule")).to_contain_text("Schedule evidence is stale")
        page.screenshot(path=str(output / "simulated-browser-expiry.png"), animations="disabled")
        return "STALE_AFTER_BOUNDARY_AND_DELAYED_RESPONSE"


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
            discovery(live, data, sample, output, viewport)
            results[viewport] = predictions(live, sample, completed, output, viewport)
            historical_controls(live, LOCAL)
            context.close()
        expiry_check = schedule_expiry(browser, output, issues, writes)
        browser.close()
    assert not issues, issues
    assert not writes, writes
    with httpx.Client(base_url=LOCAL, timeout=20, trust_env=False) as http:
        assert http.get("/api/v1/forecasts?limit=1").raise_for_status().json()["total"] == ledger_count
    summary = dict(mode=config["mode"],snapshot=config["snapshot_version"],browser=version,viewports=VIEWPORTS,
                   page_pairs=len(VIEWPORTS)*len(PAGES),states=results,console_errors=issues,ledger_count=ledger_count,
                   historical_controls_checked=list(VIEWPORTS), publish_requests=len(writes),
                   fixture_discovery_checked=list(VIEWPORTS),
                   expiry_check=expiry_check,
                   schedule_freshness=data["schedule_freshness"],eligible_fixture_in_first_six=any(
                       verdict["eligibility_status"] in ("READY","EARLY_READY") for _,verdict in sample))
    (output/"evidence.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    print(json.dumps(run(parser.parse_args().run_id),indent=2))
