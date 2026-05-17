"""Unit tests for VDR completeness gate (Plan 06 / REQ-02)."""
from __future__ import annotations

from orchestra_tprm.graph import (
    _DRL_CATEGORIES,
    _DRL_KEYWORDS,
    _vdr_completeness_check,
)


def test_drl_categories_and_keywords_match() -> None:
    """The 6 DRL categories and the keyword table cover the same set."""
    assert len(_DRL_CATEGORIES) == 6
    assert set(_DRL_CATEGORIES) == set(_DRL_KEYWORDS.keys())
    # Locked categories from CONTEXT.md VDR Completeness Gate
    assert set(_DRL_CATEGORIES) == {
        "financial_statements",
        "legal_corporate",
        "ip_assignments",
        "security_pentest",
        "cap_table",
        "tax_returns",
    }


def test_all_categories_present_emits_no_findings() -> None:
    """A manifest covering every DRL category produces zero missing-category Findings."""
    manifest = [
        {"path": "income_statement.pdf", "kind": "financial_filing"},
        {"path": "articles_of_incorporation.pdf", "kind": "contract"},
        {"path": "ip_assignment_2024.pdf", "kind": "contract"},
        {"path": "pentest_report.pdf", "kind": "security_attestation"},
        {"path": "cap_table_2024.xlsx", "kind": "unknown"},
        {"path": "tax_return_form_1120.pdf", "kind": "unknown"},
    ]
    missing = _vdr_completeness_check(manifest)
    assert missing == []


def test_empty_manifest_emits_six_findings() -> None:
    """Empty manifest → one informational Finding per DRL category."""
    missing = _vdr_completeness_check([])
    assert len(missing) == 6
    categories = {f.category for f in missing}
    assert categories == {
        "vdr-missing-financial-statements",
        "vdr-missing-legal-corporate",
        "vdr-missing-ip-assignments",
        "vdr-missing-security-pentest",
        "vdr-missing-cap-table",
        "vdr-missing-tax-returns",
    }
    for f in missing:
        assert f.severity == "low"
        assert f.workstream == "legal"
        assert f.ic_decision == "post-close-monitoring"
        assert f.agent == "VDRGate"


def test_partial_manifest_emits_only_missing_findings() -> None:
    """Only the absent categories produce Findings."""
    manifest = [
        {"path": "income_statement_2024.pdf", "kind": "financial_filing"},
        {"path": "pentest_report.pdf", "kind": "security_attestation"},
    ]
    missing = _vdr_completeness_check(manifest)
    cats = {f.category for f in missing}
    # Financial statements + security pentest are present → not in missing
    assert "vdr-missing-financial-statements" not in cats
    assert "vdr-missing-security-pentest" not in cats
    # Remaining four are missing
    assert "vdr-missing-legal-corporate" in cats
    assert "vdr-missing-ip-assignments" in cats
    assert "vdr-missing-cap-table" in cats
    assert "vdr-missing-tax-returns" in cats
    assert len(missing) == 4
