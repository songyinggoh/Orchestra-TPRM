"""TPRMState merge reducer tests.

Covers every Annotated field in TPRMState and the merge mechanics provided
by orchestra.core.state. All tests are pure unit tests — no LLM, no I/O.

State fields under test
-----------------------
findings        : Annotated[list[Finding], merge_list]
packet_manifest : Annotated[list[dict], merge_list]
file_uris       : Annotated[dict[str, str], merge_dict]
routing         : Annotated[dict[str, list[str]], merge_dict]

Plain (last-write-wins) fields are tested via the round-trip group.
"""
from __future__ import annotations

from typing import Any

import pytest

from orchestra.core.state import (
    apply_state_update,
    extract_reducers,
    merge_parallel_updates,
)
from orchestra_tprm.schemas import Citation, Finding, TPRMState


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

def _finding(agent: str, category: str = "liability", severity: str = "high") -> Finding:
    """Return a minimal Finding for use in tests."""
    return Finding(
        agent=agent,
        category=category,
        severity=severity,  # type: ignore[arg-type]
        summary=f"Finding from {agent}",
    )


def _finding_with_evidence(agent: str) -> Finding:
    return Finding(
        agent=agent,
        category="contract",
        severity="medium",
        summary=f"Evidence-backed finding from {agent}",
        evidence=[Citation(file_id="msa.pdf", page=1, snippet="clause 3.1")],
        raw={"clause_id": "3.1"},
    )


def _base_state(**overrides: Any) -> TPRMState:
    """Return a clean TPRMState with optional field overrides."""
    return TPRMState(**overrides)


def _reducers() -> dict[str, Any]:
    return extract_reducers(TPRMState)


# ---------------------------------------------------------------------------
# Group 1: extract_reducers — structure assertions
# ---------------------------------------------------------------------------

class TestExtractReducers:

    def test_tprm_state_reducers_finds_all_annotated_fields(self):
        """extract_reducers must discover all four Annotated fields."""
        # Arrange
        expected = {"findings", "packet_manifest", "file_uris", "routing"}

        # Act
        reducers = _reducers()

        # Assert
        assert set(reducers.keys()) == expected

    def test_findings_reducer_is_merge_list(self):
        from orchestra.core.state import merge_list
        assert _reducers()["findings"] is merge_list

    def test_packet_manifest_reducer_is_merge_list(self):
        from orchestra.core.state import merge_list
        assert _reducers()["packet_manifest"] is merge_list

    def test_file_uris_reducer_is_merge_dict(self):
        from orchestra.core.state import merge_dict
        assert _reducers()["file_uris"] is merge_dict

    def test_routing_reducer_is_merge_dict(self):
        from orchestra.core.state import merge_dict
        assert _reducers()["routing"] is merge_dict

    def test_plain_fields_absent_from_reducers(self):
        """Fields without Annotated reducer must NOT appear in reducer map."""
        plain_fields = {"mode", "subject_name", "packet_path", "risk_score",
                        "policy_verdict", "verdict_doc_id", "verdict_local_path"}
        reducers = _reducers()
        assert plain_fields.isdisjoint(set(reducers.keys()))


# ---------------------------------------------------------------------------
# Group 2: findings — merge_list semantics
# ---------------------------------------------------------------------------

class TestFindingsMergeList:

    def test_findings_two_parallel_agents_concatenate_not_overwrite(self):
        """Two agents each appending findings must accumulate, not clobber."""
        # Arrange
        state = _base_state()
        reducers = _reducers()
        f_legal = _finding("LegalAgent")
        f_privacy = _finding("PrivacyAgent", category="privacy", severity="medium")

        # Act
        final = merge_parallel_updates(
            state,
            [{"findings": [f_legal]}, {"findings": [f_privacy]}],
            reducers,
        )

        # Assert
        assert len(final.findings) == 2
        agents = {f.agent for f in final.findings}
        assert agents == {"LegalAgent", "PrivacyAgent"}

    def test_findings_empty_branch_plus_nonempty_branch_preserves_nonempty(self):
        """An agent returning no findings must not wipe out findings from a peer."""
        # Arrange
        state = _base_state()
        reducers = _reducers()
        f = _finding("FinancialAgent", severity="critical")

        # Act
        final = merge_parallel_updates(
            state,
            [{"findings": [f]}, {"findings": []}],
            reducers,
        )

        # Assert
        assert len(final.findings) == 1
        assert final.findings[0].agent == "FinancialAgent"

    def test_findings_nonempty_branch_plus_empty_branch_preserves_nonempty(self):
        """Order independence: empty-first, then nonempty — result still correct."""
        # Arrange
        state = _base_state()
        reducers = _reducers()
        f = _finding("SecurityAgent", severity="critical")

        # Act
        final = merge_parallel_updates(
            state,
            [{"findings": []}, {"findings": [f]}],
            reducers,
        )

        # Assert
        assert len(final.findings) == 1
        assert final.findings[0].agent == "SecurityAgent"

    def test_findings_both_empty_branches_produce_empty_state(self):
        """Two empty-finding branches must leave findings list empty."""
        # Arrange
        state = _base_state()
        reducers = _reducers()

        # Act
        final = merge_parallel_updates(
            state,
            [{"findings": []}, {"findings": []}],
            reducers,
        )

        # Assert
        assert final.findings == []

    def test_findings_three_parallel_agents_all_concatenate(self):
        """Fan-out of three agents: all findings present, in order."""
        # Arrange
        state = _base_state()
        reducers = _reducers()
        agents = ["AgentA", "AgentB", "AgentC"]
        updates = [{"findings": [_finding(name)]} for name in agents]

        # Act
        final = merge_parallel_updates(state, updates, reducers)

        # Assert
        assert len(final.findings) == 3
        result_agents = [f.agent for f in final.findings]
        assert result_agents == agents  # sequential application preserves order

    def test_findings_with_evidence_and_raw_survive_merge_intact(self):
        """Finding objects with nested Citation and raw dict are preserved verbatim."""
        # Arrange
        state = _base_state()
        reducers = _reducers()
        f = _finding_with_evidence("ContractAgent")

        # Act
        final = merge_parallel_updates(state, [{"findings": [f]}], reducers)

        # Assert
        assert len(final.findings) == 1
        result = final.findings[0]
        assert result.evidence[0].file_id == "msa.pdf"
        assert result.raw["clause_id"] == "3.1"

    def test_findings_pre_existing_state_accumulates_new_findings(self):
        """Findings already in state are not reset when a new update arrives."""
        # Arrange
        existing = _finding("ExistingAgent")
        state = _base_state(findings=[existing])
        reducers = _reducers()
        incoming = _finding("NewAgent")

        # Act
        final = apply_state_update(state, {"findings": [incoming]}, reducers)

        # Assert
        assert len(final.findings) == 2
        assert {f.agent for f in final.findings} == {"ExistingAgent", "NewAgent"}

    def test_findings_duplicate_objects_both_kept(self):
        """merge_list does not deduplicate — identical findings from two agents are both kept."""
        # Arrange
        state = _base_state()
        reducers = _reducers()
        f = _finding("AgentX")

        # Act — same finding returned by two independent agents
        final = merge_parallel_updates(
            state,
            [{"findings": [f]}, {"findings": [f]}],
            reducers,
        )

        # Assert
        assert len(final.findings) == 2


# ---------------------------------------------------------------------------
# Group 3: routing — merge_dict semantics
# ---------------------------------------------------------------------------

class TestRoutingMergeDict:

    def test_routing_two_agents_writing_different_keys_are_merged(self):
        """Intake and classifier agents writing distinct routing keys: both survive."""
        # Arrange
        state = _base_state()
        reducers = _reducers()
        update_a = {"routing": {"legal": ["LegalAgent"]}}
        update_b = {"routing": {"privacy": ["PrivacyAgent"]}}

        # Act
        final = merge_parallel_updates(state, [update_a, update_b], reducers)

        # Assert
        assert set(final.routing.keys()) == {"legal", "privacy"}
        assert final.routing["legal"] == ["LegalAgent"]
        assert final.routing["privacy"] == ["PrivacyAgent"]

    def test_routing_same_key_second_write_wins(self):
        """merge_dict is shallow: same key, later update overwrites."""
        # Arrange
        state = _base_state()
        reducers = _reducers()
        update_first = {"routing": {"legal": ["AgentV1"]}}
        update_second = {"routing": {"legal": ["AgentV2"]}}

        # Act
        final = merge_parallel_updates(state, [update_first, update_second], reducers)

        # Assert
        assert final.routing["legal"] == ["AgentV2"]

    def test_routing_empty_update_does_not_clear_existing_keys(self):
        """Applying an empty routing update must not wipe existing routing entries."""
        # Arrange
        state = _base_state(routing={"legal": ["LegalAgent"]})
        reducers = _reducers()

        # Act
        final = apply_state_update(state, {"routing": {}}, reducers)

        # Assert
        assert final.routing["legal"] == ["LegalAgent"]

    def test_routing_pre_existing_entries_preserved_across_merge(self):
        """Entries from state initialisation survive a merge with new entries."""
        # Arrange
        state = _base_state(routing={"existing": ["OldAgent"]})
        reducers = _reducers()

        # Act
        final = apply_state_update(state, {"routing": {"new": ["NewAgent"]}}, reducers)

        # Assert
        assert "existing" in final.routing
        assert "new" in final.routing

    def test_routing_three_branches_all_distinct_keys_all_present(self):
        """Fan-out of three routing writes with different keys: all survive."""
        # Arrange
        state = _base_state()
        reducers = _reducers()
        updates = [
            {"routing": {"legal": ["LegalAgent"]}},
            {"routing": {"privacy": ["PrivacyAgent"]}},
            {"routing": {"financial": ["FinancialAgent"]}},
        ]

        # Act
        final = merge_parallel_updates(state, updates, reducers)

        # Assert
        assert set(final.routing.keys()) == {"legal", "privacy", "financial"}


# ---------------------------------------------------------------------------
# Group 4: file_uris — merge_dict semantics
# ---------------------------------------------------------------------------

class TestFileUrisMergeDict:

    def test_file_uris_two_branches_different_keys_merge(self):
        # Arrange
        state = _base_state()
        reducers = _reducers()

        # Act
        final = merge_parallel_updates(
            state,
            [
                {"file_uris": {"msa.pdf": "gs://bucket/msa.pdf"}},
                {"file_uris": {"soc2.pdf": "gs://bucket/soc2.pdf"}},
            ],
            reducers,
        )

        # Assert
        assert final.file_uris == {
            "msa.pdf": "gs://bucket/msa.pdf",
            "soc2.pdf": "gs://bucket/soc2.pdf",
        }

    def test_file_uris_same_key_later_uri_wins(self):
        # Arrange
        state = _base_state()
        reducers = _reducers()

        # Act
        final = merge_parallel_updates(
            state,
            [
                {"file_uris": {"msa.pdf": "gs://bucket/v1/msa.pdf"}},
                {"file_uris": {"msa.pdf": "gs://bucket/v2/msa.pdf"}},
            ],
            reducers,
        )

        # Assert
        assert final.file_uris["msa.pdf"] == "gs://bucket/v2/msa.pdf"

    def test_file_uris_empty_update_preserves_existing(self):
        # Arrange
        state = _base_state(file_uris={"existing.pdf": "gs://bucket/existing.pdf"})
        reducers = _reducers()

        # Act
        final = apply_state_update(state, {"file_uris": {}}, reducers)

        # Assert
        assert final.file_uris["existing.pdf"] == "gs://bucket/existing.pdf"


# ---------------------------------------------------------------------------
# Group 5: packet_manifest — merge_list semantics
# ---------------------------------------------------------------------------

class TestPacketManifestMergeList:

    def test_packet_manifest_two_branches_concatenate(self):
        # Arrange
        state = _base_state()
        reducers = _reducers()
        doc_a = {"file": "msa.pdf", "pages": 12}
        doc_b = {"file": "soc2.pdf", "pages": 30}

        # Act
        final = merge_parallel_updates(
            state,
            [{"packet_manifest": [doc_a]}, {"packet_manifest": [doc_b]}],
            reducers,
        )

        # Assert
        assert len(final.packet_manifest) == 2
        files = [d["file"] for d in final.packet_manifest]
        assert "msa.pdf" in files
        assert "soc2.pdf" in files

    def test_packet_manifest_empty_branch_preserves_existing(self):
        # Arrange
        state = _base_state()
        reducers = _reducers()
        doc = {"file": "nda.pdf", "pages": 5}

        # Act
        final = merge_parallel_updates(
            state,
            [{"packet_manifest": [doc]}, {"packet_manifest": []}],
            reducers,
        )

        # Assert
        assert len(final.packet_manifest) == 1
        assert final.packet_manifest[0]["file"] == "nda.pdf"


# ---------------------------------------------------------------------------
# Group 6: plain (last-write-wins) fields
# ---------------------------------------------------------------------------

class TestPlainFieldLastWriteWins:

    def test_risk_score_last_write_wins(self):
        """risk_score has no reducer — second writer's value replaces first."""
        # Arrange
        state = _base_state()
        reducers = _reducers()

        # Act
        final = merge_parallel_updates(
            state,
            [{"risk_score": 0.4}, {"risk_score": 0.8}],
            reducers,
        )

        # Assert
        assert final.risk_score == 0.8

    def test_policy_verdict_last_write_wins(self):
        # Arrange
        state = _base_state()
        reducers = _reducers()

        # Act
        final = merge_parallel_updates(
            state,
            [{"policy_verdict": "APPROVE"}, {"policy_verdict": "REJECT"}],
            reducers,
        )

        # Assert
        assert final.policy_verdict == "REJECT"

    def test_subject_name_set_in_initial_state_preserved_after_unrelated_update(self):
        """Updating findings must not disturb plain fields not mentioned in the update."""
        # Arrange
        state = _base_state(subject_name="Acme Corp", packet_path="/tmp/acme")
        reducers = _reducers()
        f = _finding("LegalAgent")

        # Act
        final = apply_state_update(state, {"findings": [f]}, reducers)

        # Assert
        assert final.subject_name == "Acme Corp"
        assert final.packet_path == "/tmp/acme"


# ---------------------------------------------------------------------------
# Group 7: TPRMState round-trips
# ---------------------------------------------------------------------------

class TestTPRMStateRoundTrip:

    def test_empty_state_round_trips_through_model_dump(self):
        """Default TPRMState survives model_dump() → model_validate() without data loss."""
        # Arrange
        state = _base_state()

        # Act
        dumped = state.model_dump()
        restored = TPRMState.model_validate(dumped)

        # Assert
        assert restored == state

    def test_state_with_findings_round_trips_through_model_dump(self):
        # Arrange
        f = _finding_with_evidence("LegalAgent")
        state = _base_state(
            subject_name="Acme Corp",
            findings=[f],
            routing={"legal": ["LegalAgent"]},
            risk_score=0.75,
            policy_verdict="REVIEW",
        )

        # Act
        dumped = state.model_dump()
        restored = TPRMState.model_validate(dumped)

        # Assert
        assert restored.subject_name == "Acme Corp"
        assert len(restored.findings) == 1
        assert restored.findings[0].agent == "LegalAgent"
        assert restored.findings[0].evidence[0].file_id == "msa.pdf"
        assert restored.routing == {"legal": ["LegalAgent"]}
        assert restored.risk_score == 0.75
        assert restored.policy_verdict == "REVIEW"

    def test_state_with_all_annotated_fields_round_trips(self):
        # Arrange
        state = _base_state(
            file_uris={"msa.pdf": "gs://b/msa.pdf"},
            packet_manifest=[{"file": "msa.pdf", "pages": 10}],
            routing={"legal": ["LegalAgent"], "privacy": ["PrivacyAgent"]},
            findings=[_finding("LegalAgent"), _finding("PrivacyAgent")],
        )

        # Act
        dumped = state.model_dump()
        restored = TPRMState.model_validate(dumped)

        # Assert
        assert restored.file_uris == state.file_uris
        assert restored.packet_manifest == state.packet_manifest
        assert restored.routing == state.routing
        assert len(restored.findings) == 2

    def test_model_dump_json_round_trip_preserves_findings(self):
        """model_dump_json() / model_validate_json() path preserves nested structures."""
        # Arrange
        state = _base_state(findings=[_finding_with_evidence("ContractAgent")])

        # Act
        json_str = state.model_dump_json()
        restored = TPRMState.model_validate_json(json_str)

        # Assert
        assert restored.findings[0].evidence[0].snippet == "clause 3.1"
        assert restored.findings[0].raw["clause_id"] == "3.1"

    def test_default_values_are_correct_types(self):
        """Fresh TPRMState fields must have correct default types (not None)."""
        # Arrange / Act
        state = _base_state()

        # Assert
        assert isinstance(state.findings, list)
        assert isinstance(state.routing, dict)
        assert isinstance(state.file_uris, dict)
        assert isinstance(state.packet_manifest, list)
        assert state.mode == "vendor"
        assert state.subject_name == ""
        assert state.risk_score == 0.0


# ---------------------------------------------------------------------------
# Group 8: error path — unknown field rejected
# ---------------------------------------------------------------------------

class TestStateUpdateErrorPaths:

    def test_apply_state_update_raises_on_unknown_field(self):
        """Passing an unknown key to apply_state_update must raise StateValidationError."""
        from orchestra.core.errors import StateValidationError

        state = _base_state()
        reducers = _reducers()

        with pytest.raises(StateValidationError, match="Unknown state field"):
            apply_state_update(state, {"nonexistent_field": "value"}, reducers)

    def test_merge_parallel_updates_with_no_updates_returns_unchanged_state(self):
        """Empty update list leaves state identical to input."""
        # Arrange
        f = _finding("LegalAgent")
        state = _base_state(findings=[f], risk_score=0.5)
        reducers = _reducers()

        # Act
        final = merge_parallel_updates(state, [], reducers)

        # Assert
        assert final.risk_score == 0.5
        assert len(final.findings) == 1
