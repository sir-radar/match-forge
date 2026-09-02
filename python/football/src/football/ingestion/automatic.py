from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

AcquisitionStageV1 = Literal[
    "discover",
    "checkpoint",
    "acquire",
    "preserve",
    "validate",
    "normalize",
    "resolve",
    "reconcile",
    "quarantine",
    "publish",
    "advance_cursor",
    "change_set",
    "downstream",
]

ACQUISITION_STAGES_V1: tuple[AcquisitionStageV1, ...] = (
    "discover",
    "checkpoint",
    "acquire",
    "preserve",
    "validate",
    "normalize",
    "resolve",
    "reconcile",
    "quarantine",
    "publish",
    "advance_cursor",
    "change_set",
    "downstream",
)


class AutomaticAcquisitionError(RuntimeError):
    """An automatic acquisition flow violates its execution contract."""


@dataclass(frozen=True, slots=True)
class AcquisitionStepV1:
    stage: AcquisitionStageV1
    action: Callable[[], None]


@dataclass(frozen=True, slots=True)
class AutomaticAcquisitionResultV1:
    completed_stages: tuple[AcquisitionStageV1, ...]


class AutomaticAcquisitionFlowV1:
    """Execute the complete ordered acquisition flow once.

    Each action owns its domain contract and durable checkpoint. Exceptions are
    propagated with the stage untouched so retries restart at the same semantic
    boundary rather than treating a fetch as canonical publication.
    """

    def __init__(self, steps: tuple[AcquisitionStepV1, ...]) -> None:
        stages = tuple(step.stage for step in steps)
        if stages != ACQUISITION_STAGES_V1:
            raise AutomaticAcquisitionError(
                "automatic acquisition steps must match the versioned stage order"
            )
        self._steps = steps

    def run(self) -> AutomaticAcquisitionResultV1:
        completed: list[AcquisitionStageV1] = []
        for step in self._steps:
            step.action()
            completed.append(step.stage)
        return AutomaticAcquisitionResultV1(tuple(completed))
