"""Exercise the five refined XPECTA pages against the bound localhost service."""

import argparse
from datetime import datetime, timezone
import json
import os

import httpx
from playwright.sync_api import expect, sync_playwright

from scripts.xpecta_api.settings import PRIVATE
from tests.browser_phase857 import VIEWPORTS, browser_route, choose_team, monitor, screenshot

LOCAL = os.environ.get("XPECTA_TEST_URL", "http://127.0.0.1:8765").rstrip("/")
ZONES = {"desktop": "UTC", "tablet": "Asia/Ho_Chi_Minh", "mobile": "Europe/Madrid"}


def discovery(page, fixture, desktop):
    page.goto(LOCAL + "/#predict")
    cards = page.locator("#presetFixtures .fixture-card")
    expect(cards.first).to_be_visible()
    expect(page.locator("#page-predict")).not_to_contain_text("Schedule evidence")
    expect(page.locator("#page-predict")).not_to_contain_text("Check forecast availability")
    assert "UTC+0" in cards.first.locator("time").inner_text()
    start, end = page.get_by_label("From (UTC+0)"), page.get_by_label("To (UTC+0)")
    if desktop:
        status = page.get_by_label("Catalogue status")
        assert start.bounding_box()["y"] == end.bounding_box()["y"]
        assert start.bounding_box()["height"] == status.bounding_box()["height"]
        for property_name in ("background-color", "border-radius", "font-size"):
            style = status.evaluate("(input, name) => getComputedStyle(input).getPropertyValue(name)", property_name)
            expect(start).to_have_css(property_name, style)
    teams = fixture["home_team"], fixture["away_team"]
    selected = page.locator(f'#presetFixtures [data-fixture="{fixture["canonical_fixture_key"]}"]')
    for side in ("Team 1", "Team 2"):
        choose_team(page, side, teams[0])
        expect(selected).to_be_visible()
        page.get_by_role("button", name="Clear filters").click()
    keys = []
    for first, second in (teams, tuple(reversed(teams))):
        choose_team(page, "Team 1", first)
        choose_team(page, "Team 2", second)
        expect(selected).to_be_visible()
        keys.append(cards.locator("[data-fixture]").evaluate_all("buttons => buttons.map(button => button.dataset.fixture)"))
    assert keys[0] == keys[1] and all(
        set(key.split(":")[-2:]) == set(teams) for key in keys[0])
    choose_team(page, "Team 2", teams[1])
    expect(page.locator("#presetFixtures [role=alert]")).to_have_text("Select two different teams to filter fixtures.")
    page.get_by_role("button", name="Clear filters").click()
    expect(page.get_by_role("combobox", name="Team 1")).to_have_value("")
    expect(page.get_by_role("combobox", name="Team 2")).to_have_value("")
    assert page.evaluate("""async () => {
      const {fixturePage} = await import('/assets/fixtures.js');
      const {formatUtcTimestamp} = await import('/assets/view.js');
      const rows = [
        {canonical_fixture_key:'inside', kickoff_utc:'2026-11-29T00:59:59+01:00'},
        {canonical_fixture_key:'outside', kickoff_utc:'2026-11-29T01:00:00+01:00'},
        {canonical_fixture_key:'unknown', kickoff_utc:null},
      ];
      const page = fixturePage(rows, {start:'2026-11-28', end:'2026-11-28'}, 1, '2026-11-28T01:00:00Z');
      return page.items.map(row => row.canonical_fixture_key).join(',') === 'inside' &&
        formatUtcTimestamp('2026-11-29T00:59:59+01:00') === '28 Nov 2026 · 23:59 UTC+0';
    }""")


def simulation(page):
    page.get_by_role("button", name="Custom matchup").click()
    page.locator("#customHome").select_option("Malaga")
    page.locator("#customAway").select_option("Malaga")
    submit = page.locator("#runPrediction")
    submit.click()
    expect(page.locator("#predictionOutput [role=alert]")).to_have_text("Select two different teams to simulate.")
    expect(page.locator("#predictionOutput [data-xg]")).to_have_count(0)
    page.locator("#customAway").select_option("Barcelona")
    with page.expect_response("**/api/v1/simulations") as response:
        submit.click()
    result = response.value.json()
    assert response.value.ok, result
    expect(page.locator("#predictionOutput")).to_contain_text("HYPOTHETICAL SIMULATION")
    for side in ("home", "away"):
        expect(page.locator(f'#predictionOutput [data-xg="{side}"]')).to_have_text(f'{result[side + "_xg"]:.2f}')
    created = datetime.fromisoformat(result["generated_at_utc"]).astimezone(timezone.utc)
    label = f"{created.day} {created:%b %Y} · {created:%H:%M} UTC+0"
    expect(page.locator("#predictionOutput")).to_contain_text(label)
    page.locator('#predictionOutput [data-jump="history"]').click()
    page.reload()
    rows = page.locator("#historyTable tbody tr")
    expect(rows).to_have_count(1)
    expect(rows).to_contain_text("Custom Simulation")
    expect(rows).to_contain_text(label)
    return result


def history(page):
    rows = page.locator("#historyTable tbody tr")
    choose_team(page, "Search teams", "Barcelona")
    expect(rows).to_have_count(1)
    choose_team(page, "Search teams", "Real Madrid")
    expect(page.locator("#historyTable .empty")).to_contain_text("No prediction records match")
    page.locator("#clearHistory").click()
    page.locator("#historyRecordType").select_option("CUSTOM_SIMULATION")
    expect(page.locator("#historyType")).to_be_disabled()
    expect(rows).to_have_count(1)
    rows.locator("[data-simulation]").click()
    expect(page.locator("#modalBody")).to_contain_text("SIMULATED xG")
    page.keyboard.press("Escape")
    with page.expect_download() as download:
        page.locator("#exportHistory").click()
    csv = download.value.path().read_text(encoding="utf-8-sig")
    assert all(value in csv for value in ('"CUSTOM_SIMULATION"', '"record_type"', '"features_sha256"', '"generated_at_utc"'))
    page.evaluate("() => localStorage.setItem('xpecta.simulation.v1.real.bad', 'invalid JSON')")
    page.reload()
    expect(page.locator("#historyNotice")).to_contain_text("Some saved simulations could not be read.")
    expect(rows).to_have_count(1)


def analysis(page, desktop):
    with page.expect_response("**/api/v1/historical/match-analysis?*") as received:
        page.goto(LOCAL + "/#analysis")
    result = received.value.json()
    expect(page.locator("#page-analysis .desc").first).to_have_text("Explore observed xG, xGA and team form.")
    insights = page.locator(".analysis-insights-card")
    expect(insights).to_be_visible()
    expect(insights.locator(".insight-row")).to_have_count(3)
    for name in ("Attacking performance", "Defensive performance", "Recent form"):
        expect(insights).to_contain_text(name)
    expect(page.locator("#page-analysis")).not_to_contain_text("Shot sources")
    expect(page.locator("#page-analysis")).not_to_contain_text("Verified completed matches before")
    if desktop:
        script = """async data => {
          const {matchAnalysis} = await import('/assets/view.js');
          function attacking(home, away) {
            data.home.overall.mean_xg = home;
            data.away.overall.mean_xg = away;
            return new DOMParser().parseFromString(matchAnalysis(data),'text/html')
             .querySelector('.analysis-insights-card .insight-row p').textContent;
          }
          return attacking(2,1).startsWith(data.home.team) &&
            attacking(1,2).startsWith(data.away.team) &&
            attacking(1,1).startsWith('Both teams') &&
            attacking(null,1).includes('insufficient data');
        }"""
        assert page.evaluate(script, result)
        selected = page.locator("#analysisHome").input_value()
        away = page.locator("#analysisAway")
        away.select_option(selected)
        expect(page.locator("#analysisOutput [role=alert]")).to_have_text("Select two different teams to analyze.")
        expect(insights).to_have_count(0)
        away.select_option(result["away"]["team"])
        page.locator("#analysisWindow").select_option("10")
        expect(insights).to_contain_text("Last 10")


def stats_and_model(page, output, name):
    page.goto(LOCAL + "/#stats")
    compare = page.locator("[data-team-comparison]")
    expect(compare).to_be_visible()
    splits = page.locator(".team-splits")
    expect(splits.locator(".home-venue-value")).to_have_css("color", "rgb(118, 227, 93)")
    expect(splits.locator(".away-venue-value")).to_have_css("color", "rgb(255, 138, 87)")
    card = splits.locator(".card").first.bounding_box()
    venue_grid = splits.locator(".location-grid").bounding_box()
    assert 0 <= card["y"] + card["height"] - venue_grid["y"] - venue_grid["height"] <= 32
    expect(splits).not_to_contain_text("Understat (")
    expect(splits).not_to_contain_text("FBref (")
    screenshot(page, output / f"{name}-stats.png")
    page.goto(LOCAL + "/#model")
    for score in ("0.5665", "0.7497", "0.6368", "11.03%"):
        expect(page.locator("#modelMetricCards").get_by_text(score, exact=True)).to_be_visible()
    expect(page.locator("#modelScatter circle")).to_have_count(760)
    expect(page.locator("#modelResidual .evaluation-bar")).to_have_count(85)
    assert page.locator("#modelResidual .evaluation-bar.negative").count() > 0
    expect(page.locator("#modelResidualScope")).to_contain_text("85 of 760")
    assert "2024-08-15" in page.locator("#modelScatter circle").first.get_attribute("data-tip")
    screenshot(page, output / f"{name}-model.png")


def run(run_id):
    output = PRIVATE / "ui-02-06" / run_id
    output.mkdir(parents=True, exist_ok=False)
    with httpx.Client(base_url=LOCAL, trust_env=False) as client:
        fixture = client.get("/api/v1/fixtures", params={"upcoming": True, "season": 2026, "limit": 1}).raise_for_status().json()["items"][0]
        before = client.get("/api/v1/forecasts?limit=1").raise_for_status().json()["total"]
        issues, publications, results = [], [], {}
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True, args=["--disable-background-networking"])
            for name, (width, height) in VIEWPORTS.items():
                viewport = {"width": width, "height": height}
                with browser.new_context(viewport=viewport, timezone_id=ZONES[name], accept_downloads=True,
                                         locale="en-GB", reduced_motion="reduce") as context:
                    context.route("**/*", browser_route)
                    page = context.new_page()
                    monitor(page, issues)
                    page.on("request", lambda request: publications.append(request.url)
                            if request.url.endswith("/forecasts/publish") else None)
                    discovery(page, fixture, name == "desktop")
                    screenshot(page, output / f"{name}-predict.png")
                    result = simulation(page)
                    results[name] = [round(result["home_xg"], 2), round(result["away_xg"], 2)]
                    screenshot(page, output / f"{name}-history.png")
                    if name == "desktop":
                        history(page)
                    analysis(page, name == "desktop")
                    screenshot(page, output / f"{name}-analysis.png")
                    stats_and_model(page, output, name)
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
                    if name == "desktop":
                        page.route("**/api/v1/forecasts?*", lambda route: route.fulfill(status=503, json={}))
                        page.goto(LOCAL + "/#history")
                        page.reload()
                        expect(page.locator("#historyNotice")).to_contain_text("Official forecasts are unavailable.")
                        expect(page.locator("#historyTable tbody tr")).to_have_count(1)
                        page.evaluate("""() => {
                          Object.defineProperty(window, 'localStorage', {get() {throw new Error('Storage unavailable');}});
                          window.dispatchEvent(new StorageEvent('storage', {key:null}));
                        }""")
                        expect(page.locator("#historyNotice")).to_contain_text("Local simulation history is unavailable.")
            with browser.new_context(timezone_id="America/New_York") as context:
                page = context.new_page()
                page.goto(LOCAL)
                assert page.evaluate("""async () => {
                  const {formatUtcTimestamp} = await import('/assets/view.js');
                  return formatUtcTimestamp('2026-11-28T15:15:00Z') === '28 Nov 2026 · 15:15 UTC+0';
                }""")
            browser.close()
        after = client.get("/api/v1/forecasts?limit=1").raise_for_status().json()["total"]
        assert before == after and not publications
        assert all("503" in issue for issue in issues), issues
    result = {"viewports": VIEWPORTS, "timezones": [*ZONES.values(), "America/New_York"],
              "simulations": results, "real_ledger": after, "publish_requests": len(publications)}
    (output / "evidence.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    options = parser.parse_args()
    if not options.run_id.replace("-", "").isalnum():
        parser.error("Use a short alphanumeric run ID")
    print(json.dumps(run(options.run_id), indent=2))
