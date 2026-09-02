from __future__ import annotations

from collections.abc import Callable

import pytest
from football.ingestion import (
    ACQUISITION_STAGES_V1,
    AcquisitionStepV1,
    AutomaticAcquisitionError,
    AutomaticAcquisitionFlowV1,
)


def test_automatic_acquisition_runs_the_governed_order() -> None:
    calls: list[str] = []
    flow = AutomaticAcquisitionFlowV1(
        tuple(AcquisitionStepV1(stage, _append(calls, stage)) for stage in ACQUISITION_STAGES_V1)
    )

    result = flow.run()

    assert result.completed_stages == ACQUISITION_STAGES_V1
    assert calls == list(ACQUISITION_STAGES_V1)


def test_automatic_acquisition_rejects_missing_or_reordered_stage() -> None:
    steps = tuple(AcquisitionStepV1(stage, lambda: None) for stage in ACQUISITION_STAGES_V1[:-1])
    with pytest.raises(AutomaticAcquisitionError, match="stage order"):
        AutomaticAcquisitionFlowV1(steps)


def test_automatic_acquisition_stops_before_later_stages_on_failure() -> None:
    calls: list[str] = []

    def fail() -> None:
        calls.append("validate")
        raise RuntimeError("quarantine")

    steps = tuple(
        AcquisitionStepV1(
            stage,
            fail if stage == "validate" else _append(calls, stage),
        )
        for stage in ACQUISITION_STAGES_V1
    )
    flow = AutomaticAcquisitionFlowV1(steps)

    with pytest.raises(RuntimeError, match="quarantine"):
        flow.run()
    assert calls == ["discover", "checkpoint", "acquire", "preserve", "validate"]


def _append(calls: list[str], stage: str) -> Callable[[], None]:
    def action() -> None:
        calls.append(stage)

    return action
