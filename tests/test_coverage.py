"""Tests for coverage registry, gap analyzer, and scorer."""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.coverage.gap_analyzer import analyze_gaps
from src.coverage.registry import CoverageRegistryManager
from src.coverage.scorer import calculate_coverage_summary
from src.models.coverage import (
    CategoryCoverage,
    CoverageRegistry,
    GlobalCoverageStats,
    PageCoverage,
    SignatureRecord,
    TestResultSummary,
)
from src.models.site_model import PageModel, SiteModel
from src.models.test_result import Evidence, RunResult, TestResult


# ============================================================================
# CoverageRegistryManager
# ============================================================================


class TestCoverageRegistryManager:
    """Tests for loading, saving, and updating the coverage registry."""

    def test_load_creates_new_when_missing(self, tmp_path):
        path = tmp_path / "coverage" / "registry.json"
        mgr = CoverageRegistryManager(path, target_url="https://example.com")
        registry = mgr.load()
        assert registry.target_url == "https://example.com"
        assert len(registry.pages) == 0

    def test_load_returns_saved_data(self, tmp_path):
        path = tmp_path / "registry.json"
        mgr = CoverageRegistryManager(path, target_url="https://example.com")

        registry = CoverageRegistry(target_url="https://example.com")
        registry.pages["p1"] = PageCoverage(page_id="p1", url="https://example.com/", test_count=5)
        mgr.save(registry)

        loaded = mgr.load()
        assert loaded.target_url == "https://example.com"
        assert "p1" in loaded.pages
        assert loaded.pages["p1"].test_count == 5

    def test_save_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "registry.json"
        mgr = CoverageRegistryManager(path, target_url="https://example.com")
        registry = CoverageRegistry(target_url="https://example.com")
        mgr.save(registry)
        assert path.exists()

    def test_save_sets_last_updated(self, tmp_path):
        path = tmp_path / "registry.json"
        mgr = CoverageRegistryManager(path, target_url="https://example.com")
        registry = CoverageRegistry(target_url="https://example.com")
        mgr.save(registry)
        assert registry.last_updated != ""

    def test_load_handles_corrupt_file(self, tmp_path):
        path = tmp_path / "registry.json"
        path.write_text("not valid json {{{")
        mgr = CoverageRegistryManager(path, target_url="https://example.com")
        registry = mgr.load()
        # Should fallback to a fresh registry
        assert registry.target_url == "https://example.com"
        assert len(registry.pages) == 0

    def test_roundtrip_preserves_data(self, tmp_path):
        path = tmp_path / "registry.json"
        mgr = CoverageRegistryManager(path, target_url="https://example.com")

        registry = CoverageRegistry(target_url="https://example.com")
        registry.pages["p1"] = PageCoverage(
            page_id="p1", url="https://example.com/",
            categories={
                "functional": CategoryCoverage(
                    category="functional",
                    signatures_tested=[
                        SignatureRecord(signature="login_test", last_result="pass", test_count=3),
                    ],
                    coverage_score=1.0,
                ),
            },
            test_count=3,
        )
        mgr.save(registry)
        loaded = mgr.load()

        assert loaded.pages["p1"].categories["functional"].signatures_tested[0].signature == "login_test"
        assert loaded.pages["p1"].categories["functional"].signatures_tested[0].test_count == 3


class TestUpdateFromRun:
    """Tests for CoverageRegistryManager.update_from_run()."""

    def _make_run_result(self, test_results: list[TestResult]) -> RunResult:
        return RunResult(
            run_id="run_abc123",
            plan_id="plan-001",
            started_at="2025-01-01T00:00:00Z",
            completed_at="2025-01-01T00:05:00Z",
            target_url="https://example.com",
            total_tests=len(test_results),
            passed=sum(1 for r in test_results if r.result == "pass"),
            failed=sum(1 for r in test_results if r.result == "fail"),
            test_results=test_results,
        )

    def test_creates_page_entry_for_new_page(self, tmp_path):
        path = tmp_path / "registry.json"
        mgr = CoverageRegistryManager(path, target_url="https://example.com")
        registry = CoverageRegistry(target_url="https://example.com")

        tr = TestResult(
            test_id="tc_001", test_name="Login test",
            category="functional", result="pass",
            target_page_id="page-login",
            coverage_signature="login_submit",
        )
        run_result = self._make_run_result([tr])
        updated = mgr.update_from_run(registry, run_result)

        assert "page-login" in updated.pages
        assert updated.pages["page-login"].test_count == 1

    def test_prefers_actual_page_id_over_target(self, tmp_path):
        path = tmp_path / "registry.json"
        mgr = CoverageRegistryManager(path, target_url="https://example.com")
        registry = CoverageRegistry(target_url="https://example.com")

        tr = TestResult(
            test_id="tc_001", test_name="Login redirects to dashboard",
            category="functional", result="pass",
            target_page_id="page-login",
            actual_page_id="page-dashboard",
            actual_url="https://example.com/dashboard",
            coverage_signature="login_redirect",
        )
        run_result = self._make_run_result([tr])
        updated = mgr.update_from_run(registry, run_result)

        # Should use actual_page_id, not target_page_id
        assert "page-dashboard" in updated.pages
        assert "page-login" not in updated.pages

    def test_updates_existing_signature(self, tmp_path):
        path = tmp_path / "registry.json"
        mgr = CoverageRegistryManager(path, target_url="https://example.com")

        # Pre-populate with an existing signature
        registry = CoverageRegistry(target_url="https://example.com")
        registry.pages["p1"] = PageCoverage(
            page_id="p1", url="https://example.com/",
            categories={
                "functional": CategoryCoverage(
                    category="functional",
                    signatures_tested=[
                        SignatureRecord(signature="login_submit", last_result="pass", test_count=2),
                    ],
                ),
            },
            test_count=2,
        )

        tr = TestResult(
            test_id="tc_001", test_name="Login test",
            category="functional", result="fail",
            target_page_id="p1",
            coverage_signature="login_submit",
        )
        run_result = self._make_run_result([tr])
        updated = mgr.update_from_run(registry, run_result)

        sig = updated.pages["p1"].categories["functional"].signatures_tested[0]
        assert sig.test_count == 3
        assert sig.last_result == "fail"

    def test_adds_new_signature(self, tmp_path):
        path = tmp_path / "registry.json"
        mgr = CoverageRegistryManager(path, target_url="https://example.com")
        registry = CoverageRegistry(target_url="https://example.com")

        tr = TestResult(
            test_id="tc_001", test_name="Search test",
            category="functional", result="pass",
            target_page_id="page-search",
            coverage_signature="search_query",
        )
        run_result = self._make_run_result([tr])
        updated = mgr.update_from_run(registry, run_result)

        sigs = updated.pages["page-search"].categories["functional"].signatures_tested
        assert len(sigs) == 1
        assert sigs[0].signature == "search_query"

    def test_falls_back_to_test_name_when_no_signature(self, tmp_path):
        path = tmp_path / "registry.json"
        mgr = CoverageRegistryManager(path, target_url="https://example.com")
        registry = CoverageRegistry(target_url="https://example.com")

        tr = TestResult(
            test_id="tc_001", test_name="My special test",
            category="functional", result="pass",
            target_page_id="p1",
            coverage_signature="",  # empty
        )
        run_result = self._make_run_result([tr])
        updated = mgr.update_from_run(registry, run_result)

        sigs = updated.pages["p1"].categories["functional"].signatures_tested
        assert sigs[0].signature == "My special test"

    def test_history_retention_trims_old_entries(self, tmp_path):
        path = tmp_path / "registry.json"
        mgr = CoverageRegistryManager(path, target_url="https://example.com", history_retention=3)
        registry = CoverageRegistry(target_url="https://example.com")

        # Add same test 5 times (exceeding retention of 3)
        for i in range(5):
            tr = TestResult(
                test_id=f"tc_{i}", test_name="Repeated test",
                category="functional", result="pass",
                target_page_id="p1",
                coverage_signature="repeated_sig",
            )
            run_result = self._make_run_result([tr])
            registry = mgr.update_from_run(registry, run_result)

        sig = registry.pages["p1"].categories["functional"].signatures_tested[0]
        assert len(sig.history) == 3  # Trimmed to retention limit

    def test_recalculates_global_stats(self, tmp_path):
        path = tmp_path / "registry.json"
        mgr = CoverageRegistryManager(path, target_url="https://example.com")
        registry = CoverageRegistry(target_url="https://example.com")

        tests = [
            TestResult(
                test_id="tc_1", test_name="Pass test", category="functional",
                result="pass", target_page_id="p1", coverage_signature="sig1",
            ),
            TestResult(
                test_id="tc_2", test_name="Fail test", category="functional",
                result="fail", target_page_id="p1", coverage_signature="sig2",
            ),
        ]
        run_result = self._make_run_result(tests)
        updated = mgr.update_from_run(registry, run_result)

        stats = updated.global_stats
        assert stats.total_pages == 1
        assert stats.pages_tested == 1
        assert stats.overall_score == 0.5  # 1 pass / 2 total

    def test_regression_counting(self, tmp_path):
        path = tmp_path / "registry.json"
        mgr = CoverageRegistryManager(path, target_url="https://example.com")
        registry = CoverageRegistry(target_url="https://example.com")

        # Run 1: pass
        tr1 = TestResult(
            test_id="tc_1", test_name="Test", category="functional",
            result="pass", target_page_id="p1", coverage_signature="sig",
        )
        registry = mgr.update_from_run(registry, self._make_run_result([tr1]))

        # Run 2: fail (regression)
        tr2 = TestResult(
            test_id="tc_1", test_name="Test", category="functional",
            result="fail", target_page_id="p1", coverage_signature="sig",
        )
        registry = mgr.update_from_run(registry, self._make_run_result([tr2]))

        assert registry.global_stats.regression_count == 1

    def test_uses_actual_url_when_not_in_site_model(self, tmp_path):
        path = tmp_path / "registry.json"
        mgr = CoverageRegistryManager(path, target_url="https://example.com")
        registry = CoverageRegistry(target_url="https://example.com")

        tr = TestResult(
            test_id="tc_001", test_name="Dynamic page test",
            category="functional", result="pass",
            target_page_id="page-dynamic",
            actual_url="https://example.com/dynamic",
            coverage_signature="dynamic_test",
        )
        run_result = self._make_run_result([tr])
        updated = mgr.update_from_run(registry, run_result)

        assert updated.pages["page-dynamic"].url == "https://example.com/dynamic"

    def test_uses_site_model_page_metadata(self, tmp_path):
        path = tmp_path / "registry.json"
        mgr = CoverageRegistryManager(path, target_url="https://example.com")
        registry = CoverageRegistry(target_url="https://example.com")

        site_model = SiteModel(
            base_url="https://example.com",
            pages=[PageModel(
                page_id="page-login", url="https://example.com/login",
                page_type="form", title="Login",
            )],
        )

        tr = TestResult(
            test_id="tc_001", test_name="Login test",
            category="functional", result="pass",
            target_page_id="page-login",
            coverage_signature="login_sig",
        )
        run_result = self._make_run_result([tr])
        updated = mgr.update_from_run(registry, run_result, site_model=site_model)

        assert updated.pages["page-login"].url == "https://example.com/login"
        assert updated.pages["page-login"].page_type == "form"


# ============================================================================
# Gap Analyzer
# ============================================================================


class TestGapAnalyzer:
    """Tests for the coverage gap analyzer."""

    def _make_site_model(self, page_ids: list[str]) -> SiteModel:
        return SiteModel(
            base_url="https://example.com",
            pages=[PageModel(page_id=pid, url=f"https://example.com/{pid}", title=pid)
                   for pid in page_ids],
        )

    def test_untested_pages_detected(self):
        registry = CoverageRegistry(target_url="https://example.com")
        site_model = self._make_site_model(["p1", "p2", "p3"])

        report = analyze_gaps(registry, site_model)

        assert set(report.untested_pages) == {"p1", "p2", "p3"}

    def test_no_gaps_when_fully_tested(self):
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        registry = CoverageRegistry(target_url="https://example.com")
        registry.pages["p1"] = PageCoverage(
            page_id="p1", url="https://example.com/p1",
            last_tested=now, test_count=1,
            categories={"functional": CategoryCoverage(
                category="functional", coverage_score=0.8,
                signatures_tested=[SignatureRecord(signature="s", last_result="pass")],
            )},
        )
        site_model = self._make_site_model(["p1"])

        report = analyze_gaps(registry, site_model)

        assert report.untested_pages == []

    def test_stale_pages_detected(self):
        old_date = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        registry = CoverageRegistry(target_url="https://example.com")
        registry.pages["p1"] = PageCoverage(
            page_id="p1", url="https://example.com/p1",
            last_tested=old_date, test_count=1,
        )
        site_model = self._make_site_model(["p1"])

        report = analyze_gaps(registry, site_model, staleness_days=7)

        assert "p1" in report.stale_pages

    def test_low_coverage_detected(self):
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        registry = CoverageRegistry(target_url="https://example.com")
        registry.pages["p1"] = PageCoverage(
            page_id="p1", url="https://example.com/p1",
            last_tested=now, test_count=1,
            categories={"functional": CategoryCoverage(
                category="functional", coverage_score=0.2,
                signatures_tested=[SignatureRecord(signature="s", last_result="fail")],
            )},
        )
        site_model = self._make_site_model(["p1"])

        report = analyze_gaps(registry, site_model, low_coverage_threshold=0.5)

        assert len(report.low_coverage_areas) == 1
        assert report.low_coverage_areas[0] == ("p1", "functional", 0.2)

    def test_recent_failures_detected(self):
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        registry = CoverageRegistry(target_url="https://example.com")
        registry.pages["p1"] = PageCoverage(
            page_id="p1", url="https://example.com/p1",
            last_tested=now, test_count=1,
            categories={"functional": CategoryCoverage(
                category="functional", coverage_score=0.0,
                signatures_tested=[
                    SignatureRecord(signature="login_fail", last_result="fail"),
                ],
            )},
        )
        site_model = self._make_site_model(["p1"])

        report = analyze_gaps(registry, site_model)

        assert ("p1", "login_fail") in report.recent_failures

    def test_suggested_focus_includes_all_issues(self):
        old_date = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        registry = CoverageRegistry(target_url="https://example.com")
        registry.pages["p1"] = PageCoverage(
            page_id="p1", url="https://example.com/p1",
            last_tested=old_date, test_count=1,
            categories={"functional": CategoryCoverage(
                category="functional", coverage_score=0.1,
                signatures_tested=[SignatureRecord(signature="s", last_result="fail")],
            )},
        )
        site_model = self._make_site_model(["p1", "p2"])

        report = analyze_gaps(registry, site_model)

        assert len(report.suggested_focus) >= 3  # untested, failures, stale


# ============================================================================
# Coverage Scorer
# ============================================================================


class TestCoverageScorer:
    """Tests for calculate_coverage_summary."""

    def test_basic_summary(self):
        registry = CoverageRegistry(target_url="https://example.com")
        registry.global_stats = GlobalCoverageStats(
            total_pages=10, pages_tested=7,
            overall_score=0.75,
            category_scores={"functional": 0.8, "visual": 0.7},
            last_full_run="2025-01-01T00:00:00Z",
        )

        summary = calculate_coverage_summary(registry)

        assert "https://example.com" in summary
        assert "7/10" in summary
        assert "75%" in summary
        assert "Functional" in summary
        assert "Visual" in summary

    def test_shows_regressions(self):
        registry = CoverageRegistry(target_url="https://example.com")
        registry.global_stats = GlobalCoverageStats(
            total_pages=5, pages_tested=5,
            overall_score=0.9,
            regression_count=2,
        )

        summary = calculate_coverage_summary(registry)
        assert "Regressions: 2" in summary

    def test_no_regressions_omitted(self):
        registry = CoverageRegistry(target_url="https://example.com")
        registry.global_stats = GlobalCoverageStats(
            total_pages=5, pages_tested=5,
            overall_score=1.0,
            regression_count=0,
        )

        summary = calculate_coverage_summary(registry)
        assert "Regression" not in summary

    def test_empty_registry(self):
        registry = CoverageRegistry(target_url="https://example.com")
        summary = calculate_coverage_summary(registry)
        assert "0/0" in summary
