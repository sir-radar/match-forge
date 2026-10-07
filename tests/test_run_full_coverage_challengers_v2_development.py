from pathlib import Path

import pytest

from scripts.run_full_coverage_challengers_v2_development import execute


def test_executor_rejects_non_head_source_before_reading_development_data() -> None:
    missing = Path("does-not-exist")

    with pytest.raises(RuntimeError, match="source commit must equal current Git HEAD"):
        execute(
            development_root=missing,
            v1_snapshot_root=missing,
            champion_artifact_path=missing,
            source_commit="0" * 40,
        )
