"""Read-only exact-duplicate analysis for files >= 1 MiB listed by walk.py.

Same size -> 2 MiB head/tail fingerprint -> full SHA-256. For proven duplicates,
compare the first physical device offset (F_LOG2PHYS) to tell APFS clones (shared
extents, no space to recover) from independent copies.
usage: dedupe.py WALK_JSON OUT_JSON
"""
import collections
import fcntl
import hashlib
import json
import os
import struct
import sys
import time

walk = json.load(open(sys.argv[1]))
big = walk["big_files"]
by_size = collections.defaultdict(list)
for size, alloc, ino, mtime, birth, path in big:
    by_size[size].append((alloc, ino, path))

F_LOG2PHYS = 49


def devoffset(path):
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            buf = fcntl.fcntl(fd, F_LOG2PHYS, bytes(20))
            return struct.unpack("<Iqq", buf)[2]
        finally:
            os.close(fd)
    except OSError:
        return None


def fingerprint(path, size):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read(1 << 20))
        if size > (2 << 20):
            fh.seek(size - (1 << 20))
            h.update(fh.read(1 << 20))
    return h.hexdigest()


def full(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(8 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


start = time.time()
groups = []
hashed_bytes = 0
errors = []
for size, items in sorted(by_size.items(), reverse=True):
    inodes = {}
    for alloc, ino, path in items:
        inodes.setdefault(ino, (alloc, path))
    if len(inodes) < 2:
        continue
    fps = collections.defaultdict(list)
    for ino, (alloc, path) in inodes.items():
        try:
            fps[fingerprint(path, size)].append((alloc, path))
        except OSError as e:
            errors.append(str(e))
    for fp, members in fps.items():
        if len(members) < 2:
            continue
        shas = collections.defaultdict(list)
        for alloc, path in members:
            try:
                shas[full(path)].append((alloc, path))
                hashed_bytes += size
            except OSError as e:
                errors.append(str(e))
        for sha, same in shas.items():
            if len(same) < 2:
                continue
            offs = [devoffset(p) for _, p in same]
            distinct_extents = len({o for o in offs if o is not None}) or 1
            groups.append(
                {
                    "sha256": sha,
                    "size": size,
                    "copies": len(same),
                    "distinct_first_extents": distinct_extents,
                    "duplicate_logical_bytes": size * (len(same) - 1),
                    "est_recoverable_physical_bytes": same[0][0] * (distinct_extents - 1),
                    "paths": [p for _, p in same],
                    "first_devoffsets": offs,
                }
            )

groups.sort(key=lambda g: -g["duplicate_logical_bytes"])
out = {
    "elapsed_seconds": round(time.time() - start, 1),
    "candidate_files": len(big),
    "full_hashed_bytes": hashed_bytes,
    "duplicate_groups": len(groups),
    "duplicate_logical_bytes": sum(g["duplicate_logical_bytes"] for g in groups),
    "est_recoverable_physical_bytes": sum(g["est_recoverable_physical_bytes"] for g in groups),
    "errors": errors[:50],
    "groups": groups,
}
json.dump(out, open(sys.argv[2], "w"), indent=1)
print({k: v for k, v in out.items() if k not in ("groups", "errors")})
