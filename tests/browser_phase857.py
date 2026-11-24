"""Run an offline Edge browser walkthrough and save local V9.12 screenshot pairs."""

import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
from threading import Thread
from time import monotonic, sleep
from unittest.mock import patch
from urllib.parse import urlparse

import httpx
from playwright.sync_api import expect, sync_playwright
import uvicorn

from scripts.inference.common import sha256
from scripts.multisource.forecast_examples import TARGET
from scripts.xpecta_api.app import create_app
from scripts.xpecta_api.demo import initialize_demo
from scripts.xpecta_api.prepare_frontend import REFERENCE_SHA256
from scripts.xpecta_api.settings import FRONTEND, PREPARED, PRIVATE, Mode, Settings
from tests.test_phase857_api import AUTH, OPERATOR, create_live_demo

PAGES = ["home", "predict", "analysis", "stats", "history", "model"]
VIEWPORTS = {"desktop": (1440, 900), "tablet": (820, 1180), "mobile": (390, 844)}
FONT = "https://fonts.gstatic.com/phase857-montserrat.ttf"
LATE_PREVIEW = """() => {
    const original = window.fetch;
    window.fetch = function(url, ...args) {
        if (!url.endsWith('/forecasts/preview')) return original(url, ...args);
        return new Promise(resolve => setTimeout(resolve, 420)).then(() => original(url, ...args));
    };
}"""


@contextmanager
def host(profile, token="", *, demo_name="browser"):
    app = create_app(Settings(Mode.SYNTHETIC_DEMO, profile, demo_name, token))
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", proxy_headers=False))
        thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = monotonic() + 25
            while not server.started:
                if not thread.is_alive() or monotonic() >= deadline:
                    raise RuntimeError("Local browser test server did not start")
                sleep(0.05)
            yield f"http://127.0.0.1:{port}"
        finally:
            server.should_exit = True
            thread.join(12)
            if thread.is_alive():
                raise RuntimeError("Local browser test server did not stop")


def publish(url):
    response = httpx.post(url + "/api/v1/forecasts/publish", headers=AUTH,
                          json={"fixture_key": TARGET}, trust_env=False)
    response.raise_for_status()
    return response.json()


def browser_route(route):
    url = urlparse(route.request.url)
    if url.hostname == "fonts.googleapis.com" and url.path.startswith("/css2"):
        style = f"@font-face{{font-family:Montserrat;font-weight:100 900;src:url('{FONT}') format('truetype')}}"
        route.fulfill(status=200, content_type="text/css", body=style, headers={"Access-Control-Allow-Origin": "*"})
    elif route.request.url == FONT:
        route.fulfill(path=FRONTEND/"montserrat.ttf", content_type="font/ttf",
                      headers={"Access-Control-Allow-Origin": "*"})
    elif url.scheme in {"data", "file", "blob"} or url.hostname == "127.0.0.1":
        route.continue_()
    else:
        route.abort()


def await_page(page, name):
    expect(page.locator("#page-" + name)).to_be_visible()
    selectors = {"home": "#homeFixtures .fixture-card", "predict": "#presetFixtures .fixture-card",
                 "analysis": "#analysisOutput .analysis-overview-card",
                 "stats": "#statsOutput .metric-grid", "history": "#historyTable tr",
                 "model": "#featuresList code"}
    if name == "history" and page.url.startswith("file:"):
        expect(page.locator("#historyTable .empty")).to_be_visible()
    else:
        expect(page.locator(selectors[name]).first).to_be_visible(timeout=13000)
    if name == "home":
        expect(page.locator("#homeTeamBars .bar-row").first).to_be_visible(timeout=13000)
    page.evaluate("document.fonts.ready")
    assert page.evaluate("document.fonts.check('700 24px Montserrat')"), name
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), name


def geometry(page):
    return page.evaluate("""() => {
      const c = document.querySelector('.topbar');
      const r = c.getBoundingClientRect();
      return {height: r.height, width: r.width, background: getComputedStyle(c).backgroundImage,
        filter: getComputedStyle(c).backdropFilter,
        brand: getComputedStyle(document.querySelector('.expecta-logo')).objectFit};
    }""")


def screenshot(page, path):
    page.screenshot(path=str(path), animations="disabled", full_page=True)


def visual_pairs(browser, local, output, console_issues):
    reference = (PREPARED/"reference.html").as_uri()
    results = []
    for viewport, (width, height) in VIEWPORTS.items():
        context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1)
        context.route("**/*", browser_route)
        before, after = context.new_page(), context.new_page()
        monitor(after, console_issues)
        for name in PAGES:
            before.goto(reference + "#" + name)
            after.goto(local + "/#" + name)
            await_page(before, name)
            await_page(after, name)
            expected, actual = geometry(before), geometry(after)
            assert expected.keys() == actual.keys(), (viewport, name)
            assert abs(expected["height"] - actual["height"]) <= 2 and expected["width"] == actual["width"], (viewport, name)
            for key in ("background", "filter", "brand"):
                assert expected[key] == actual[key], (viewport, name, key)
            expect(after.locator("#bridgeModeText")).to_be_visible()
            screenshot(before, output / f"{viewport}-{name}-reference.png")
            screenshot(after, output / f"{viewport}-{name}-integrated.png")
            results.append({"viewport": viewport, "page": name, "reference_navigation": expected,
                            "integrated_navigation": actual})
        context.close()
    return results


def monitor(page, issues):
    page.on("pageerror", lambda error: issues.append(str(error)))
    page.on("console", lambda entry: issues.append(entry.text) if entry.type == "error" else None)
    page.add_init_script("""window.addEventListener('unhandledrejection', event =>
        console.error('Unhandled browser rejection', String(event.reason)));""")


def workflow(browser, local, output, issues):
    context = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True,
                                  timezone_id="America/Los_Angeles")
    context.route("**/*", browser_route)
    page = context.new_page()
    monitor(page, issues)
    page.goto(local)
    await_page(page, "home")
    cards = page.locator("#homeFixtures .fixture-card")
    expect(cards).to_have_count(4)
    target = f'[data-fixture="{TARGET}"]'
    target_card = cards.filter(has=page.locator(target))
    overview_xg = target_card.locator('[data-forecast-state="EARLY_READY"] [data-overview-xg]')
    expect(overview_xg).to_be_visible(timeout=15000)
    displayed_xg = overview_xg.inner_text()
    first, middle, _, last = [card.bounding_box() for card in cards.all()]
    assert abs(last["x"] - middle["x"]) <= 1 and abs(last["width"] - first["width"]) <= 1
    assert page.evaluate("""async () => {
      const {fixturePage} = await import('/assets/fixtures.js');
      const {formatUtcTimestamp} = await import('/assets/view.js');
      const now = '2026-11-20T10:00:00Z';
      const rows = Array.from({length: 20}, (_, index) => ({
        canonical_fixture_key: String(index).padStart(2, '0'), home_team: 'Atlético Madrid',
        away_team: 'Test Club', match_date: '2026-11-23', observed_status: 'scheduled',
        kickoff_utc: index === 0 ? null : '2026-11-23T20:00:00Z',
      })).reverse();
      const lengths = [0, 1, 4, 12, 20].map(n => fixturePage(rows.slice(0, n), {}, 1, now).items.length);
      const second = fixturePage(rows, {search: '  ATLETICO   madrid  '}, 2, now);
      const date = fixturePage(rows, {start: '2026-11-23', end: '2026-11-23'}, 99, now);
      return lengths.join() === '0,1,4,12,12' && second.total === 20 &&
        second.items[0].canonical_fixture_key === '13' && second.items.at(-1).kickoff_utc === null &&
        date.total === 19 && date.page === 2 &&
        formatUtcTimestamp('2026-11-24T00:30:00+02:00') === '2026-11-23 22:30 UTC+0' &&
        formatUtcTimestamp('2026-11-24T23:15:09.123456-02:00', {seconds: true}) === '2026-11-25 01:15:09 UTC+0' &&
        formatUtcTimestamp('2026-11-24T23:15:00-02:00', {compact: true}) === '25 Nov · 01:15 UTC+0' &&
        [null, '', '2026-11-24', '2026-11-24T12:00:00', '2026-11-24Z', 'invalidZ']
          .every(value => formatUtcTimestamp(value) === '—');
    }""")
    page.evaluate(LATE_PREVIEW)
    target_card.locator(target).click()
    expect(page.locator("#predictionOutput")).to_have_attribute("aria-busy", "true")
    expect(page.locator("#predictionOutput .forecast-placeholder")).to_have_count(2)
    expect(page.locator("#predictionOutput [data-xg]")).to_have_count(0)
    expect(page.get_by_text("Loading…", exact=True).last).to_be_visible()
    screenshot(page, output / "prediction-loading.png")
    expect(page.locator("#predictionOutput [data-xg]")).to_have_count(2)
    assert displayed_xg == " VS ".join(page.locator("#predictionOutput [data-xg]").all_text_contents())
    expect(page.locator("#predictionOutput").get_by_text("Generated", exact=True).locator("..")).to_contain_text("UTC+0")
    page.locator("#backToFixtures").click()
    page.locator("#presetFixtures button" + f'[data-fixture="{TARGET}"]').click()
    expect(page.locator("#predictionOutput [data-readiness]")).to_have_text("EARLY READY")
    expect(page.locator("#predictionOutput [data-xg]")).to_have_count(2)
    screenshot(page, output / "preset-prediction.png")
    preset = [node.inner_text() for node in page.locator("#predictionOutput [data-xg]").all()]
    page.get_by_role("button", name="Custom matchup").click()
    page.locator("#customHome").select_option("Valencia")
    page.locator("#customAway").select_option("Real Madrid")
    page.locator("#runPrediction").click()
    expect(page.locator("#predictionOutput [data-xg]")).to_have_count(2)
    assert [node.inner_text() for node in page.locator("#predictionOutput [data-xg]").all()] == preset
    page.locator("[data-analyze]").click()
    await_page(page, "analysis")
    expect(page.locator(".analysis-insights-card")).to_be_visible()
    with page.expect_request(lambda request: request.url.endswith("/api/v1/forecasts/preview")) as resumed:
        page.locator(".analysis-insights-card [data-to-custom]").click()
    assert resumed.value.post_data_json == {"fixture_key": TARGET}
    expect(page.locator("#predictionOutput [data-readiness]")).to_have_text("EARLY READY")
    assert [node.inner_text() for node in page.locator("#predictionOutput [data-xg]").all()] == preset
    page.locator("[data-analyze]").click()
    await_page(page, "analysis")
    with page.expect_request(lambda request: request.url.endswith("/api/v1/forecasts/preview")) as nav_resumed:
        page.locator(".nav-links [data-page=predict]").click()
    assert nav_resumed.value.post_data_json == {"fixture_key": TARGET}
    expect(page.locator("#predictionOutput [data-xg]")).to_have_count(2)
    page.locator("[data-analyze]").click()
    await_page(page, "analysis")
    page.locator("#analysisWindow").select_option("10")
    page.locator("#analysisRefresh").click()
    expect(page.locator("#analysisOutput").get_by_text("LAST 10", exact=False).first).to_be_visible()
    page.locator("#analysisAway").select_option("Barcelona")
    page.locator("#analysisRefresh").click()
    expect(page.locator(".analysis-insights-card")).to_be_visible()
    page.locator(".analysis-insights-card [data-to-custom]").click()
    expect(page.locator("#customAway")).to_have_value("Barcelona")
    expect(page.locator("#predictionOutput [data-xg]")).to_have_count(0)
    page.locator(".nav-links [data-page=stats]").click()
    await_page(page, "stats")
    page.locator("#statsSeason").select_option("2026")
    page.locator("#statsTeam").select_option("Valencia")
    page.locator("#statsRefresh").click()
    expect(page.locator("#statsOutput .section-title").first).to_have_text("VALENCIA")
    expect(page.locator("[data-team-comparison] .crest")).to_have_count(2)
    page.locator(".nav-links [data-page=model]").click()
    await_page(page, "model")
    expect(page.locator("#featuresList code")).to_have_count(13)
    expect(page.locator("#featuresList code").nth(11)).to_have_text("opponent_matches_seen")
    expect(page.locator("#modelMetricCards")).to_contain_text("2025/26 after 2025-09-30")
    page.locator(".nav-links [data-page=history]").click()
    await_page(page, "history")
    expect(page.locator("#historyTable tbody tr")).to_have_count(2)
    expect(page.locator("#historyTable tbody tr").first).to_contain_text("UTC+0")
    page.locator("#historyType").select_option("UPDATED")
    expect(page.locator("#historyTable tbody tr")).to_have_count(1)
    page.locator("#historySearch").fill("unmatched")
    expect(page.locator("#historyTable .empty")).to_be_visible()
    page.locator("#clearHistory").click()
    expect(page.locator("#historyTable tbody tr")).to_have_count(2)
    page.locator("#historySort").select_option("old")
    expect(page.locator("#historyTable tbody tr").first).to_contain_text("INITIAL")
    page.locator("#historyTable [data-history]").first.click()
    expect(page.get_by_text("Created", exact=False).filter(has_text="UTC+0")).to_be_visible()
    page.get_by_text("Revision evidence", exact=True).click()
    expect(page.locator(".history-integrity")).to_contain_text("Feature SHA-256")
    page.locator("[data-compare]").click()
    expect(page.locator("#compareOutput h3")).to_have_text("V1 → V2")
    screenshot(page, output / "comparison.png")
    page.keyboard.press("Escape")
    with page.expect_download() as pending:
        page.locator("#exportHistory").click()
    csv = Path(pending.value.path()).read_text(encoding="utf-8-sig")
    assert all(name in csv for name in ('"INITIAL"', '"UPDATED"', '"dataset_kind"', '"record_sha256"', '"features_sha256"'))
    assert '"generated_at_utc"' in csv and "UTC+0" not in csv
    assert page.evaluate(r"""async () => {
      const {csvText} = await import('/assets/view.js');
      const value = csvText([{home_team:' =2+2', away_team:'Tab\t\n"quoted"'}]);
      return value.includes(String.fromCharCode(39) + ' =2+2') && value.includes('""quoted""');
    }""")
    page.route("**/api/v1/model/summary", lambda route: route.fulfill(status=200, json={}))
    page.locator(".nav-links [data-page=model]").click()
    expect(page.locator("#featuresList [role=alert]")).to_have_text("XPECTA returned an unexpected response.")
    screenshot(page, output / "api-failure.png")
    page.unroute("**/api/v1/model/summary")
    page.locator(".nav-links [data-page=predict]").click()
    page.route("**/api/v1/forecasts/preview", lambda route: route.fulfill(status=200, json={}))
    page.locator("#presetFixtures button" + f'[data-fixture="{TARGET}"]').click()
    expect(page.locator("#predictionOutput [role=alert]")).to_have_text("XPECTA returned an unexpected response.")
    expect(page.locator("#predictionOutput .forecast-placeholder")).to_have_count(2)
    expect(page.locator("#predictionOutput [data-xg]")).to_have_count(0)
    page.unroute("**/api/v1/forecasts/preview")
    page.locator(".nav-links [data-page=home]").click()
    expect(page.locator("#homeFixtures .fixture-card").first).to_be_visible()
    context.close()


def mobile_and_blocked(browser, local, output, issues):
    context = browser.new_context(viewport={"width": 390, "height": 844})
    context.route("**/*", browser_route)
    page = context.new_page()
    monitor(page, issues)
    page.goto(local)
    await_page(page, "home")
    expect(page.locator("#bridgeModeText")).to_have_text("SYNTHETIC DEMO")
    page.locator("#mobileToggle").click()
    expect(page.locator("#mobileToggle")).to_have_attribute("aria-expanded", "true")
    screenshot(page, output / "mobile-navigation.png")
    page.locator("#mobileMenu [data-page=predict]").click()
    await_page(page, "predict")
    expect(page.locator("#mobileToggle")).to_have_attribute("aria-expanded", "false")
    page.locator("#presetFixtures button" + f'[data-fixture="{TARGET}"]').click()
    expect(page.locator("#predictionOutput [data-readiness]")).to_have_text("WAITING DATA")
    expect(page.locator("#predictionOutput [role=alert]")).to_have_text("MISSING ROLLING STATISTICS")
    expect(page.locator("#predictionOutput [data-xg]")).to_have_count(0)
    expect(page.locator("#predictionOutput .forecast-placeholder")).to_have_count(2)
    screenshot(page, output / "mobile-missing-data.png")
    context.close()


def live_fixture_workflow(browser, local, output, issues):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.route("**/*", browser_route)
    page = context.new_page()
    monitor(page, issues)
    page.goto(local)
    await_page(page, "home")
    expect(page.locator(f'#homeFixtures button[data-fixture="{TARGET}"]')).to_have_count(0)
    page.locator(".nav-links [data-page=predict]").click()
    await_page(page, "predict")
    expect(page.locator(f'#presetFixtures button[data-fixture="{TARGET}"]')).to_have_count(0)
    page.get_by_label("Catalogue status").select_option("live")
    expect(page.locator(f'#presetFixtures button[data-fixture="{TARGET}"]')).to_have_count(1)
    page.get_by_role("button", name="Custom matchup").click()
    page.locator("#customHome").select_option("Valencia")
    page.locator("#customAway").select_option("Real Madrid")
    with page.expect_response(lambda response: response.url.endswith("/api/v1/forecasts/preview")) as preview:
        page.locator("#runPrediction").click()
    response = preview.value
    assert response.status == 200 and response.json()["eligibility"]["target"]["observed_status"] == "live"
    expect(page.locator('#predictionOutput [data-observed-status="live"]')).to_have_text("LIVE")
    expect(page.locator("#predictionOutput [data-readiness]")).to_have_text("UNAVAILABLE")
    expect(page.locator("#predictionOutput [role=alert]")).to_have_text("TARGET NOT UPCOMING")
    expect(page.locator("#predictionOutput [data-xg]")).to_have_count(0)
    expect(page.locator("#predictionOutput .forecast-placeholder")).to_have_count(2)
    screenshot(page, output / "live-fixture-unavailable.png")
    context.close()


def run(output, channel):
    if not output.resolve().is_relative_to(PRIVATE.resolve()):
        raise ValueError("Keep visual evidence in the local ignored phase directory")
    output.mkdir(parents=True, exist_ok=False)
    assert sha256(PREPARED / "reference.html") == REFERENCE_SHA256
    console_issues = []
    with TemporaryDirectory(prefix="phase857-browser-") as temp, patch("scripts.xpecta_api.settings.PRIVATE", Path(temp)):
        initialize_demo(Path(temp) / "demos" / "browser")
        create_live_demo(Path(temp) / "demos" / "browser-live")
        with host("initial", OPERATOR) as local:
            assert publish(local)["forecast"]["forecast_stage"] == "INITIAL"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel=channel, headless=True, args=["--disable-background-networking"])
            browser_version = browser.version
            try:
                with host("updated", OPERATOR) as local:
                    assert publish(local)["forecast"]["forecast_stage"] == "UPDATED"
                    workflow(browser, local, output, console_issues)
                    comparisons = visual_pairs(browser, local, output, console_issues)
                with host("incomplete") as local:
                    mobile_and_blocked(browser, local, output, console_issues)
                with host("initial", demo_name="browser-live") as local:
                    live_fixture_workflow(browser, local, output, console_issues)
            finally:
                browser.close()
    assert not console_issues, console_issues
    result = {"status": "PASS", "browser": channel, "browser_version": browser_version,
              "visual_pairs": comparisons, "screenshot_count": len(list(output.glob("*.png"))),
              "console_errors": 0, "uncaught_rejections": 0, "external_requests_allowed": False,
              "live_fixture_display_verified": True, "live_fixture_forecast_status": "UNAVAILABLE"}
    (output / "browser-evidence.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    return {"status": "PASS", "browser": browser_version, "visual_pairs": len(comparisons),
            "screenshot_count": result["screenshot_count"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--channel", default="msedge")
    name = parser.parse_args()
    output = PRIVATE / "visual" / name.run_id
    print(json.dumps(run(output, name.channel), indent=2))
