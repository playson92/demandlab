"""Inspect a real rendered demo; keep trial artifacts exclusively under output."""

import argparse
import base64
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def inventory_layout(page):
    """Measure rendered SVG text separately from interactions and visual review."""
    chart = page.get_by_test_id("stPlotlyChart").first
    chart.scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    boxes = chart.evaluate(
        """el => {
            const svg = el.querySelector('.main-svg').getBoundingClientRect();
            const box = node => {
                const r = node.getBoundingClientRect();
                return {text: node.textContent, left: r.left - svg.left,
                    top: r.top - svg.top, right: r.right - svg.left,
                    bottom: r.bottom - svg.top};
            };
            return {width: svg.width, height: svg.height,
                legend: box(el.querySelector('.legend')),
                entries: [...el.querySelectorAll('.legendtext')].map(box),
                titles: [...el.querySelectorAll(
                    '.annotation-text, .xtitle, .x2title, .ytitle, .y2title'
                )].map(box)};
        }"""
    )
    legend = boxes["legend"]
    assert len(boxes["entries"]) == 4, boxes
    for rect in [legend, *boxes["titles"]]:
        assert rect["left"] >= -1 and rect["right"] <= boxes["width"] + 1, boxes
        assert rect["top"] >= -1 and rect["bottom"] <= boxes["height"] + 1, boxes
    for title in boxes["titles"]:
        overlap = min(title["right"], legend["right"]) > max(title["left"], legend["left"]) and min(
            title["bottom"], legend["bottom"]
        ) > max(title["top"], legend["top"])
        assert not overlap, boxes
    return boxes


def native_zoom(url, destination):
    """Use Chromium's tab zoom, recording the actual dimensions and scale."""
    extension = destination / "zoom-tools" / "extension"
    extension.mkdir(parents=True, exist_ok=True)
    (extension / "manifest.json").write_text(
        json.dumps(
            {
                "manifest_version": 3,
                "name": "Local browser zoom verification",
                "version": "1.0",
                "permissions": ["tabs"],
                "background": {"service_worker": "background.js"},
            }
        ),
        encoding="utf-8",
    )
    (extension / "background.js").write_text(
        "chrome.runtime.onInstalled.addListener(() => {});", encoding="utf-8"
    )
    checks, screenshots, errors = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            str(destination / "zoom-tools" / "profile"),
            channel="chromium",
            headless=True,
            no_viewport=True,
            args=[
                "--window-size=1366,855",
                f"--disable-extensions-except={extension.resolve()}",
                f"--load-extension={extension.resolve()}",
            ],
        )
        worker = (
            browser.service_workers[0]
            if browser.service_workers
            else browser.wait_for_event("serviceworker")
        )
        page = browser.pages[0]
        session = browser.new_cdp_session(page)
        page.on("pageerror", lambda exc: errors.append(str(exc)))

        def screenshot(name):
            # Playwright's CSS-sized clip can crop a natively zoomed window.
            # CDP captures the complete physical viewport at the actual zoom.
            png = session.send(
                "Page.captureScreenshot",
                {"format": "png", "fromSurface": True, "captureBeyondViewport": False},
            )
            (destination / name).write_bytes(base64.b64decode(png["data"]))
            screenshots.append(name)

        for view in ["product", "inventory", "methods"]:
            page.goto(url + "?" + urlencode({"view": view, "sku": "85123A"}))
            page.get_by_test_id("stPlotlyChart").first.wait_for(timeout=60000)
            worker.evaluate(
                """async prefix => {
                    const tabs = await chrome.tabs.query({});
                    const tab = tabs.find(t => t.url?.startsWith(prefix));
                    await chrome.tabs.setZoom(tab.id, 2);
                }""",
                url,
            )
            page.wait_for_timeout(600)
            metrics = page.evaluate(
                """({width: innerWidth, height: innerHeight, dpr: devicePixelRatio,
                    outerWidth, outerHeight, scroll: document.documentElement.scrollWidth})"""
            )
            assert abs(metrics["dpr"] - 2) < 0.01, metrics
            assert metrics["scroll"] <= metrics["width"] + 2, metrics
            assert page.get_by_test_id("stException").count() == 0
            record = {"view": view, **metrics}
            if view == "inventory":
                record["inventory_svg"] = inventory_layout(page)
                # The 440px chart exceeds a 200% viewport: capture both ends
                # without increasing the browser window or reducing the zoom.
                chart = page.get_by_test_id("stPlotlyChart").first
                for end in ["start", "end"]:
                    chart.evaluate("(el, end) => el.scrollIntoView({block: end})", end)
                    if end == "start":
                        page.get_by_test_id("stMain").evaluate("el => el.scrollTop -= 72")
                    page.wait_for_timeout(300)
                    name = f"inventory_zoom_200_{end}.png"
                    screenshot(name)
            else:
                name = f"{view}_zoom_200.png"
                screenshot(name)
            checks.append(record)
        browser.close()
    assert not errors, errors
    return {"status": "PASS", "zoom_percent": 200, "checks": checks, "screenshots": screenshots}


def capture(url, destination, smoke=False):
    destination.mkdir(parents=True, exist_ok=True)
    for _attempt in range(90):
        try:
            with urlopen(url + "/_stcore/health", timeout=2) as response:
                if response.status == 200:
                    break
        except OSError:
            time.sleep(1)
    else:
        raise RuntimeError("Demo did not start within 90 seconds")
    errors, evidence = (
        [],
        {
            "url": url,
            "screenshots": [],
            "checks": [],
            "rendered_layout_checks": [],
            "visual_review": {
                "status": "NOT_RUN",
                "reason": "Requires inspecting saved screenshots",
            },
        },
    )
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 768}, device_scale_factor=1)
        page.on("pageerror", lambda exc: errors.append(str(exc)))

        def visit(view, sku="85123A", method="weekday_mean_4w"):
            page.goto(url + "?" + urlencode({"view": view, "sku": sku, "method": method}))
            page.get_by_test_id("stPlotlyChart").first.wait_for(timeout=60000)
            assert page.get_by_test_id("stException").count() == 0
            page.wait_for_timeout(600)

        def shot(name):
            viewport = page.viewport_size
            page.get_by_test_id("stMain").evaluate("el => el.scrollTo(0, 0)")
            page.wait_for_timeout(300)
            viewport_name = name.replace(".png", "_viewport.png")
            page.screenshot(path=str(destination / viewport_name))
            evidence["screenshots"].append(viewport_name)
            if parse_qs(urlparse(page.url).query).get("view") == ["inventory"]:
                evidence["rendered_layout_checks"].append(
                    {"viewport": viewport, "inventory_svg": inventory_layout(page)}
                )
                chart_name = name.replace(".png", "_chart.png")
                page.get_by_test_id("stPlotlyChart").first.screenshot(
                    path=str(destination / chart_name)
                )
                evidence["screenshots"].append(chart_name)
            # A separate full-content image is convenient for reviewing all
            # controls. It is not evidence of the original viewport height.
            content_height = page.get_by_test_id("stMain").evaluate("el => el.scrollHeight")
            page.set_viewport_size(
                {
                    "width": viewport["width"],
                    "height": min(4000, max(viewport["height"], content_height)),
                }
            )
            page.evaluate("window.scrollTo(0, 0)")
            page.get_by_test_id("stMain").evaluate("el => el.scrollTo(0, 0)")
            page.wait_for_timeout(300)
            page.screenshot(path=str(destination / name), full_page=True)
            page.set_viewport_size(viewport)
            evidence["screenshots"].append(name)

        visit("product")
        product = page.get_by_role(
            "combobox", name="Wyszukaj produkt po nazwie lub SKU", exact=True
        )
        for sku in ["17003", "85123A"]:
            product.fill(sku)
            page.get_by_role("option", name=re.compile(rf"^{sku} · ")).click()
            page.wait_for_function(
                "sku => new URL(location.href).searchParams.get('sku') === sku", arg=sku
            )
            page.get_by_test_id("stPlotlyChart").first.wait_for(timeout=60000)
            page.wait_for_timeout(600)
        evidence["checks"].append("product-selection-widget")
        assert page.get_by_test_id("stPlotlyChart").first.bounding_box()["y"] < 768
        page.get_by_role("combobox", name="Przedział nominalny", exact=True).click()
        page.get_by_role("option", name="95%", exact=True).click()
        page.get_by_role("switch", name="Porównaj metody", exact=True).press("Space")
        page.get_by_role("combobox", name="Pasmo dla jednej metody", exact=True).wait_for()
        page.get_by_role("switch", name="Porównaj metody", exact=True).press("Space")
        page.get_by_role("combobox", name="Przedział nominalny", exact=True).click()
        page.get_by_role("option", name="80%", exact=True).click()
        shot("frontend_forecast.png")
        page.get_by_role("button", name="Sprawdź scenariusz zapasu").click()
        page.get_by_role("spinbutton", name="Czas dostawy [dni]", exact=True).wait_for()
        page.wait_for_function("new URL(location.href).searchParams.get('view') === 'inventory'")
        initial = page.get_by_role(
            "spinbutton", name="Zapas początkowy [szt.]", exact=True
        ).input_value()
        page.get_by_role("button", name="Zapisz jako punkt odniesienia").click()
        lead = page.get_by_role("spinbutton", name="Czas dostawy [dni]", exact=True)
        lead.fill("14")
        lead.press("Enter")
        page.get_by_text(
            "A: zapisany punkt odniesienia · B: bieżący scenariusz", exact=True
        ).wait_for()
        assert (
            page.get_by_role("spinbutton", name="Zapas początkowy [szt.]", exact=True).input_value()
            == initial
        )
        page.get_by_text("Czas dostawy: 7 → 14", exact=True).wait_for()
        with page.expect_download() as download:
            page.get_by_role("button", name="Scenariusz B · JSON").click()
        export = destination / "inventory_visible.json"
        download.value.save_as(str(export))
        saved = json.loads(export.read_text(encoding="utf-8"))
        assert saved["parameters"]["lead_time_days"] == 14
        assert saved["parameters"]["initial_stock"] == int(initial)
        assert saved["provenance"]["sku"] == "85123A"
        from demandlab.inventory import InventoryParameters, simulate

        expected = simulate(
            saved["forecast"], saved["scenario_sales"], InventoryParameters(**saved["parameters"])
        )
        assert expected.summary == saved["summary"]
        with page.expect_download() as download:
            page.get_by_role("button", name="Scenariusz B · CSV").click()
        download.value.save_as(str(destination / "inventory_visible.csv"))
        shot("frontend_inventory.png")
        page.get_by_role("combobox", name="Ścieżka sprzedaży", exact=True).click()
        page.get_by_role("option", name="Hipotetyczna · wspólna referencja", exact=True).click()
        page.get_by_test_id("stSlider").get_by_role("slider").wait_for()
        assert (
            page.get_by_text(
                "A: zapisany punkt odniesienia · B: bieżący scenariusz", exact=True
            ).count()
            == 0
        )
        evidence["checks"].extend(
            [
                "first-viewport-chart",
                "product-to-inventory-context",
                "lead-time-A-B-preserves-stock",
                "visible-JSON-and-CSV-download",
                "export-matches-original-simulator",
                "scenario-change-invalidates-A",
                "95-percent-band-and-method-comparison",
            ]
        )
        visit("methods")
        assert "Nie zawiera prognoz walidacyjnych" in page.content()
        page.get_by_role("combobox", name="Etap oceny", exact=True).click()
        page.get_by_role("option", name="Test końcowy · zamrożony", exact=True).click()
        page.get_by_role("heading", name="Test · aktualny produkt 85123A", exact=True).wait_for()
        shot("frontend_methods.png")
        evidence["checks"].append("validation-test-page-scope")
        visit("product", "17003", "hist_gradient_boosting")
        page.reload()
        page.get_by_test_id("stPlotlyChart").first.wait_for(timeout=60000)
        query = parse_qs(urlparse(page.url).query)
        assert query["sku"] == ["17003"] and query["method"] == ["hist_gradient_boosting"]
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.tagName") != "BODY"
        evidence["checks"].extend(["product-method-URL-refresh", "keyboard-focus"])
        if not smoke:
            for width, height in [(1440, 900), (390, 844)]:
                page.set_viewport_size({"width": width, "height": height})
                for view in ["product", "inventory", "methods"]:
                    visit(view)
                    shot(f"frontend_{view}_{width}.png")
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= window.innerWidth + 2"
                    )
            page.goto(url + "?view=bad&sku=bad&method=bad")
            page.get_by_text(
                "Nieznany parametr adresu został pominięty. Wybrano dostępne ustawienia demo.",
                exact=True,
            ).wait_for(timeout=60000)
            evidence["checks"].extend(
                [
                    "1440x900",
                    "1366x768",
                    "390x844-no-horizontal-overflow",
                    "native-browser-200-percent-zoom",
                    "invalid-URL-friendly-fallback",
                ]
            )
        browser.close()
    if not smoke:
        evidence["native_zoom"] = native_zoom(url, destination)
    assert not errors, errors
    evidence.update(status="PASS", browser_errors=errors)
    (destination / "browser_checks.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(evidence, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8501")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "output/frontend/browser" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
    )
    parser.add_argument("--ci-smoke", action="store_true")
    args = parser.parse_args()
    capture(args.url.rstrip("/"), args.output_dir, args.ci_smoke)
