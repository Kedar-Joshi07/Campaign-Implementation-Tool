from __future__ import annotations

import gzip
import hashlib

import pytest

from scripts.validation.run_full_fresh_phase1_to_phase7 import (
    FullFreshValidationError,
    _assert_hashes_match_accepted,
    _canonical_sha,
)


def test_plain_csv_canonical_hash_normalizes_only_line_endings(tmp_path) -> None:
    lf = tmp_path / "lf.csv"
    crlf = tmp_path / "crlf.csv"
    changed = tmp_path / "changed.csv"
    lf.write_bytes(b"id,name\n1,Ada\n")
    crlf.write_bytes(b"id,name\r\n1,Ada\r\n")
    changed.write_bytes(b"id,name\r\n1,Bea\r\n")

    expected = hashlib.sha256(b"id,name\n1,Ada\n").hexdigest()
    assert _canonical_sha(lf) == expected
    assert _canonical_sha(crlf) == expected
    assert _canonical_sha(changed) != expected


def test_gzip_canonical_hash_keeps_decompressed_payload_exact(tmp_path) -> None:
    source = tmp_path / "source.csv.gz"
    payload = b"id\r\n1\r\n"
    source.write_bytes(gzip.compress(payload, mtime=0))

    assert _canonical_sha(source) == hashlib.sha256(payload).hexdigest()


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
