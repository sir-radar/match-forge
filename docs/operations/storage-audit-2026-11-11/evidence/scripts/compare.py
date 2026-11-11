"""Read-only comparison of copies of the football-data tree.

For each copy: files whose relative path and size match the live tree, how many of
those share the first physical extent (APFS clone / same blocks), and a hashed sample.
usage: compare.py OUT_JSON BASE COPY [COPY...]
"""
import fcntl
import hashlib
import json
import os
import random
import struct
import sys

out, base, copies = sys.argv[1], sys.argv[2], sys.argv[3:]


def listing(root):
    res = {}
    for dp, dn, fn in os.walk(root, followlinks=False):
        for n in fn:
            p = os.path.join(dp, n)
            try:
                st = os.lstat(p)
            except OSError:
                continue
            res[os.path.relpath(p, root)] = (st.st_size, st.st_blocks * 512, st.st_ino)
    return res


def devoffset(path):
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            return struct.unpack("<Iqq", fcntl.fcntl(fd, 49, bytes(20)))[2]
        finally:
            os.close(fd)
    except OSError:
        return None


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(4 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


random.seed(20261111)
b = listing(base)
result = {"base": base, "base_files": len(b), "base_alloc": sum(v[1] for v in b.values()), "copies": []}
for c in copies:
    l = listing(c)
    same = [r for r, v in l.items() if r in b and b[r][0] == v[0]]
    same_ino = sum(1 for r in same if b[r][2] == l[r][2])
    shared_extent = shared_bytes = checked = 0
    for r in same:
        if l[r][0] == 0:
            continue
        o1, o2 = devoffset(os.path.join(base, r)), devoffset(os.path.join(c, r))
        if o1 is None or o2 is None:
            continue
        checked += 1
        if o1 == o2:
            shared_extent += 1
            shared_bytes += l[r][1]
    sample = random.sample(same, min(400, len(same)))
    equal = sum(1 for r in sample if sha(os.path.join(base, r)) == sha(os.path.join(c, r)))
    result["copies"].append(
        {
            "copy": c,
            "files": len(l),
            "alloc": sum(v[1] for v in l.values()),
            "same_relpath_and_size_files": len(same),
            "same_relpath_and_size_alloc": sum(l[r][1] for r in same),
            "same_inode_hardlinks": same_ino,
            "extent_checked": checked,
            "shared_first_extent_files": shared_extent,
            "shared_first_extent_alloc": shared_bytes,
            "hash_sample": len(sample),
            "hash_sample_equal": equal,
            "only_in_copy_files": len([r for r in l if r not in b]),
            "only_in_copy_alloc": sum(v[1] for r, v in l.items() if r not in b),
            "size_differs_files": len([r for r, v in l.items() if r in b and b[r][0] != v[0]]),
        }
    )
json.dump(result, open(out, "w"), indent=1)
print(json.dumps(result, indent=1))
