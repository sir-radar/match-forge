"""Explicit event labels shared by the observed FotMob and PitchAPI feeds."""

from football.providers.normalization.common import required_text


def event_type(value: str, card: object = None) -> str | None:
    label = value.casefold().replace("_", "")
    if label == "card":
        label = required_text(card).casefold().replace("_", "")
    return {
        "goal": "GOAL",
        "owngoal": "GOAL",
        "penaltygoal": "GOAL",
        "disallowedgoal": "DISALLOWED_GOAL",
        "cancelledgoal": "DISALLOWED_GOAL",
        "yellow": "YELLOW_CARD",
        "yellowcard": "YELLOW_CARD",
        "red": "RED_CARD",
        "redcard": "RED_CARD",
        "yellowred": "RED_CARD",
        "substitution": "SUBSTITUTION",
        "sub": "SUBSTITUTION",
        "corner": "CORNER",
    }.get(label)
