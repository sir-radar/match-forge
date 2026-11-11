"""One serializer backs every hash; these pin the bytes each caller depends on."""

import math

import pytest
from football.contracts.source import canonical_json_bytes
from football.forecasting import contextual_goal, model_contracts
from football.forecasting.fresh_corpus import semantic_sha256
from football.product.domain import canonical_json, sha256_json

VALUE = {"b": [1, 2.5, None], "a": "Malmö"}


def test_canonical_json_bytes_supports_both_recorded_text_encodings() -> None:
    assert canonical_json_bytes(VALUE) == '{"a":"Malmö","b":[1,2.5,null]}'.encode()
    assert canonical_json_bytes(VALUE, ensure_ascii=True) == b'{"a":"Malm\\u00f6","b":[1,2.5,null]}'


def test_callers_keep_the_encoding_their_hashes_were_taken_over() -> None:
    escaped = canonical_json_bytes(VALUE, ensure_ascii=True)
    assert canonical_json(VALUE) == escaped
    assert model_contracts._canonical_json(VALUE) == escaped
    assert contextual_goal._canonical_json(VALUE) == escaped
    assert sha256_json(VALUE) == "97063c39276256ca762e701140dab1fe3c35eb6d4a4bb9a75a7268bf6a9e75c4"
    assert (
        semantic_sha256(VALUE) == "7b09544bc0fecf702d4389c46178b010de3a5906b2e6b3e40a4dffe8320c57c7"
    )


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_json_numbers_cannot_reach_a_hash(value: float) -> None:
    for serializer in (
        canonical_json_bytes,
        canonical_json,
        model_contracts._canonical_json,
        contextual_goal._canonical_json,
    ):
        with pytest.raises(ValueError, match="Out of range float values"):
            serializer({"probability": value})
