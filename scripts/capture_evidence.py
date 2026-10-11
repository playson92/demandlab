"""Inspect a real rendered demo; keep trial artifacts exclusively under output."""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


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
    errors, evidence = [], {"url": url, "screenshots": [], "checks": []}
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
        assert "Czas dostawy: 7 → 14" in page.content()
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
            page.set_viewport_size({"width": 683, "height": 384})
            visit("product")
            shot("frontend_zoom_200.png")
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
                    "200-percent-equivalent-layout",
                    "invalid-URL-friendly-fallback",
                ]
            )
        browser.close()
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
