"""One retained Historical Analysis functional slice in the headed QA harness."""

from __future__ import annotations

import argparse
import json
import sqlite3
import traceback
from importlib.metadata import version
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

from scripts.validation.browser.post14b_qa_launcher import (
    prepare_qa_root, start_qa_server, stop_qa_server,
)
from scripts.validation.browser.system_browser import (
    attach_page_event_capture, detach_page_event_capture,
    launch_system_browser_session, save_screenshot,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-kind", choices=("DEFAULT", "LEGACY_TRAINABLE"),
                        default="DEFAULT")
    args = parser.parse_args()
    trainable = args.fixture_kind == "LEGACY_TRAINABLE"
    root = prepare_qa_root(fixture_kind=args.fixture_kind)
    print(f"Retained QA root: {root}", flush=True)
    process = None
    report = {"scope": "RETAINED_COMPONENT_HARNESS_HISTORICAL_SLICE",
              "status": "NOT_RUN", "qa_root": str(root), "headless": False,
              "fixture_kind": args.fixture_kind}
    try:
        process, port = start_qa_server(root)
        report["loopback_port"] = port
        database = root / "state" / "qa.db"
        with sqlite3.connect(database) as connection:
            expected_people = connection.execute(
                "SELECT COUNT(DISTINCT customer_id) FROM campaign_sales "
                + ("WHERE campaign_id LIKE 'CMP_TRAIN_%'" if trainable else "")
            ).fetchone()[0]
            before = connection.execute("SELECT COUNT(*) FROM historical_analysis_runs").fetchone()[0]
        assert expected_people == (300 if trainable else 230) and before == 0
        responses = []
        with sync_playwright() as playwright:
            with launch_system_browser_session(
                playwright, system_browser="chrome", headless=False,
                viewport={"width": 1366, "height": 768},
                profile_dir=root / "browser_profile", downloads_dir=root / "downloads",
            ) as session:
                page = session.page
                page.set_default_timeout(20_000)
                capture, listeners = attach_page_event_capture(page)

                def on_response(response):
                    path = urlsplit(response.url).path
                    if path.startswith("/api/"):
                        responses.append({"method": response.request.method,
                                          "path": path, "status": response.status})

                page.on("response", on_response)
                try:
                    page.goto(f"http://127.0.0.1:{port}/qa-retained#historical-analysis",
                              wait_until="domcontentloaded")
                    page.wait_for_function(
                        "() => location.pathname === '/qa-retained' && "
                        "document.querySelector('#page-title')?.textContent === 'Historical Analysis' && "
                        "!document.querySelector('#historical-analysis-view')?.hidden",
                        timeout=20_000,
                    )
                    page.locator("#historical-analysis-workspace").wait_for(
                        state="visible", timeout=30_000)
                    assert page.locator("#contact-date-from").input_value()
                    assert page.locator("#contact-date-to").input_value()
                    page.locator("#historical-analysis-reset").click()
                    page.locator("#analysis-name").fill("Bounded native historical P1-P3")
                    if trainable:
                        training_campaigns = page.locator("#campaign-filter").evaluate(
                            "e => [...e.options].map(o => o.value).filter(v => v.startsWith('CMP_TRAIN_'))")
                        assert len(training_campaigns) == 10
                        page.locator("#campaign-filter").select_option(training_campaigns)
                    page.locator('input[name="conversion_definition"][value="ANY_PURCHASE"]').check()
                    save_screenshot(page, root / "screenshots" / "historical_form.png")
                    page.locator("#analyze-population").click()
                    page.wait_for_function(
                        "() => document.querySelector('#analysis-results-status')?.textContent.trim()"
                        ".toUpperCase() === 'COMPLETED' && /[1-9]/.test("
                        "document.querySelector('#result-run-id')?.textContent || '')",
                        timeout=120_000,
                    )
                    run_id_text = page.locator("#result-run-id").inner_text()
                    run_id = int("".join(ch for ch in run_id_text if ch.isdigit()))
                    assert page.locator("#result-selected").inner_text().strip() == str(expected_people)
                    with sqlite3.connect(database) as connection:
                        row = connection.execute(
                            "SELECT status,conversion_definition,observation_count,"
                            "selected_customer_count,positive_customer_count "
                            "FROM historical_analysis_runs WHERE analysis_run_id=?",
                            (run_id,),
                        ).fetchone()
                    assert row is not None and row[0] == "COMPLETED"
                    assert row[1] == "ANY_PURCHASE" and row[3] == expected_people
                    assert row[2] == (300 if trainable else 640)
                    assert row[4] == (100 if trainable else 230)
                    assert any(r["method"] == "POST" and r["path"] == "/api/historical/analyses"
                               and r["status"] == 201 for r in responses)
                    page.locator("#recent-analyses-body .recent-reopen").first.click()
                    page.wait_for_function(
                        "id => document.querySelector('#result-run-id')?.textContent.includes(String(id))",
                        arg=run_id,
                    )
                    tabs = page.locator("#analysis-breakdown-tabs [role='tab']")
                    assert tabs.count() >= 2
                    for tab in tabs.all():
                        tab.click()
                        assert tab.get_attribute("aria-selected") == "true"
                    save_screenshot(page, root / "screenshots" / "historical_result.png")
                    page.goto(f"http://127.0.0.1:{port}/qa-retained#model-training",
                              wait_until="domcontentloaded")
                    page.wait_for_function(
                        "() => document.querySelector('#page-title')?.textContent"
                        " === 'Model Training & Prospect Scoring' && "
                        "!document.querySelector('#model-training-view')?.hidden",
                        timeout=20_000,
                    )
                    page.locator("#model-training-workspace").wait_for(state="visible", timeout=30_000)
                    page.locator("#source-analysis-select").select_option(str(run_id))
                    page.locator("#model-name-input").fill(
                        "Bounded legacy trainable" if trainable else "Bounded one-component negative")
                    assert page.locator("#source-unlabeled-count").inner_text().strip() == (
                        "200" if trainable else "0")
                    page.locator("#train-model-submit").click()
                    page.locator("#model-job-content").wait_for(state="visible", timeout=30_000)
                    page.wait_for_function(
                        "() => ['FAILED','COMPLETED'].includes("
                        "document.querySelector('#model-job-status')?.textContent.trim().toUpperCase())",
                        timeout=120_000,
                    )
                    model_job_status = page.locator("#model-job-status").inner_text().strip().upper()
                    assert model_job_status == ("COMPLETED" if trainable else "FAILED")
                    model_failure = page.locator("#model-job-failure").inner_text().strip()
                    with sqlite3.connect(database) as connection:
                        model_jobs = connection.execute(
                            "SELECT COUNT(*) FROM jobs WHERE job_type='MODEL_TRAINING' AND status=?",
                            (model_job_status,),
                        ).fetchone()[0]
                        model_rows = connection.execute(
                            "SELECT status,error_message FROM model_runs ORDER BY model_run_id"
                        ).fetchall()
                        scoring_runs = connection.execute("SELECT COUNT(*) FROM scoring_runs").fetchone()[0]
                    assert model_jobs == 1 and scoring_runs == 0
                    assert len(model_rows) == 1 and model_rows[0][0] == model_job_status
                    if trainable:
                        assert not model_rows[0][1]
                        save_screenshot(page, root / "screenshots" / "model_trainable_result.png")
                        page.locator("#prospect-scoring-panel").wait_for(state="visible", timeout=30_000)
                        page.wait_for_function(
                            "() => { const button = document.querySelector('#score-prospect-submit');"
                            " return button && !button.disabled && !button.hidden; }",
                            timeout=30_000,
                        )
                        assert page.locator("#scoring-demographic-count").inner_text().strip() == "200"
                        prior_job_id = page.locator("#model-job-id").inner_text().strip()
                        page.locator("#score-prospect-submit").click()
                        page.wait_for_function(
                            "prior => { const job = document.querySelector('#model-job-id')?.textContent.trim();"
                            " const status = document.querySelector('#model-job-status')?.textContent.trim().toUpperCase();"
                            " return job && job !== prior && ['COMPLETED','FAILED'].includes(status); }",
                            arg=prior_job_id, timeout=180_000,
                        )
                        scoring_job_status = page.locator("#model-job-status").inner_text().strip().upper()
                        assert scoring_job_status == "COMPLETED"
                        page.locator("#scoring-completed-summary").wait_for(state="visible", timeout=30_000)
                        assert page.locator("#scoring-summary-scored-count").inner_text().strip() == "200"
                        with sqlite3.connect(database) as connection:
                            scored = connection.execute(
                                "SELECT status,demographic_snapshot_count,scored_person_count "
                                "FROM scoring_runs"
                            ).fetchall()
                        assert scored == [("COMPLETED", 200, 200)]
                        save_screenshot(page, root / "screenshots" / "model_bounded_scoring_result.png")
                        page.goto(f"http://127.0.0.1:{port}/qa-retained#audience-explorer",
                                  wait_until="domcontentloaded")
                        page.wait_for_function(
                            "() => document.querySelector('#page-title')?.textContent"
                            " === 'Audience Explorer' && !document.querySelector('#audience-explorer-view')?.hidden",
                            timeout=20_000,
                        )
                        page.wait_for_function(
                            "() => !document.querySelector('#audience-explorer-prep-needed')?.hidden || "
                            "!document.querySelector('#audience-explorer-workspace')?.hidden",
                            timeout=30_000,
                        )
                        if page.locator("#audience-explorer-prep-needed").is_visible():
                            page.locator("#audience-prepare-submit").click()
                        page.locator("#audience-explorer-workspace").wait_for(
                            state="visible", timeout=180_000)
                        assert page.locator("#audience-context-population").inner_text().strip() == "200"
                        page.locator("#audience-apply-filters").click()
                        page.wait_for_function(
                            "() => document.querySelector('#audience-estimate-matching')?.textContent.trim()"
                            " === '200' && document.querySelector('#audience-estimate-selected')?.textContent.trim()"
                            " === '200'",
                            timeout=60_000,
                        )
                        page.locator("#audience-save-name").fill("Bounded native ranked audience")
                        page.locator("#audience-save-submit").click()
                        page.wait_for_function(
                            "() => document.querySelector('#audience-save-status')?.textContent.startsWith('Saved audience #')",
                            timeout=60_000,
                        )
                        with sqlite3.connect(database) as connection:
                            audiences = connection.execute(
                                "SELECT selection_mode,resolved_count FROM saved_audiences"
                            ).fetchall()
                        assert audiences == [("ALL_MATCHING", 200)]
                        save_screenshot(page, root / "screenshots" / "audience_saved.png")
                        page.wait_for_function(
                            "() => document.querySelectorAll('#audience-results-body tr').length === 50 "
                            "&& !document.querySelector('#audience-load-more')?.hidden",
                            timeout=30_000,
                        )
                        for expected_rows in (100, 150, 200):
                            page.locator("#audience-load-more").click()
                            page.wait_for_function(
                                "count => document.querySelectorAll('#audience-results-body tr').length === count",
                                arg=expected_rows, timeout=30_000,
                            )
                        assert page.locator("#audience-load-more").is_hidden()
                        result_people = page.locator("#audience-results-body tr td:nth-child(5)").all_inner_texts()
                        assert len(result_people) == len(set(result_people)) == 200
                        page.wait_for_function(
                            "() => !document.querySelector('#audience-profile-summary')?.textContent"
                            ".includes('Loading exact profile aggregates')",
                            timeout=30_000,
                        )
                        profile_dimensions = page.locator("#audience-profile-dimension option").count()
                        assert profile_dimensions >= 2
                        page.locator("#audience-profile-dimension").select_option(index=1)
                        profile_tabs = page.locator("#audience-profile-comparison-tabs [role='tab']")
                        assert profile_tabs.count() == 2
                        for tab in profile_tabs.all():
                            tab.click()
                            assert tab.get_attribute("aria-selected") == "true"
                        estimate_posts = sum(
                            r["method"] == "POST" and r["path"].endswith("/estimate")
                            for r in responses
                        )
                        page.locator("#audience-score-min").fill("0.9")
                        page.locator("#audience-score-max").fill("0.8")
                        page.locator("#audience-apply-filters").click()
                        assert "Score min cannot exceed score max" in page.locator(
                            "#audience-form-error").inner_text()
                        assert sum(
                            r["method"] == "POST" and r["path"].endswith("/estimate")
                            for r in responses
                        ) == estimate_posts
                        page.locator("#audience-filter-reset").click()
                        assert page.locator("#audience-score-min").input_value() == ""
                        page.locator("#audience-selection-topn").check()
                        assert page.locator("#audience-target-count").is_enabled()
                        page.locator("#audience-target-count").fill("10")
                        page.locator("#audience-apply-filters").click()
                        page.wait_for_function(
                            "() => document.querySelector('#audience-estimate-matching')?.textContent.trim()"
                            " === '200' && document.querySelector('#audience-estimate-selected')?.textContent.trim()"
                            " === '10'",
                            timeout=60_000,
                        )
                        page.locator("#audience-save-name").fill("Bounded native top ten")
                        page.locator("#audience-save-submit").click()
                        page.wait_for_function(
                            "() => document.querySelector('#audience-save-status')?.textContent.startsWith('Saved audience #')"
                            " && [...document.querySelectorAll('#saved-audience-list .saved-audience-item')]"
                            ".some(e => e.textContent.includes('Bounded native top ten'))",
                            timeout=60_000,
                        )
                        with sqlite3.connect(database) as connection:
                            audiences = connection.execute(
                                "SELECT selection_mode,target_count,resolved_count FROM saved_audiences "
                                "ORDER BY audience_id"
                            ).fetchall()
                        assert audiences == [("ALL_MATCHING", None, 200), ("TOP_N", 10, 10)]
                        top_n_item = page.locator("#saved-audience-list .saved-audience-item").filter(
                            has_text="Bounded native top ten")
                        top_n_item.get_by_role("button", name="View").click()
                        page.wait_for_function(
                            "() => document.querySelector('#saved-audience-detail-title')?.textContent"
                            " === 'Bounded native top ten'",
                            timeout=30_000,
                        )
                        assert "10 selected" in page.locator("#saved-audience-detail-meta").inner_text()
                        page.locator("#saved-audience-reopen").click()
                        page.wait_for_function(
                            "() => document.querySelector('#audience-estimate-selected')?.textContent.trim()"
                            " === '10' && document.querySelector('#audience-selection-topn')?.checked",
                            timeout=60_000,
                        )
                        save_screenshot(page, root / "screenshots" / "audience_top_n_reopened.png")
                        page.goto(f"http://127.0.0.1:{port}/qa-retained#saved-target-groups",
                                  wait_until="domcontentloaded")
                        page.locator("#business-target-groups-loading").wait_for(
                            state="hidden", timeout=30_000)
                        assert page.locator("#business-target-groups-list .saved-audience-item").count() == 2
                        page.locator("#business-target-groups-refresh").click()
                        page.locator("#business-target-groups-loading").wait_for(
                            state="hidden", timeout=30_000)
                        assert page.locator("#business-target-groups-list .saved-audience-item").count() == 2
                        page.locator("#business-target-groups-list .saved-audience-item").filter(
                            has_text="Bounded native top ten").get_by_role(
                            "button", name="View advanced definition").click()
                        page.wait_for_function(
                            "() => location.hash === '#audience-explorer' && "
                            "!document.querySelector('#audience-explorer-view')?.hidden",
                            timeout=30_000,
                        )
                        page.goto(f"http://127.0.0.1:{port}/qa-retained#data-status",
                                  wait_until="domcontentloaded")
                        page.wait_for_function(
                            "() => [...document.querySelectorAll('[data-dataset-card]')]"
                            ".every(e => !e.classList.contains('is-loading')) && "
                            "!document.querySelector('#import-history-body .loading-row')",
                            timeout=60_000,
                        )
                        with sqlite3.connect(database) as connection:
                            source_counts = {name: connection.execute(
                                f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                                for name in ("customers", "campaign_sales", "demographics")}
                        for name, count in source_counts.items():
                            actual = page.locator(f'[data-dataset-card="{name}"] [data-field="actual"]')
                            assert actual.inner_text().strip().replace(",", "") == str(count)
                        before_refresh = sum(
                            r["method"] == "GET" and r["path"] == "/api/data/status"
                            for r in responses
                        )
                        page.locator("#data-status-refresh").click()
                        page.wait_for_function(
                            "() => [...document.querySelectorAll('[data-dataset-card]')]"
                            ".every(e => !e.classList.contains('is-loading'))",
                            timeout=60_000,
                        )
                        assert sum(
                            r["method"] == "GET" and r["path"] == "/api/data/status"
                            for r in responses
                        ) == before_refresh + 1
                        assert page.locator("#data-status-error").is_hidden()
                        save_screenshot(page, root / "screenshots" / "data_status_counts.png")
                    else:
                        assert model_failure
                        assert "known-positive and unlabeled rows" in model_rows[0][1]
                        save_screenshot(page, root / "screenshots" / "model_one_component_block.png")
                    report.update({
                        "status": ("PASS_RETAINED_TRAINABLE_MODEL" if trainable
                                   else "PASS_RETAINED_HISTORICAL_AND_MODEL_BLOCK"),
                        "browser": session.metadata.to_dict(),
                        "playwright_version": version("playwright"),
                        "analysis_run_id": run_id, "selected_people": row[3],
                        "positive_people": row[4], "observations": row[2],
                        "breakdown_tabs_tested": tabs.count(),
                        "model_one_component_job_status": model_job_status,
                        "model_one_component_safe_failure": model_failure[:300],
                        "model_one_component_failure_category": (
                            None if trainable else "NO_UNLABELED_COMPONENT"),
                        "bounded_scoring_status": "COMPLETED" if trainable else "NOT_RUN",
                        "bounded_scored_people": 200 if trainable else 0,
                        "bounded_audience_saved_people": 200 if trainable else 0,
                        "bounded_audience_top_n_people": 10 if trainable else 0,
                        "bounded_audience_paginated_people": 200 if trainable else 0,
                        "bounded_saved_target_groups_visible": 2 if trainable else 0,
                        "bounded_data_status_counts": source_counts if trainable else {},
                        "api_responses": responses,
                        "console_errors": capture.console_errors,
                        "page_errors": capture.page_errors,
                        "request_failures": capture.request_failures,
                    })
                    assert not capture.console_errors and not capture.page_errors and not capture.request_failures
                finally:
                    detach_page_event_capture(page, listeners)
    except Exception as exc:
        report.update({"status": "FAIL_ONE_RETAINED_HISTORICAL_CASE",
                       "error_type": type(exc).__name__, "error": str(exc)[:1200],
                       "traceback": traceback.format_exc()[-3000:]})
    finally:
        if process is not None:
            stop_qa_server(process)
            report["owned_server_stopped"] = process.poll() is not None
        path = root / "native_retained_historical.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "evidence": str(path)},
                         sort_keys=True), flush=True)
    return 0 if report["status"] in {
        "PASS_RETAINED_HISTORICAL_AND_MODEL_BLOCK", "PASS_RETAINED_TRAINABLE_MODEL",
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
