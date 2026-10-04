"""Opt-in browser smoke of an existing Completed run; no analysis or paid API."""

import argparse
import csv
import json
import os
import threading
import time
import traceback
from pathlib import Path

from gamingcreator.ui.server import create_server


def wait_for(page, expression: str, timeout: int = 30000) -> None:
    """Poll through the debugger, without requiring unsafe-eval in the page CSP."""
    deadline = time.monotonic() + timeout / 1000
    while not page.evaluate(expression):
        if time.monotonic() >= deadline:
            raise AssertionError(f"UI condition timed out: {expression}")
        page.wait_for_timeout(50)


def validate(project: Path, run_id: str, output: Path, query: str) -> dict[str, object]:
    from playwright.sync_api import sync_playwright

    repository = Path(__file__).resolve().parents[1]
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(repository / ".tools/browsers")
    output.mkdir(parents=True, exist_ok=True)
    server = create_server("127.0.0.1", 0, repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    project_reference = project.resolve().relative_to(repository).as_posix()
    errors: list[str] = []
    try:
        with sync_playwright() as driver:
            browser = driver.chromium.launch(headless=True, channel="chromium")
            try:
                context = browser.new_context(
                    viewport={"width": 1600, "height": 1080}, accept_downloads=True
                )
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(url, wait_until="domcontentloaded")
                wait_for(
                    page,
                    "!document.querySelector('#project-select').disabled && document.querySelector('#run-select').options.length > 0",
                )
                page.locator("#project-select").select_option(project_reference)
                wait_for(
                    page,
                    "document.querySelector('#run-select').options.length > 0 && !document.querySelector('#run-select').disabled",
                )
                page.locator("#run-select").select_option(run_id)
                wait_for(
                    page,
                    "!document.querySelector('#search-button').disabled && document.querySelectorAll('.timeline-row').length > 0",
                )
                wait_for(
                    page, "document.querySelector('#source-video').readyState >= 2", timeout=30000
                )
                event_count = page.locator(".timeline-row").count()
                page.locator("#query").fill(query)
                page.locator("#top").fill("3")
                page.locator("#search-button").click()
                wait_for(
                    page,
                    "!document.querySelector('#search-button').disabled && document.querySelectorAll('.candidate-card').length > 0",
                    timeout=30000,
                )
                candidate_count = page.locator(".candidate-card").count()
                first = page.locator(".candidate-card").first
                first.locator(".clip-preview").click()
                wait_for(
                    page,
                    "document.querySelector('#source-video').paused && document.querySelector('#source-video').currentTime > 0",
                    timeout=10000,
                )
                played = page.locator("#source-video").evaluate(
                    "video => ({time:video.currentTime,duration:video.duration,paused:video.paused})"
                )
                wait_for(
                    page,
                    "Array.from(document.querySelectorAll('#evidence-list img')).some(image=>image.complete && image.naturalWidth>0)",
                )
                first.locator(".select-clip").click()
                wait_for(page, "!document.querySelector('#export-json').disabled")
                with page.expect_download() as download:
                    page.locator("#export-json").click()
                json_path = output / "selected-clips.json"
                download.value.save_as(json_path)
                selected = json.loads(json_path.read_text(encoding="utf-8"))
                assert selected["runId"] == run_id and selected["mediaSha256"]
                assert len(selected["selectedClips"]) == 1
                clip = selected["selectedClips"][0]
                assert clip["evidenceIds"] and clip["startUs"] < clip["endUs"]
                assert (
                    clip["startUs"] / 1_000_000
                    <= played["time"]
                    <= clip["endUs"] / 1_000_000 + 0.15
                )
                assert played["paused"]
                with page.expect_download() as download:
                    page.locator("#export-csv").click()
                csv_path = output / "selected-clips.csv"
                download.value.save_as(csv_path)
                with csv_path.open(encoding="utf-8-sig", newline="") as source:
                    rows = list(csv.DictReader(source))
                assert len(rows) == 1 and int(rows[0]["startUs"]) == clip["startUs"]
                page.locator("#timeline-filter").fill("不存在的事件-UI验证")
                assert page.locator(".timeline-row").count() == 0
                assert page.locator(".candidate-card").count() == candidate_count
                page.locator("#timeline-filter").fill("")
                page.screenshot(path=str(output / "workspace.png"), full_page=True)
                page.locator("#query").fill("汽车修理工拆卸发动机维修车辆")
                page.locator("#search-button").click()
                wait_for(
                    page,
                    "!document.querySelector('#search-button').disabled && document.querySelector('#candidate-count').textContent==='0'",
                )
                assert page.locator(".candidate-card").count() == 0
                page.reload(wait_until="domcontentloaded")
                wait_for(page, "!document.querySelector('#search-button').disabled")
                # The workspace defaults to the first completed run. Select the same
                # identity before asserting that its isolated basket was restored.
                page.locator("#project-select").select_option(project_reference)
                wait_for(page, "!document.querySelector('#run-select').disabled")
                page.locator("#run-select").select_option(run_id)
                wait_for(page, "!document.querySelector('#search-button').disabled")
                assert page.locator("#selection-count").inner_text() == "1", "run basket lost"
                assert not page.locator("#export-json").is_disabled()
                assert not errors, errors
                return {
                    "passed": True,
                    "runId": run_id,
                    "project": project_reference,
                    "eventCount": event_count,
                    "candidateCount": candidate_count,
                    "preview": played,
                    "selectedClip": clip,
                    "evidenceImageLoaded": True,
                    "jsonCsvVerified": True,
                    "filterPreservesRanking": True,
                    "negativeCandidates": 0,
                    "selectionSurvivesReload": True,
                    "browserErrors": errors,
                    "browserVersion": browser.version,
                    "qualityGate": None,
                    "limitations": [
                        "development footage, not independent human acceptance",
                        "source clock/browser offset not validated for all containers",
                    ],
                }
            finally:
                browser.close()
    finally:
        server.shutdown()
        thread.join(5)
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/inspection-ui-validation"))
    parser.add_argument("--query", default="寻找角色打斗和攻击的片段")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        report = validate(args.project, args.run, args.output, args.query)
    except Exception as error:
        report = {
            "passed": False,
            "error": str(error),
            "errorType": type(error).__name__,
            "traceback": traceback.format_exc(),
            "qualityGate": None,
        }
    (args.output / "browser-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {"passed": report["passed"], "report": str(args.output / "browser-report.json")},
            ensure_ascii=False,
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
