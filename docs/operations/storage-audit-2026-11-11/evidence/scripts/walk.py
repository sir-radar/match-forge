"""Read-only storage walk. Never follows symlinks, never writes outside OUT.

usage: walk.py OUT_JSON ROOT [ROOT...]
"""
import collections
import datetime
import json
import os
import stat
import sys
import time

out_path, roots = sys.argv[1], sys.argv[2:]
ROLLUP_DEPTH = 5
BIG = 1 << 20  # files >= 1 MiB are listed individually for duplicate analysis

dirs = collections.defaultdict(lambda: [0, 0, 0, 0.0, 0.0])  # files, logical, alloc, min_mtime, max_mtime
exts = collections.defaultdict(lambda: [0, 0, 0])
days = collections.defaultdict(lambda: collections.defaultdict(int))  # birth day -> group -> alloc
mdays = collections.defaultdict(lambda: collections.defaultdict(int))  # mtime day -> group -> alloc
sizehist = collections.defaultdict(lambda: [0, 0])
big = []
seen_inodes = set()
hardlink_dupe_alloc = 0
errors = []
symlinks = 0
total = [0, 0, 0]
start = time.time()


def group_of(rel_parts):
    if not rel_parts:
        return "."
    if rel_parts[0] == ".local" and len(rel_parts) > 1:
        if rel_parts[1] in ("football-data", "remediation", "foundation") and len(rel_parts) > 2:
            return "/".join(rel_parts[:3])
        return "/".join(rel_parts[:2])
    return rel_parts[0]


def day(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


for root in roots:
    root = os.path.abspath(root)
    base_parts = len(root.split(os.sep))
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=lambda e: errors.append(str(e))):
        parts = dirpath.split(os.sep)
        rel = parts[base_parts:]
        keys = [os.sep.join(parts[: base_parts + d]) for d in range(0, min(len(rel), ROLLUP_DEPTH) + 1)]
        grp = os.path.basename(root) + ":" + group_of(rel) if len(roots) > 1 else group_of(rel)
        try:
            dst = os.lstat(dirpath)
            dalloc = dst.st_blocks * 512
        except OSError as e:
            errors.append(str(e))
            dalloc = 0
        for k in keys:
            dirs[k][2] += dalloc
        total[2] += dalloc
        for name in filenames:
            p = os.path.join(dirpath, name)
            try:
                st = os.lstat(p)
            except OSError as e:
                errors.append(str(e))
                continue
            if stat.S_ISLNK(st.st_mode):
                symlinks += 1
            size = st.st_size
            alloc = st.st_blocks * 512
            if st.st_nlink > 1:
                ino = (st.st_dev, st.st_ino)
                if ino in seen_inodes:
                    hardlink_dupe_alloc += alloc
                    alloc = 0
                else:
                    seen_inodes.add(ino)
            total[0] += 1
            total[1] += size
            total[2] += alloc
            for k in keys:
                d = dirs[k]
                d[0] += 1
                d[1] += size
                d[2] += alloc
                if d[3] == 0.0 or st.st_mtime < d[3]:
                    d[3] = st.st_mtime
                if st.st_mtime > d[4]:
                    d[4] = st.st_mtime
            ext = os.path.splitext(name)[1].lower() or "(none)"
            e = exts[ext]
            e[0] += 1
            e[1] += size
            e[2] += alloc
            birth = getattr(st, "st_birthtime", st.st_mtime)
            days[day(birth)][grp] += alloc
            mdays[day(st.st_mtime)][grp] += alloc
            b = 0 if size == 0 else size.bit_length()
            h = sizehist[b]
            h[0] += 1
            h[1] += alloc
            if size >= BIG and stat.S_ISREG(st.st_mode):
                big.append((size, alloc, st.st_ino, st.st_mtime, birth, p))

big.sort(reverse=True)
result = {
    "roots": roots,
    "measured_at": datetime.datetime.now().isoformat(timespec="seconds"),
    "elapsed_seconds": round(time.time() - start, 1),
    "method": "os.walk without symlink traversal; logical=st_size, allocated=st_blocks*512; "
    "hard-linked inodes counted once; directory blocks included in allocated; APFS clones not detectable here",
    "total": {"files": total[0], "logical_bytes": total[1], "allocated_bytes": total[2]},
    "hardlink_duplicate_allocated_bytes_excluded": hardlink_dupe_alloc,
    "symlinks": symlinks,
    "errors": errors[:200],
    "error_count": len(errors),
    "dirs": {k: v for k, v in dirs.items()},
    "extensions": dict(sorted(exts.items(), key=lambda kv: -kv[1][2])[:80]),
    "birth_days": {d: dict(v) for d, v in sorted(days.items())},
    "mtime_days": {d: dict(v) for d, v in sorted(mdays.items())},
    "size_histogram_log2": {str(k): v for k, v in sorted(sizehist.items())},
    "big_files": big,
}
with open(out_path, "w") as fh:
    json.dump(result, fh)
print("done", result["total"], "elapsed", result["elapsed_seconds"], "errors", len(errors))
