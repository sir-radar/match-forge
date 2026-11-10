"""Install tested Restic 0.19.1 from checksum-pinned Homebrew bottles, without root."""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOTTLES = {
    ("Darwin", "arm64"): "46e8a729f34715368444f8b7d4b6e99dca7ec575f7c677bba40bec71764c1dea",
    ("Linux", "x86_64"): "c3fda69d9bba81b3d9fa3e9854377bd2b02c23681ba1d2eb4a8925dc3cb936d3",
    ("Linux", "aarch64"): "13fa3948a9e6b498bb2e38178eef94685b0cc60760ac3875941e72595ec20a8b",
}


def main() -> None:
    target = ROOT / ".tools/bin/restic"
    if target.exists():
        result = subprocess.run(
            [str(target), "version"], capture_output=True, text=True, check=True
        )
        if result.stdout.startswith("restic 0.19.1 "):
            print("Restic 0.19.1 already installed")
            return
        raise ValueError("existing Restic differs; inspect it before replacement")
    digest = BOTTLES[(platform.system(), platform.machine())]
    with urllib.request.urlopen(
        "https://ghcr.io/token?service=ghcr.io&scope=repository:homebrew/core/restic:pull",
        timeout=30,
    ) as response:
        token = json.load(response)["token"]
    request = urllib.request.Request(
        "https://ghcr.io/v2/homebrew/core/restic/blobs/sha256:" + digest,
        headers={"Authorization": "Bearer " + token},
    )
    with tempfile.TemporaryDirectory(prefix="matchforge-restic-install-") as temporary:
        archive = Path(temporary) / "bottle.tar.gz"
        with urllib.request.urlopen(request, timeout=120) as source, archive.open("wb") as dest:
            shutil.copyfileobj(source, dest)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
            raise ValueError("Restic bottle checksum mismatch")
        with tarfile.open(archive) as bundle:
            matches = [
                item
                for item in bundle.getmembers()
                if item.isfile() and item.name.endswith("/bin/restic")
            ]
            if len(matches) != 1:
                raise ValueError("Restic bottle executable is ambiguous")
            source = bundle.extractfile(matches[0])
            assert source is not None
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open("xb") as dest:
                shutil.copyfileobj(source, dest)
        target.chmod(0o755)
    print("Installed checksum-verified Restic 0.19.1")


if __name__ == "__main__":
    main()
