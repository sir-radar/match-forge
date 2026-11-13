"""Documentation hygiene check run by `make docs-check` and in CI.

Mechanical rules from the documentation lifecycle in docs/README.md:

- only the listed Markdown files may live at the repository root;
- no new dated report files beside the frozen legacy set;
- no scratch, progress or draft documents in tracked directories;
- JSON under docs/ only in the directories that hold evidence or evaluation inputs;
- every relative Markdown link and heading anchor resolves;
- every maintained document under docs/ is reachable from docs/README.md.

Records that describe a past date (evidence, decision events, source archives and the
legacy dated reports) are never rewritten, so their links are not checked. Uses the
standard library only so it runs before dependencies are installed.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

ROOT_DOCUMENTS = frozenset(
    {
        "AGENTS.md",
        "CLAUDE.md",
        "PLAN.md",
        "README.md",
        # Path and SHA-256 are cited by the unified-redesign evidence register.
        "MatchForge_Post_Redesign_Extensible_Football_Product_Implementation_Plan_v2_2026-11-09.md",
    }
)
# Point-in-time records. They are kept as written and retired only by owner decision.
HISTORICAL_PREFIXES = ("docs/evidence/", "docs/governance/decision-events/", "docs/references/")
LEGACY_DATED_REPORTS = frozenset(
    {
        "docs/CODEBASE_REMEDIATION_REPORT.md",
        "docs/V4_IMPLEMENTATION_REPORT.md",
        "docs/V4_ISSUE_02_QUALIFICATION_REPORT.md",
    }
)
DATED_REPORT_NAME = re.compile(r"(_REPORT|^MVP-|^V4_)", re.IGNORECASE)
SCRATCH_WORDS = frozenset(
    {"draft", "notes", "progress", "scratch", "scratchpad", "temp", "tmp", "todo", "wip"}
)
SCRATCH_PREFIXES = ("current_task", "tasks_to_continue", "agent-output", "agent_output")
DOCS_JSON_DIRECTORIES = ("docs/evidence/", "docs/evaluation/", "docs/architecture/")
DOCS_JSON_FILES = frozenset({"docs/project-status.json"})
INDEX = "docs/README.md"

LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE = re.compile(r"`[^`]*`")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
EXPLICIT_ANCHOR = re.compile(r"<a\s+(?:name|id)=\"([^\"]+)\"")


def tracked_files() -> list[str]:
    output = subprocess.run(["git", "ls-files", "-z"], check=True, capture_output=True).stdout
    return [path for path in output.decode().split("\0") if path]


def is_historical(path: str) -> bool:
    return path.startswith(HISTORICAL_PREFIXES) or path in LEGACY_DATED_REPORTS


def is_document(path: str) -> bool:
    return path.endswith(".md")


def scratch_name(path: str) -> bool:
    stem = PurePosixPath(path).stem.lower()
    words = set(re.split(r"[-_.\s]+", stem))
    return stem.startswith(SCRATCH_PREFIXES) or bool(SCRATCH_WORDS & words)


ROOT_MESSAGE = "Markdown at the repository root; update a document under docs/ instead"
SCRATCH_MESSAGE = "scratch, draft or progress file; keep it in .local/tmp/ (git-ignored)"
REPORT_MESSAGE = "new dated report; put the result in the PR description or docs/evidence/"
JSON_MESSAGE = (
    "JSON in a documentation directory; move it beside its consumer or into docs/evidence/"
)


def misplaced_json(path: str) -> bool:
    in_docs = path.startswith("docs/") and path.endswith((".json", ".jsonl"))
    allowed = path in DOCS_JSON_FILES or path.startswith(DOCS_JSON_DIRECTORIES)
    return in_docs and not allowed


def placement_problems(path: str) -> list[str]:
    name = PurePosixPath(path).name
    checks = [
        ("/" not in path and is_document(path) and path not in ROOT_DOCUMENTS, ROOT_MESSAGE),
        (scratch_name(path), SCRATCH_MESSAGE),
        (
            is_document(path)
            and bool(DATED_REPORT_NAME.search(name))
            and path not in LEGACY_DATED_REPORTS,
            REPORT_MESSAGE,
        ),
        (misplaced_json(path), JSON_MESSAGE),
    ]
    return [f"{path}: {message}" for failed, message in checks if failed]


def placement_findings(files: Iterable[str]) -> list[str]:
    return [
        problem
        for path in files
        if path.endswith((".md", ".json", ".jsonl")) and not path.startswith(HISTORICAL_PREFIXES)
        for problem in placement_problems(path)
    ]


def visible_lines(text: str, *, keep_code: bool = False) -> Iterable[tuple[int, str]]:
    fenced = False
    for number, line in enumerate(text.splitlines(), start=1):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced:
            yield number, line if keep_code else INLINE_CODE.sub("", line)


def slug(heading: str) -> str:
    text = re.sub(r"<[^>]+>", "", heading)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text).strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(text: str) -> set[str]:
    found: set[str] = set()
    counts: dict[str, int] = {}
    for _, line in visible_lines(text, keep_code=True):
        found.update(EXPLICIT_ANCHOR.findall(line))
        match = HEADING.match(line)
        if not match:
            continue
        base = slug(match.group(1))
        seen = counts.get(base, 0)
        counts[base] = seen + 1
        found.add(base if seen == 0 else f"{base}-{seen}")
    return found


def resolve(source: str, target: str) -> str:
    parts: list[str] = []
    for part in (PurePosixPath(source).parent / target).parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    return "/".join(parts)


def links(path: str, text: str) -> Iterable[tuple[int, str, str]]:
    for number, line in visible_lines(text):
        for target in LINK.findall(line):
            target = target.strip("<>")
            if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
                continue
            file_part, _, anchor = target.partition("#")
            yield number, resolve(path, file_part) if file_part else path, anchor


def link_findings(files: list[str], read: dict[str, str]) -> list[str]:
    tracked = set(files)
    directories = {str(parent) for path in files for parent in PurePosixPath(path).parents}
    anchor_cache: dict[str, set[str]] = {}
    findings = []
    for path in files:
        if not is_document(path) or is_historical(path):
            continue
        for number, target, anchor in links(path, read[path]):
            if target not in tracked and target not in directories:
                findings.append(f"{path}:{number}: broken link to {target}")
            elif anchor and target.endswith(".md") and target in tracked:
                if target not in anchor_cache:
                    anchor_cache[target] = anchors(read[target])
                if anchor not in anchor_cache[target]:
                    findings.append(f"{path}:{number}: missing anchor #{anchor} in {target}")
    return findings


def reachable(files: list[str], read: dict[str, str]) -> set[str]:
    documents = {path for path in files if is_document(path)}
    seen, queue = {INDEX}, [INDEX]
    while queue:
        current = queue.pop()
        for _, target, _ in links(current, read[current]):
            members = (
                {target}
                if target in documents
                else {
                    path
                    for path in documents
                    if str(PurePosixPath(path).parent) == target.rstrip("/")
                }
            )
            for member in members - seen:
                seen.add(member)
                queue.append(member)
    return seen


def index_findings(files: list[str], read: dict[str, str]) -> list[str]:
    linked = reachable(files, read)
    maintained = [
        path
        for path in files
        if path.startswith("docs/") and is_document(path) and not is_historical(path)
    ]
    return [
        f"{path}: not reachable from {INDEX}; link it from the document that owns its topic"
        for path in maintained
        if path not in linked
    ]


def main() -> int:
    files = tracked_files()
    read = {path: Path(path).read_text(encoding="utf-8") for path in files if is_document(path)}
    findings = placement_findings(files) + link_findings(files, read) + index_findings(files, read)
    for finding in findings:
        print(finding, file=sys.stderr)
    if findings:
        summary = f"docs-check: {len(findings)} finding(s). See {INDEX}#documentation-lifecycle."
        print(summary, file=sys.stderr)
        return 1
    print("docs-check: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
