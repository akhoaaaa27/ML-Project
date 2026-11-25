"""Overview UI verification against real localhost and isolated browser responses."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os

import httpx
from playwright.sync_api import expect, sync_playwright

from scripts.xpecta_api.settings import PRIVATE
from tests.browser_phase857 import VIEWPORTS, browser_route, monitor

LOCAL = os.environ.get("XPECTA_TEST_URL", "http://127.0.0.1:8765").rstrip("/") + "/"
API = LOCAL + "api/v1/"
RUN_ROOT = PRIVATE / "ui-01"
EXPLORE = ["Overview", "Prediction", "Match Analysis", "Team Statistics", "Prediction History", "AI Model"]
CLOCK = datetime(2026, 11, 24, 12, tzinfo=timezone.utc)


def fixtures(page):
    return page.locator("#homeFixtures .fixture-card")


def states(page, status):
    return page.locator(f'#homeFixtures [data-forecast-state="{status}"]')


def overview_layout(page):
    return page.evaluate("""() => Object.fromEntries(
      ['.hero-main','.hero-copy h1','.hero-copy p','.hero-buttons'].map(selector => {
        const item = document.querySelector(selector).getBoundingClientRect();
        return [selector,{x:item.x,y:item.y,width:item.width,height:item.height}];
      }))""")


def capture_overview(page, path):
    page.evaluate("document.fonts.ready")
    page.locator("#homeFixtures img").evaluate_all("images => Promise.all(images.map(image => image.decode()))")
    page.screenshot(path=str(path), full_page=True, animations="disabled")


def real_browser(browser, output, config, data, history_count):
    viewport_results = {}
    for name, (width, height) in VIEWPORTS.items():
        issues, requests = [], []
        with browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1,
                                 timezone_id="Asia/Ho_Chi_Minh", locale="en-GB", reduced_motion="reduce") as context:
            context.route("**/*", browser_route)
            page = context.new_page()
            monitor(page, issues)
            page.on("request", lambda request: requests.append((request.method, request.url)))
            page.goto(LOCAL)
            expect(page.locator("#bridgeModeText")).to_have_text("REAL RESEARCH")
            expect(fixtures(page)).to_have_count(min(6, data["upcoming_fixtures"]), timeout=15000)
            expect(states(page, "LOADING")).to_have_count(0, timeout=20000)
            expect(page.locator("#homeTeamBars .bar-row").first).to_be_visible()
            expect(page.locator("#homeTeamBars .bar-row[title]").first).to_be_visible()
            assert sum("/historical/season-leaderboard" in url for _, url in requests) == 1
            assert all("/historical/team-stats" not in url for _, url in requests)
            expect(page.locator("#page-home .hero-note, #page-home .hero-caption")).to_have_count(0)
            expect(page.locator("#page-home .stat-feature")).to_contain_text("Selected season · Observed xG per match")
            expect(page.locator("#homeTeamBars")).not_to_contain_text("Sources by team")
            expect(page.locator("#totalMatches")).to_have_text(f'{data["verified_completed"]:,}')
            assert page.locator(".foot-inner > div").nth(1).locator("a").all_text_contents() == EXPLORE
            assert page.locator(".foot-brand img").get_attribute("src") == page.locator("#brand img").get_attribute("src")
            expect(page.locator(".foot")).not_to_contain_text("DEMO · NO LIVE API")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            boxes = [card.bounding_box() for card in fixtures(page).all()]
            if len(boxes) == 6:
                assert len({round(box["x"]) for box in boxes}) == {"desktop": 3, "tablet": 2, "mobile": 1}[name]
            capture_overview(page, output / f"{name}-overview.png")
            observed = {
                "hero": overview_layout(page), "cards": fixtures(page).count(),
                "statuses": page.locator("#homeFixtures [data-forecast-state]").evaluate_all(
                    "nodes => nodes.map(node => node.dataset.forecastState)"),
            }
            explore = page.locator(".foot-inner > div").nth(1).locator("a")
            explore.first.focus()
            page.keyboard.press("Tab")
            expect(explore.nth(1)).to_be_focused()
            assert explore.nth(1).evaluate("link => link.matches(':focus-visible')")
            page.keyboard.press("Enter")
            expect(page.locator("#page-predict")).to_be_visible()
            expect(page.get_by_label("From (UTC+0)")).to_be_visible()
            expect(page.get_by_label("To (UTC+0)")).to_be_visible()
            expect(page.locator("#fixtureEvidence")).to_have_count(0)
            explore.first.press("Enter")
            expect(page.locator("#page-home")).to_be_visible()
            if boxes:
                button = fixtures(page).first.locator("[data-fixture]")
                key = button.get_attribute("data-fixture")
                with page.expect_request(lambda request: request.url.endswith("/forecasts/preview") and
                                         request.method == "POST" and request.post_data_json["fixture_key"] == key):
                    button.press("Enter")
                expect(page.locator("#predictionOutput")).to_be_focused()
                explore.first.press("Enter")
            if name == "desktop":
                season = next(year for year in config["seasons"] if year != int(page.locator("#homeSeason").input_value()))
                with page.expect_response(lambda response: "/historical/season-leaderboard" in response.url and
                                          f"season={season}" in response.url) as filtered:
                    page.locator("#homeSeason").select_option(str(season))
                assert filtered.value.ok
                expect(page.locator("#homeTeamBars .bar-row").first).to_be_visible()
                expect(page.locator("#totalMatches")).to_have_text(f'{data["verified_completed"]:,}')
                page.locator("#page-home [data-jump=predict]").last.press("Enter")
                expect(page.locator("#page-predict")).to_be_visible()
                for link in explore.all():
                    href = link.get_attribute("href")
                    link.press("Enter")
                    expect(page.locator("#page-" + href[1:])).to_be_visible()
                page.locator(".foot").get_by_role("link", name="About the Model").click()
                expect(page.locator("#featuresList code")).to_have_count(13)
                page.locator("#footerXgGuide").click()
                expect(page.locator("#modalTitle")).to_have_text("WHAT IS xG?")
                page.keyboard.press("Escape")
                expect(page.locator("#modalCover")).to_be_hidden()
            assert not issues, issues
            assert all("/forecasts/publish" not in url for _, url in requests)
            viewport_results[name] = observed
    with httpx.Client(trust_env=False) as http:
        assert http.get(API + "forecasts?limit=1").raise_for_status().json()["total"] == history_count
    return viewport_results


def mock_page(context, config, data, source, size, *, offline=False):
    page = context.new_page()
    page.clock.install()
    offset = timezone(timedelta(hours=14))
    rows = [dict(row, kickoff_utc=(CLOCK + timedelta(seconds=30 + 30 * i)).astimezone(offset).isoformat(),
                 match_date=CLOCK.date().isoformat()) for i, row in enumerate(source[:size])]
    indices = {row["canonical_fixture_key"]: i for i, row in enumerate(rows)}
    calls = {"eligibility": [], "preview": [], "publish": []}

    def handle(route):
        request = route.request
        endpoint, _, query = request.url.removeprefix(API).partition("?")
        if endpoint == "bootstrap":
            if offline:
                return route.fulfill(status=503, json={"error": {"message": "XPECTA is temporarily unavailable."}})
            return route.fulfill(json=dict(config, label="UI-01 MOCK"))
        if endpoint == "data-status":
            return route.fulfill(json=dict(data, evaluated_at_utc=CLOCK.isoformat(), upcoming_fixtures=len(rows),
                                           schedule_evidence=[], schedule_freshness="UNVERIFIED"))
        if endpoint == "fixtures":
            return route.fulfill(json=dict(items=rows, total=len(rows), offset=0, limit=100))
        if endpoint == "forecasts/publish":
            calls["publish"].append(request.url)
            return route.fulfill(status=403, json={})
        if endpoint not in ("eligibility", "forecasts/preview"):
            return route.continue_()

        key = (httpx.QueryParams(query)["fixture_key"] if endpoint == "eligibility"
               else request.post_data_json["fixture_key"])
        index = indices[key]
        status = ("READY", "EARLY_READY", "WAITING_DATA", "UNAVAILABLE", "READY", "READY")[index % 6]
        reason = {"WAITING_DATA": "MISSING_ROLLING_STATISTICS", "UNAVAILABLE": "TARGET_NOT_UPCOMING"}.get(status)
        if endpoint == "eligibility":
            calls["eligibility"].append(key)
            return route.fulfill(json=dict(canonical_fixture_key=key, snapshot_version=config["snapshot_version"],
                                           eligibility_status=status, reason=reason, target=rows[index],
                                           history_cutoff=CLOCK.date().isoformat(), fixture_reviewed_at_utc=CLOCK.isoformat()))
        calls["preview"].append(key)
        if index == 4:
            return route.fulfill(status=503, json={"error": {"message": "Forecast request failed."}})
        if status in ("WAITING_DATA", "UNAVAILABLE"):
            return route.fulfill(json=dict(status=status, eligibility=dict(
                canonical_fixture_key=key, snapshot_version=config["snapshot_version"],
                eligibility_status=status, reason=reason)))
        return route.fulfill(json=dict(status=status, preview=dict(
            canonical_fixture_key=key, history_snapshot_version=config["snapshot_version"],
            model_version=config["model_version"], dataset_kind="real", history_cutoff=CLOCK.date().isoformat(),
            target_kickoff_utc=rows[index]["kickoff_utc"], fixture_reviewed_at_utc=CLOCK.isoformat(),
            history_database_sha256=data["database_sha256"] if index != 5 else "a" * 64,
            generated_at_utc=CLOCK.isoformat(), home_xg=0.0 if index == 0 else 1.15, away_xg=1.72,
            source_notice="Isolated UI test output.")))

    page.route(f"{API}**", handle)
    return page, calls, rows


def controlled_browser(browser, output, config, data, source):
    with browser.new_context(viewport={"width": 1440, "height": 900}, timezone_id="Asia/Ho_Chi_Minh",
                             locale="en-GB", device_scale_factor=1, reduced_motion="reduce") as context:
        for size in (0, 4, 8):
            page, calls, rows = mock_page(context, config, data, source, size)
            if size == 8:
                page.add_init_script("""const send = window.fetch.bind(window);
                let delay = true;
                window.delayNextPreview = () => {
                  delay = true;
                  window.previewAborted = false;
                  window.releasePreview = null;
                };
                window.fetch = (url, options) => {
                  if (!delay || !url.endsWith('/forecasts/preview')) return send(url, options);
                  delay = false;
                  return new Promise((resolve, reject) => {
                    window.releasePreview = () => send(url, options).then(resolve, reject);
                    options.signal.addEventListener('abort', () => {
                      window.previewAborted = true;
                      reject(options.signal.reason);
                    }, {once:true});
                  });
                };""")
            page.goto(LOCAL)
            expect(page.locator("#bridgeModeText")).to_have_text("UI-01 MOCK")
            expect(fixtures(page)).to_have_count(min(6, size))
            if not size:
                expect(page.locator("#homeFixtures")).to_contain_text("No upcoming fixtures")
            if size == 8:
                page.wait_for_function("() => typeof window.releasePreview === 'function'")
                expect(states(page, "LOADING")).to_have_count(1)
                page.locator(".nav-links [data-page=analysis]").click()
                page.wait_for_function("() => window.previewAborted === true")
                page.evaluate("window.releasePreview()")
                page.locator(".nav-links [data-page=home]").click()
                expect(states(page, "FORECAST_ERROR")).to_have_count(2)
            if size:
                expect(fixtures(page).first.locator("time")).to_have_text("24 Nov 2026 · 12:00 UTC+0")
                expect(states(page, "READY").locator("[data-overview-xg]")).to_have_text("0.00 VS 1.72")
                expect(states(page, "EARLY_READY")).to_contain_text("Predicted xG · Early forecast")
                expect(states(page, "WAITING_DATA")).to_contain_text("— VS —")
                expect(states(page, "WAITING_DATA")).to_contain_text("Prediction pending")
                expect(states(page, "UNAVAILABLE")).to_contain_text("Prediction unavailable")
                expect(page.locator("#homeFixtures [data-overview-xg]")).to_have_count(2)
            checked = {row["canonical_fixture_key"] for row in rows[:6]}
            assert not calls["eligibility"]
            assert set(calls["preview"]) == checked
            assert not calls["publish"]
            if size == 8:
                capture_overview(page, output / "mock-forecast-states.png")
                page.clock.fast_forward(32000)
                expect(states(page, "READY")).to_have_count(0)
                expect(states(page, "EARLY_READY")).to_have_count(1)
            if size == 4:
                cached_keys = {row["canonical_fixture_key"] for row in rows[:2]}
                page.locator("#page-home [data-jump=predict]").last.press("Enter")
                expect(page.locator('#presetFixtures [data-overview-xg]')).to_have_count(2)
                assert all(calls["preview"].count(key) == 1 for key in cached_keys)
                start = page.get_by_label("From (UTC+0)")
                end = page.get_by_label("To (UTC+0)")
                start.fill("2026-11-24")
                end.fill("2026-11-24")
                expect(page.locator("#presetFixtures .fixture-card")).to_have_count(4)
                expect(page.locator('#presetFixtures [data-forecast-state="READY"] [data-overview-xg]')).to_have_text("0.00 VS 1.72")
                start.fill("2026-11-25")
                expect(page.locator("#presetFixtures [role=alert]")).to_contain_text("The end date (UTC+0)")
                end.fill("2026-11-25")
                expect(page.locator("#presetFixtures .fixture-card")).to_have_count(0)
            if size == 8:
                page.evaluate("() => window.delayNextPreview()")
                page.locator("#page-home [data-jump=predict]").last.press("Enter")
                page.wait_for_function("() => typeof window.releasePreview === 'function'")
                page.get_by_label("Catalogue status").select_option("completed")
                page.wait_for_function("() => window.previewAborted === true")
                expect(page.locator("#presetFixtures .empty")).to_have_text("No fixtures match these filters.")
                page.get_by_label("Catalogue status").select_option("upcoming")
                expect(page.locator('#presetFixtures [data-forecast-state="EARLY_READY"]')).to_have_count(2)
                expect(page.locator('#presetFixtures [data-forecast-state="FORECAST_ERROR"]')).to_have_count(2)
            page.close()
        page, calls, _ = mock_page(context, config, data, source, 0, offline=True)
        page.goto(LOCAL)
        expect(page.locator("#bridgeModeText")).to_have_text("SERVICE UNAVAILABLE")
        expect(page.locator("#homeFixtures [role=alert]")).to_contain_text("temporarily unavailable")
        assert not any(calls.values())

    for name in ("tablet", "mobile"):
        width, height = VIEWPORTS[name]
        with browser.new_context(viewport={"width": width, "height": height}, timezone_id="UTC",
                                 locale="en-GB", device_scale_factor=1, reduced_motion="reduce") as context:
            page, _, _ = mock_page(context, config, data, source, 8)
            page.goto(LOCAL)
            expect(states(page, "READY").locator("[data-overview-xg]")).to_have_text("0.00 VS 1.72")
            early = states(page, "EARLY_READY")
            expect(early).to_contain_text("Predicted xG · Early forecast")
            assert early.evaluate("slot => slot.scrollWidth <= slot.clientWidth + 1")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            capture_overview(page, output / f"mock-{name}-forecast-states.png")


def run(run_id):
    if not run_id or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in run_id):
        raise ValueError("Use a short local lowercase run ID")
    output = RUN_ROOT / run_id
    output.mkdir(parents=True, exist_ok=False)
    with httpx.Client(trust_env=False) as http:
        config = http.get(API + "bootstrap").raise_for_status().json()
        data = http.get(API + "data-status").raise_for_status().json()
        fixtures = http.get(API + "fixtures", params={"season": config["current_season"], "upcoming": True,
                                                       "limit": 8}).raise_for_status().json()["items"]
        history_count = http.get(API + "forecasts?limit=1").raise_for_status().json()["total"]
    assert config["mode"] == "REAL_RESEARCH" and not config["operator_writes_enabled"]
    assert len(fixtures) == 8
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        real = real_browser(browser, output, config, data, history_count)
        controlled_browser(browser, output, config, data, fixtures)
        summary = dict(real=real, mock="PASS", schedule=data["schedule_freshness"], browser=browser.version,
                       snapshot=config["snapshot_version"], real_ledger=history_count)
        browser.close()
    (output / "evidence.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    run(parser.parse_args().run_id)
