from __future__ import annotations

import csv
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from io import StringIO
from types import MappingProxyType

from football.contracts.source import canonical_json_bytes, sha256_bytes
from football.providers.football_data_uk import (
    FootballDataUkHistoricalLeagueCsvV1,
    FootballDataUkSourceResourceError,
    FootballDataUkSourceResourceV1,
)
from football.providers.schema_contract import SchemaCompatibilityResultV1


class FootballDataUkCsvValidationError(ValueError):
    """A Football-Data CSV cannot safely enter provider normalization."""


@dataclass(frozen=True, slots=True)
class FootballDataUkCsvRecordV1:
    csv_record_index: int
    values: Mapping[str, str]

    def __post_init__(self) -> None:
        if self.csv_record_index <= 0:
            raise FootballDataUkCsvValidationError("CSV record index must be positive")
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))


@dataclass(frozen=True, slots=True)
class FootballDataUkFieldCoverageV1:
    column: str
    non_null_count: int
    null_count: int
    coverage_ratio: float


@dataclass(frozen=True, slots=True)
class FootballDataUkCoverageReportV1:
    resource_identity: str
    source_resource_sha256: str
    header: tuple[str, ...]
    header_sha256: str
    row_count: int
    fields: tuple[FootballDataUkFieldCoverageV1, ...]
    contract: str = "FootballDataUkCoverageReportV1"

    def field_coverage(self, column: str) -> FootballDataUkFieldCoverageV1:
        for field in self.fields:
            if field.column == column:
                return field
        raise KeyError(f"coverage column is not present: {column}")


@dataclass(frozen=True, slots=True)
class FootballDataUkCsvValidationV1:
    receipt: FootballDataUkSourceResourceV1
    schema: SchemaCompatibilityResultV1
    coverage: FootballDataUkCoverageReportV1
    records: tuple[FootballDataUkCsvRecordV1, ...]


def parse_football_data_uk_csv(
    receipt: FootballDataUkSourceResourceV1,
    payload: bytes,
) -> FootballDataUkCsvValidationV1:
    """Parse one receipt-verified historical CSV without normalizing its semantics."""

    _verify_payload(receipt, payload)
    if receipt.resource_type != "historical_league_csv":
        raise FootballDataUkCsvValidationError("CSV parser requires a historical league receipt")
    header, raw_rows = _read_csv(payload)
    schema = FootballDataUkHistoricalLeagueCsvV1.inspect_columns(header)
    if schema.status == "quarantine":
        return FootballDataUkCsvValidationV1(
            receipt=receipt,
            schema=schema,
            coverage=_coverage_report(receipt, header, ()),
            records=(),
        )
    records = tuple(
        FootballDataUkCsvRecordV1(index, dict(zip(header, row, strict=True)))
        for index, row in enumerate(raw_rows, start=1)
    )
    return FootballDataUkCsvValidationV1(
        receipt=receipt,
        schema=schema,
        coverage=_coverage_report(receipt, header, records),
        records=records,
    )


def _verify_payload(receipt: FootballDataUkSourceResourceV1, payload: bytes) -> None:
    if len(payload) != receipt.raw_byte_size or sha256_bytes(payload) != receipt.raw_sha256:
        raise FootballDataUkSourceResourceError(
            "payload does not match source receipt byte size and SHA-256"
        )


def _read_csv(payload: bytes) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    try:
        reader = csv.reader(StringIO(payload.decode("utf-8"), newline=""))
        header = tuple(next(reader))
    except UnicodeDecodeError as error:
        raise FootballDataUkCsvValidationError("CSV must be valid UTF-8") from error
    except StopIteration as error:
        raise FootballDataUkCsvValidationError("CSV is missing a header") from error
    rows = tuple(tuple(row) for row in reader)
    for index, row in enumerate(rows, start=1):
        if len(row) != len(header):
            raise FootballDataUkCsvValidationError(
                f"CSV record {index} does not match header column count"
            )
    return header, rows


def _coverage_report(
    receipt: FootballDataUkSourceResourceV1,
    header: tuple[str, ...],
    records: tuple[FootballDataUkCsvRecordV1, ...],
) -> FootballDataUkCoverageReportV1:
    row_count = len(records)
    fields = tuple(_field_coverage(column, records, row_count) for column in header)
    return FootballDataUkCoverageReportV1(
        resource_identity=receipt.resource_identity,
        source_resource_sha256=receipt.raw_sha256,
        header=header,
        header_sha256=hashlib.sha256(
            canonical_json_bytes({"ordered_header": list(header)})
        ).hexdigest(),
        row_count=row_count,
        fields=fields,
    )


def _field_coverage(
    column: str,
    records: tuple[FootballDataUkCsvRecordV1, ...],
    row_count: int,
) -> FootballDataUkFieldCoverageV1:
    non_null_count = sum(record.values[column] != "" for record in records)
    null_count = row_count - non_null_count
    return FootballDataUkFieldCoverageV1(
        column=column,
        non_null_count=non_null_count,
        null_count=null_count,
        coverage_ratio=non_null_count / row_count if row_count else 0.0,
    )
