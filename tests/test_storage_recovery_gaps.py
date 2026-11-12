import hashlib

from scripts.investigate_recovery_gaps import investigate


def test_impossible_registration_is_distinguished_from_a_missing_original() -> None:
    possible = hashlib.sha256(b"a").hexdigest()
    gaps = [{"size": 1, "sha256": possible}, {"size": 2, "sha256": "c" * 64}]
    plan = {"unavailable": gaps, "unavailable_sha256": "a" * 64}
    result = investigate(plan, {"duplicate_groups": []})
    assert result["impossible_checksum_length_pairs"] == 1
    assert result["findings"][0]["classification"] == "ORIGINAL_STILL_UNAVAILABLE"
    assert result["findings"][1]["exhaustively_tested_byte_values"] == 65536
    assert result["registrations_modified"] == 0
    assert plan["unavailable"] == gaps
    assert result["full_recovery"] is False
