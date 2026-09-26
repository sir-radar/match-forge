from __future__ import annotations

import hashlib
from pathlib import Path


def test_v2_and_statsbomb_evaluation_evidence_remain_immutable() -> None:
    root = Path(__file__).resolve().parents[3]
    expected = {
        "docs/evaluation/evaluation-v2-policy.md": (
            "90812c0119e84a5bef94e8726ba9f4a984c33f8a6bb655603c68738994a345b3"
        ),
        "docs/evaluation/pitchapi-domain-stratified-evaluation-v2-policy-proposal.json": (
            "e4dfbf6a5133fba4806de80e6a79ccc878670531bb695e5509776dca082c1da1"
        ),
        "docs/evaluation/pitchapi-domain-stratified-evaluation-v2-preregistration.json": (
            "eec2b9362b72779a44da87e8ddf3055b22bd3573a3d52b6f62e97d72c31068f4"
        ),
        "docs/evaluation/pitchapi-domain-stratified-v2-execution-configuration.json": (
            "8cf592c471d543c874c83ab12e11942e4de74453f49f3a8d4949d636667b8285"
        ),
        "docs/evaluation/pitchapi-v2-models/pitchapi-v2-challenger-artifact.json": (
            "5fab3347523ade3918b17f7cd38400a6a54f92b54adee3da61aa28fdb5d9d973"
        ),
        "docs/evaluation/pitchapi-v2-models/pitchapi-v2-reference-artifact.json": (
            "54d209dc5d409c589750822871944f1b1175ae95883c9c83b92be1c729f5ddba"
        ),
        "docs/evidence/statsbomb-evaluation-v2-qualification-package-2026-09-23.md": (
            "e5a42bf40ae36111f324a6322aab0cf65618a0fdabeb95b2fb132375648b9a39"
        ),
        "docs/evidence/statsbomb-qualification-request-send-record-2026-09-24.json": (
            "ad6681f748cbb37b815cddedfc7332371f42d329e69ff7c0cec76964f3ca3000"
        ),
    }
    actual = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in expected}
    assert actual == expected
