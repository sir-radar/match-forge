"""Read a retained native JSON record offline without canonical normalization."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

from football.providers.fotmob import parse_fotmob_fixture
from football.providers.native.models import NATIVE_MODELS
from football.providers.native.reader import NativeRecordError, native_record
from football.providers.pitchapi import parse_pitchapi_match


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise NativeRecordError(f"duplicate native field: {key}")
        value[key] = item
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=sorted(NATIVE_MODELS), required=True)
    parser.add_argument("input", type=Path)
    args = parser.parse_args(argv)
    raw = args.input.read_bytes()
    payload = json.loads(raw, object_pairs_hook=_object)
    record = native_record(NATIVE_MODELS[args.model], payload)
    if args.model == "FotmobFixture":
        record = parse_fotmob_fixture(record)
    elif args.model == "PitchApiMatch":
        record = parse_pitchapi_match(record)
    print(
        json.dumps(
            {
                "status": "PARSED",
                "native_model": args.model,
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "record": record,
            },
            ensure_ascii=False,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
