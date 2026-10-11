from __future__ import annotations

import pytest

from scripts.validation.run_full_fresh_phase1_to_phase7 import (
    FullFreshValidationError,
    _assert_hashes_match_accepted,
)


def test_full_fresh_hash_gate_keeps_canonical_payload_mandatory() -> None:
    with pytest.raises(FullFreshValidationError) as exc:
        _assert_hashes_match_accepted(
            accepted_hashes={
                "demographics": {"canonical_sha256": "accepted", "compressed_sha256": "old-gzip"}
            },
            generated_hashes={
                "demographics": {"canonical_sha256": "changed", "compressed_sha256": "new-gzip"}
            },
        )

    message = str(exc.value)
    assert "demographics" in message
    assert '"accepted": "accepted"' in message
    assert '"generated": "changed"' in message


def test_full_fresh_hash_gate_allows_only_compressed_container_drift() -> None:
    result = _assert_hashes_match_accepted(
        accepted_hashes={
            "demographics": {"canonical_sha256": "same", "compressed_sha256": "old-gzip"}
        },
        generated_hashes={
            "demographics": {"canonical_sha256": "same", "compressed_sha256": "new-gzip"}
        },
    )

    assert result["status"] == "PASS"
    assert result["canonical_mismatches"] == []
    assert result["compressed_mismatches"][0]["dataset"] == "demographics"


def test_full_fresh_hash_gate_reports_missing_dataset() -> None:
    with pytest.raises(FullFreshValidationError, match="missing_generated_hash"):
        _assert_hashes_match_accepted(
            accepted_hashes={
                "campaign_sales": {"canonical_sha256": "accepted", "compressed_sha256": "old"}
            },
            generated_hashes={},
        )
