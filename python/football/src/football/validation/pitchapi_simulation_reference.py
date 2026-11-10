"""Python reference for the frozen Rust simulation-core sampler and atom hash.

The Rust crate is the implementation of record. This module restates the parts
that Python must agree with so tests can check both against one golden fixture.
"""

from __future__ import annotations

import hashlib
import math
import struct
from collections.abc import Mapping, Sequence
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


def base_seed_commitment(
    forecast_probability_sha256: str,
    *,
    protocol_id: str = PROTOCOL_ID,
    policy_sha256: str = POLICY_SHA256,
) -> bytes:
    return hashlib.sha256(
        protocol_id.encode() + policy_sha256.encode() + forecast_probability_sha256.encode()
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


def canonical_probability(value: float) -> str:
    """Format a probability exactly as simulation-core writes it for the atom hash.

    Both sides use the shortest decimal that round-trips. They differ in layout:
    Python writes ``1.2e-05`` where Rust writes ``0.000012``, and Rust drops the
    exponent padding below ``1e-5`` (``9.9e-6``).
    """
    if isinstance(value, bool) or not isinstance(value, float):
        raise ValueError("probability must be a float")
    if not 0.0 <= value <= 1.0 or math.copysign(1.0, value) < 0.0:
        raise ValueError("probability must be in [0, 1]")
    if value == 0.0:
        return "0.0"
    mantissa, _, exponent_text = repr(value).partition("e")
    whole, _, fraction = mantissa.partition(".")
    significant = (whole + fraction).lstrip("0")
    digits = significant.rstrip("0")
    exponent = int(exponent_text or 0) - len(fraction) + len(significant) - len(digits)
    point = len(digits) + exponent
    if point > 0:
        return digits + "0" * exponent + ".0"
    if point > -5:
        return "0." + "0" * -point + digits
    leading = digits if len(digits) == 1 else f"{digits[0]}.{digits[1:]}"
    return f"{leading}e{point - 1}"


def canonical_atoms_bytes(atoms: Sequence[Mapping[str, object]]) -> bytes:
    """Serialize score atoms to the bytes whose SHA-256 is forecast_probability_sha256."""
    rows: list[str] = []
    for atom in atoms:
        goals = (atom["away_goals"], atom["home_goals"])
        if any(value is not None and type(value) is not int for value in goals):
            raise ValueError("atom goals must be integers or null")
        probability = atom["probability"]
        if not isinstance(probability, float):
            raise ValueError("atom probability must be a float")
        away, home = ("null" if value is None else str(value) for value in goals)
        rows.append(
            f'{{"away_goals":{away},"home_goals":{home},"kind":"{atom["kind"]}",'
            f'"probability":{canonical_probability(probability)}}}'
        )
    return ("[" + ",".join(rows) + "]").encode()
