"""Capture real browser screenshots and exercise downloads from the running app."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def capture():
    screenshots = ROOT / "docs/screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    exports = ROOT / "reports/exports"
    exports.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1150}, device_scale_factor=1)
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.goto("http://127.0.0.1:8501", wait_until="networkidle")
        page.get_by_text("Przegląd", exact=True).wait_for()
        page.get_by_test_id("stMetric").first.wait_for()
        manifest = json.loads((ROOT / "data/demo/manifest.json").read_text(encoding="utf-8"))
        if "regular" in manifest.get("examples", {}):
            code = manifest["examples"]["regular"]
            page.get_by_role("combobox").first.click()
            page.get_by_role("option").filter(has_text=code).first.click()
        for view, name in [
            ("Prognoza produktu", "forecast"),
            ("Jakość modeli", "quality"),
            ("Symulator", "simulator"),
        ]:
            page.get_by_text(view, exact=True).first.click()
            page.get_by_role("heading", name=view, exact=True).wait_for()
            page.locator(".js-plotly-plot").first.wait_for()
            if name == "quality":
                page.get_by_role("combobox").last.click()
                page.get_by_role("option").filter(has_text="Test końcowy").click()
            page.wait_for_timeout(1500)
            if page.get_by_test_id("stException").count():
                raise RuntimeError(page.get_by_test_id("stException").inner_text())
            page.screenshot(path=str(screenshots / f"{name}.png"), full_page=True)
        for label, filename in [
            ("Eksport dzienny · CSV", "inventory_sample.csv"),
            ("Eksport z parametrami · JSON", "inventory_sample.json"),
        ]:
            with page.expect_download() as download_info:
                page.get_by_role("button", name=label).click()
            download_info.value.save_as(str(exports / filename))
        payload = json.loads((exports / "inventory_sample.json").read_text(encoding="utf-8"))
        assert payload, "Empty simulator export"
        page.set_viewport_size({"width": 768, "height": 1024})
        page.wait_for_timeout(500)
        page.screenshot(path=str(ROOT / "output/mobile_simulator.png"), full_page=True)
        if errors:
            raise RuntimeError(errors)
        (ROOT / "reports/browser_check.json").write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "screenshots": ["forecast.png", "quality.png", "simulator.png"],
                    "downloaded": ["inventory_sample.csv", "inventory_sample.json"],
                    "desktop_viewport": [1440, 1150],
                    "small_viewport": [768, 1024],
                    "javascript_errors": errors,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        browser.close()


if __name__ == "__main__":
    capture()
