from __future__ import annotations

import pytest
from football.forecasting.uncertainty import (
    BootstrapContractError,
    BootstrapPolicyV1,
    PairedMetricSeriesV1,
    paired_moving_block_bootstrap,
)


def test_paired_moving_block_bootstrap_is_deterministic_and_preserves_pairing() -> None:
    policy = BootstrapPolicyV1(replicates=200, block_size=3, confidence_level=0.95, seed=73)
    series = (
        PairedMetricSeriesV1(
            comparison="elo_vs_result_reference",
            metric="log_loss",
            candidate=(0.2, 0.4, 0.3, 0.6, 0.5, 0.7),
            reference=(0.1, 0.3, 0.2, 0.5, 0.4, 0.6),
        ),
        PairedMetricSeriesV1(
            comparison="dixon_coles_vs_result_reference",
            metric="ranked_probability_score",
            candidate=(0.3, 0.1, 0.4, 0.2, 0.6, 0.5),
            reference=(0.2, 0.2, 0.3, 0.3, 0.5, 0.6),
        ),
    )

    first = paired_moving_block_bootstrap(series, policy)
    second = paired_moving_block_bootstrap(series, policy)

    assert first == second
    assert first.policy == policy
    assert first.intervals[0].point_delta == pytest.approx(0.1)
    assert first.intervals[0].lower_bound == pytest.approx(0.1)
    assert first.intervals[0].upper_bound == pytest.approx(0.1)
    assert len(first.intervals) == 2


def test_paired_bootstrap_rejects_unaligned_or_short_series() -> None:
    policy = BootstrapPolicyV1(replicates=10, block_size=3, confidence_level=0.95, seed=1)
    with pytest.raises(BootstrapContractError, match="aligned"):
        PairedMetricSeriesV1("model_vs_reference", "log_loss", (0.1,), (0.1, 0.2))
    with pytest.raises(BootstrapContractError, match="block size"):
        paired_moving_block_bootstrap(
            (PairedMetricSeriesV1("model_vs_reference", "log_loss", (0.1,), (0.2,)),),
            policy,
        )
