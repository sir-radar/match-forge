"""Cutover controls cannot qualify a production or unbound stage from a passing label."""

import pytest
from football.product.resolution_stages import qualify_stage


def test_production_rehearsal_is_blocked_even_for_existing_projection_backend():
    with pytest.raises(ValueError, match="disposable isolated"):
        qualify_stage(
            {"action": "REHEARSE_STAGE"}, {"order": 8, "environment": "PRODUCTION_OR_UNREGISTERED"}
        )


@pytest.mark.parametrize("stage", range(1, 14))
def test_complete_parity_label_does_not_authorize_stage_advance(stage):
    with pytest.raises(ValueError, match="separate owner acceptance"):
        qualify_stage(
            {"action": "SWITCH_STAGE"},
            {"order": stage, "environment": "ISOLATED", "parity_gate": "PASS"},
        )
