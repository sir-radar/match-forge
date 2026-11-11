"""Turn walk/dedupe JSON into the audit's evidence tables.

usage: export.py SCRATCH EVIDENCE_DIR REPO_ROOT
"""
import collections
import datetime
import json
import os
import sys

S, E, R = sys.argv[1], sys.argv[2], sys.argv[3].rstrip("/")
w = json.load(open(S + "/walk_repo.json"))
t = json.load(open(S + "/walk_tmp.json"))
dd = json.load(open(S + "/dedupe.json"))


def rel(p):
    return p.replace(R + "/", "<repo>/").replace(R, "<repo>")


def fd(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else ""


alld = dict(w["dirs"])
alld.update(t["dirs"])
children = collections.defaultdict(list)
for k in alld:
    children[os.path.dirname(k)].append(k)


def dominated(k):
    return any(alld[c][2] > 0.9 * alld[k][2] for c in children.get(k, []))


cands = sorted((k for k in alld if k != R and not dominated(k)), key=lambda k: -alld[k][2])
with open(E + "/top50-directories.tsv", "w") as f:
    f.write("allocated_bytes\tlogical_bytes\tfiles\toldest_mtime\tnewest_mtime\tpath\n")
    for k in cands[:50]:
        v = alld[k]
        f.write("%d\t%d\t%d\t%s\t%s\t%s\n" % (v[2], v[1], v[0], fd(v[3]), fd(v[4]), rel(k)))

big = sorted(w["big_files"] + t["big_files"], reverse=True)
with open(E + "/top50-files.tsv", "w") as f:
    f.write("logical_bytes\tallocated_bytes\tmodified\tcreated\tpath\n")
    for size, alloc, ino, mt, bt, p in big[:50]:
        f.write("%d\t%d\t%s\t%s\t%s\n" % (size, alloc, fd(mt), fd(bt), rel(p)))

with open(E + "/local-directories.tsv", "w") as f:
    f.write("allocated_bytes\tlogical_bytes\tfiles\toldest_mtime\tnewest_mtime\tpath\n")
    ks = [k for k in w["dirs"] if k.startswith(R + "/.local/") and k.count("/") == R.count("/") + 2]
    for k in sorted(ks, key=lambda k: -w["dirs"][k][2]):
        v = w["dirs"][k]
        f.write("%d\t%d\t%d\t%s\t%s\t%s\n" % (v[2], v[1], v[0], fd(v[3]), fd(v[4]), rel(k)))

with open(E + "/file-creation-by-week.tsv", "w") as f:
    f.write("iso_week\tallocated_bytes_created\tcumulative\ttop_groups\n")
    wk = collections.defaultdict(collections.Counter)
    for day, gs in w["birth_days"].items():
        k = datetime.date.fromisoformat(day).strftime("%G-W%V")
        for g, a in gs.items():
            wk[k][g] += a
    cum = 0
    for k in sorted(wk):
        s = sum(wk[k].values())
        cum += s
        f.write("%s\t%d\t%d\t%s\n" % (k, s, cum, "; ".join("%s=%d" % x for x in wk[k].most_common(4))))

with open(E + "/extensions.tsv", "w") as f:
    f.write("extension\tfiles\tlogical_bytes\tallocated_bytes\n")
    for e, (n, l, a) in list(w["extensions"].items())[:40]:
        f.write("%s\t%d\t%d\t%d\n" % (e, n, l, a))

with open(E + "/exact-duplicates.tsv", "w") as f:
    f.write("size_bytes\tcopies\tdistinct_first_extents\test_recoverable_physical_bytes\tsha256\tpaths\n")
    for g in dd["groups"][:400]:
        f.write(
            "%d\t%d\t%d\t%d\t%s\t%s\n"
            % (
                g["size"],
                g["copies"],
                g["distinct_first_extents"],
                g["est_recoverable_physical_bytes"],
                g["sha256"],
                " | ".join(rel(p) for p in g["paths"]),
            )
        )

summary = {
    "measured_at": w["measured_at"],
    "repo_walk_total": w["total"],
    "repo_walk_seconds": w["elapsed_seconds"],
    "repo_walk_errors": w["error_count"],
    "tmp_walk_total": t["total"],
    "method": w["method"],
    "hardlink_duplicate_allocated_bytes_excluded": w["hardlink_duplicate_allocated_bytes_excluded"],
    "exact_duplicates_ge_1MiB": {
        k: dd[k]
        for k in (
            "candidate_files",
            "full_hashed_bytes",
            "duplicate_groups",
            "duplicate_logical_bytes",
            "est_recoverable_physical_bytes",
        )
    },
    "fully_extent_shared_duplicate_groups": sum(1 for g in dd["groups"] if g["distinct_first_extents"] == 1),
    "size_histogram_log2": w["size_histogram_log2"],
}
json.dump(summary, open(E + "/walk-summary.json", "w"), indent=1)
h = w["size_histogram_log2"]
print("files 512B-2KiB:", sum(h[b][0] for b in ("10", "11")), "alloc", sum(h[b][1] for b in ("10", "11")))
print(open(E + "/top50-directories.tsv").read())
