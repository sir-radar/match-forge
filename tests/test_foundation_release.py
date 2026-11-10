from scripts.foundation_release import migration_truth, release_truth


def test_release_requires_exact_build_identity_and_clean_build() -> None:
    assert release_truth({"code_commit_sha": "unknown"}, "a" * 40) == "UNKNOWN"
    assert release_truth({"code_commit_sha": "b" * 40}, "a" * 40) == "DIFFERENT_RELEASE"
    assert release_truth({"code_commit_sha": "a" * 40}, "a" * 40) == "BUILD_STATE_UNVERIFIED"
    assert (
        release_truth({"code_commit_sha": "a" * 40, "worktree_state": "clean"}, "a" * 40)
        == "MATCHING_CLEAN_BUILD"
    )


def test_migration_truth_preserves_applied_and_pending_distinction() -> None:
    result = migration_truth({1: "one", 2: "two"}, [0, 1])
    assert result["pending"] == [2]
    assert result["unknown_applied"] == []
    assert result["applied_checksums_verified"] is False
    assert migration_truth({1: "one"}, [1, 3])["unknown_applied"] == [3]
