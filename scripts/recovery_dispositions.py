"""Record owner-approved recovery-scope retirements and source manifest corrections.

Every row is append-only and evidence-bound. Nothing here deletes or edits a registration,
writes a file, or supplies a checksum: the database rejects a row whose path, checksum or
lineage differs from the registration it names.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg import Connection
from psycopg.errors import CheckViolation, ForeignKeyViolation

from scripts.capture_architecture_v2_baseline import ROOT
from scripts.recovery_files import regular_file

# Immutable read-only explanations of the 159 declared gaps. The supplement names the two
# further registrations that share one gap's path with a registration the first file names.
APPROVED_EVIDENCE = (
    (
        "docs/evidence/storage-recovery-gaps-2026-11-12.json",
        "4c4a9d18d297c1276b64cd2b8cee508ff2e0ad6cbb947184d60c17097ecb23d1",
    ),
    (
        "docs/evidence/storage-recovery-gap-shared-owners-2026-11-12.json",
        "55918c7c023029c93046386d8393ea8f754176f2a70f62d130d4fd2ef5b7ffcb",
    ),
)
SYNTHETIC_CLASSIFICATIONS = frozenset(
    {
        "SYNTHETIC_TEST_REGISTRATION_DERIVED",
        "SYNTHETIC_TEST_REGISTRATION_PLACEHOLDER_CHECKSUM",
    }
)
CORRECTION = "MANIFEST_NEVER_WRITTEN_PATH_DIGEST"


class RecoveryDispositionError(ValueError):
    """A disposition conflicts with its evidence, its registration or recorded history."""


@dataclass(frozen=True)
class Retirement:
    table: str
    registration_id: str
    path: str
    sha256: str
    evidence_reference: str
    evidence_sha256: str


@dataclass(frozen=True)
class Correction:
    source_snapshot_id: str
    path: str
    evidence_reference: str
    evidence_sha256: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.path.encode()).hexdigest()


@dataclass(frozen=True)
class Approval:
    decision_reference: str
    recorded_at: datetime
    code_commit_sha: str


def evidence_dispositions(
    raw: bytes, reference: str, expected_sha256: str
) -> tuple[tuple[Retirement, ...], tuple[Correction, ...]]:
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise RecoveryDispositionError("recovery-gap evidence checksum differs from approval")
    evidence = json.loads(raw)
    findings = evidence["findings"]
    if (
        evidence.get("gaps", evidence.get("registrations")) != len(findings)
        or evidence["full_recovery"] is not False
        or evidence["registrations_modified"] != 0
        or evidence["fabricated_values"] != 0
    ):
        raise RecoveryDispositionError("recovery-gap evidence is not a read-only explanation")
    retirements = []
    corrections = []
    for finding in findings:
        identity = str(finding["keys"]["id"])
        if finding["classification"] in SYNTHETIC_CLASSIFICATIONS:
            if finding["registered_sha256"] is None:
                raise RecoveryDispositionError("synthetic retirement lacks a registered checksum")
            retirements.append(
                Retirement(
                    finding["table"],
                    identity,
                    finding["path"],
                    finding["registered_sha256"],
                    reference,
                    expected_sha256,
                )
            )
        elif finding["classification"] == CORRECTION and finding["table"] == "source_snapshots":
            corrections.append(Correction(identity, finding["path"], reference, expected_sha256))
        else:
            raise RecoveryDispositionError("recovery gap has no approved disposition")
    return tuple(retirements), tuple(corrections)


def approved_dispositions() -> tuple[tuple[Retirement, ...], tuple[Correction, ...]]:
    retirements: list[Retirement] = []
    corrections: list[Correction] = []
    for reference, digest in APPROVED_EVIDENCE:
        found = evidence_dispositions(regular_file(ROOT, reference).read_bytes(), reference, digest)
        retirements.extend(found[0])
        corrections.extend(found[1])
    keys = [(item.table, item.registration_id) for item in retirements]
    keys += [("source_snapshots", item.source_snapshot_id) for item in corrections]
    if len(set(keys)) != len(keys):
        raise RecoveryDispositionError("recovery-gap evidence repeats a registration")
    return tuple(retirements), tuple(corrections)


_RETIREMENT_INSERT = (
    "INSERT INTO football.recovery_scope_retirements(registration_table,registration_id,"
    "reason,registered_path,registered_sha256,evidence_reference,evidence_sha256,"
    "decision_reference,recorded_at,code_commit_sha) "
    "VALUES (%s,%s,'SYNTHETIC_TEST_LINEAGE',%s,%s,%s,%s,%s,%s,%s) "
    "ON CONFLICT (registration_table,registration_id) DO NOTHING"
)
_RETIREMENT_SELECT = (
    "SELECT registered_path,registered_sha256,evidence_reference,evidence_sha256,"
    "decision_reference,code_commit_sha FROM football.recovery_scope_retirements "
    "WHERE registration_table=%s AND registration_id=%s"
)
_CORRECTION_INSERT = (
    "INSERT INTO football.source_manifest_corrections(source_snapshot_id,correction,"
    "registered_path,registered_sha256,evidence_reference,evidence_sha256,decision_reference,"
    "recorded_at,code_commit_sha) VALUES (%s,'MANIFEST_NEVER_WRITTEN_PATH_DIGEST',"
    "%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (source_snapshot_id) DO NOTHING"
)
_CORRECTION_SELECT = (
    "SELECT registered_path,registered_sha256,evidence_reference,evidence_sha256,"
    "decision_reference,code_commit_sha FROM football.source_manifest_corrections "
    "WHERE source_snapshot_id=%s"
)


def record_dispositions(
    connection: Connection[Any],
    retirements: tuple[Retirement, ...],
    corrections: tuple[Correction, ...],
    approval: Approval,
) -> dict[str, int]:
    """Insert every disposition in one transaction, or verify an identical earlier one."""
    statements: list[tuple[str, tuple[Any, ...], str, tuple[Any, ...], tuple[Any, ...]]] = []
    for item in retirements:
        key: tuple[Any, ...] = (item.table, item.registration_id)
        bound = (item.path, item.sha256, item.evidence_reference, item.evidence_sha256)
        statements.append((_RETIREMENT_INSERT, key, _RETIREMENT_SELECT, key, bound))
    for correction in corrections:
        key = (correction.source_snapshot_id,)
        bound = (
            correction.path,
            correction.sha256,
            correction.evidence_reference,
            correction.evidence_sha256,
        )
        statements.append((_CORRECTION_INSERT, key, _CORRECTION_SELECT, key, bound))
    counts = {"inserted": 0, "verified_existing": 0}
    expected_approval = (approval.decision_reference, approval.code_commit_sha)
    try:
        with connection.transaction(), connection.cursor() as cursor:
            for insert, key, select, select_key, bound in statements:
                values = (
                    *key,
                    *bound,
                    approval.decision_reference,
                    approval.recorded_at,
                    approval.code_commit_sha,
                )
                inserted = cursor.execute(insert, values).rowcount
                counts["inserted" if inserted == 1 else "verified_existing"] += 1
                row = cursor.execute(select, select_key).fetchone()
                if row is None or tuple(map(str, row)) != tuple(
                    map(str, (*bound, *expected_approval))
                ):
                    raise RecoveryDispositionError(
                        "recovery disposition conflicts with immutable history"
                    )
    except (CheckViolation, ForeignKeyViolation) as error:
        raise RecoveryDispositionError(str(error).splitlines()[0]) from error
    return counts


def disposition_records(connection: Connection[Any]) -> dict[tuple[str, str], dict[str, str]]:
    """Every recorded disposition with the evidence and approval it is bound to.

    A governed recovery scope binds these exact records, so a backup taken under one
    approval cannot be presented as covered by a different or later one.
    """
    present = connection.execute(
        "SELECT to_regclass('football.recovery_scope_retirements') IS NOT NULL"
    ).fetchone()
    if not present or not present[0]:
        return {}
    result: dict[tuple[str, str], dict[str, str]] = {}
    for row in connection.execute(
        "SELECT 'source_snapshots',source_snapshot_id,correction,registered_path,"
        "registered_sha256,evidence_reference,evidence_sha256,decision_reference,code_commit_sha "
        "FROM football.source_manifest_corrections "
        "UNION ALL SELECT registration_table,registration_id,reason,registered_path,"
        "registered_sha256,evidence_reference,evidence_sha256,decision_reference,code_commit_sha "
        "FROM football.recovery_scope_retirements"
    ):
        table, identity, *values = map(str, row)
        result[(table, identity)] = dict(
            zip(
                (
                    "disposition",
                    "registered_path",
                    "registered_sha256",
                    "evidence_reference",
                    "evidence_sha256",
                    "decision_reference",
                    "code_commit_sha",
                ),
                values,
                strict=True,
            )
        )
    return result


def recorded_dispositions(connection: Connection[Any]) -> dict[tuple[str, str], tuple[str, str]]:
    """Map (registration table, id) to (disposition, bound checksum); empty before migration."""
    present = connection.execute(
        "SELECT to_regclass('football.recovery_scope_retirements') IS NOT NULL"
    ).fetchone()
    if not present or not present[0]:
        return {}
    result: dict[tuple[str, str], tuple[str, str]] = {}
    for table, identity, label, digest in connection.execute(
        "SELECT 'source_snapshots',source_snapshot_id,correction,registered_sha256 "
        "FROM football.source_manifest_corrections "
        "UNION ALL SELECT registration_table,registration_id,reason,registered_sha256 "
        "FROM football.recovery_scope_retirements"
    ):
        result[(str(table), str(identity))] = (str(label), str(digest))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-reference", required=True)
    parser.add_argument("--code-commit-sha", required=True)
    parser.add_argument(
        "--apply", action="store_true", help="write to DATABASE_URL; without it only validate"
    )
    args = parser.parse_args()
    retirements, corrections = approved_dispositions()
    summary: dict[str, Any] = {
        "retirements": len(retirements),
        "corrections": len(corrections),
        "applied": args.apply,
        "full_recovery": False,
    }
    if args.apply:
        approval = Approval(args.decision_reference, datetime.now(UTC), args.code_commit_sha)
        with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
            summary |= record_dispositions(connection, retirements, corrections, approval)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
