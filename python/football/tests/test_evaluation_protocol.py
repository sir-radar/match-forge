from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import pytest
from football.forecasting.evaluation_protocol import (
    EvaluationProtocolError,
    EvaluationResultIdentityV1,
    validate_evaluation_result_set,
)


def _identity() -> EvaluationResultIdentityV1:
    return EvaluationResultIdentityV1(
        evaluation_protocol_id="PITCHAPI_RETROSPECTIVE_EVALUATION_V1",
        provider_source_series_id="pitchapi:series-sha256:abc",
        snapshot_id=UUID("3ae19e2c-133b-4ec8-8f70-2245ca26da75"),
        corpus_sha256="1" * 64,
        firewall_sha256="2" * 64,
        model_build="model-build-v1",
        simulation_build="simulation-build-v1",
        target_count=758,
    )


def test_single_evaluation_rejects_mixed_protocols_by_default() -> None:
    pitchapi = _identity()
    statsbomb = replace(pitchapi, evaluation_protocol_id="EVALUATION_V2")

    with pytest.raises(EvaluationProtocolError, match="cross_evaluation_robustness"):
        validate_evaluation_result_set((pitchapi, statsbomb))


def test_cross_evaluation_comparison_requires_explicit_label() -> None:
    pitchapi = _identity()
    statsbomb = replace(pitchapi, evaluation_protocol_id="EVALUATION_V2")

    validate_evaluation_result_set(
        (pitchapi, statsbomb), analysis_kind="cross_evaluation_robustness"
    )


def test_single_evaluation_rejects_snapshot_or_build_mixing() -> None:
    first = _identity()

    with pytest.raises(EvaluationProtocolError, match="mixed evaluation results"):
        validate_evaluation_result_set((first, replace(first, model_build="model-build-v2")))
