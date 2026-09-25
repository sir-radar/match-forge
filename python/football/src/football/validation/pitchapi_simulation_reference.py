from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

PROTOCOL_ID = "PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V2"
POLICY_SHA256 = "8154e8b78b307dd25e7167ad00f2a310f012b1474580a82795e72acd5ce3a9ee"
MASK64 = (1 << 64) - 1


@dataclass
class SplitMix64:
    state: int

    def next_u64(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK64
        value = self.state
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & MASK64
        return value ^ (value >> 31)

    def next_unit_f64(self) -> float:
        return ((self.next_u64() >> 11) + 0.5) / (1 << 53)


def base_seed_commitment(forecast_probability_sha256: str) -> bytes:
    return hashlib.sha256(
        PROTOCOL_ID.encode() + POLICY_SHA256.encode() + forecast_probability_sha256.encode()
    ).digest()


def batch_seed(base: bytes, canonical_match_id: str, batch_index: int) -> bytes:
    return hashlib.sha256(
        base + canonical_match_id.encode() + struct.pack(">I", batch_index)
    ).digest()


def selected_atom_indexes(
    probabilities: tuple[float, ...], seed: bytes, draws: int
) -> tuple[int, ...]:
    generator = SplitMix64(int.from_bytes(seed[:8], "big"))
    selected: list[int] = []
    for _ in range(draws):
        value = generator.next_unit_f64()
        cumulative = 0.0
        for index, probability in enumerate(probabilities):
            cumulative += probability
            if cumulative > value:
                selected.append(index)
                break
        else:
            raise ValueError("draw exceeded categorical CDF")
    return tuple(selected)


def event_indexes(home_goals: int, away_goals: int) -> tuple[int, ...]:
    total = home_goals + away_goals
    result = [min(home_goals, 5) * 6 + min(away_goals, 5)]
    result.append(36 if home_goals > away_goals else 37 if home_goals == away_goals else 38)
    result.append(39 if home_goals > 0 and away_goals > 0 else 40)
    for threshold in range(5):
        result.append(41 + threshold * 2 + int(total <= threshold))
    result.extend((51 if away_goals == 0 else 52, 53 if home_goals == 0 else 54))
    result.append(55 + min(total, 5))
    return tuple(result)
