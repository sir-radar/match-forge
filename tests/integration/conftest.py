"""Integration tests may only reach databases proven disposable for this run.

See ``database_isolation.py``. This runs before any integration test module is imported,
so a run pointed at the operating database stops before its first write.
"""

from __future__ import annotations

import os

import pytest

from tests.integration.database_isolation import (
    DatabaseIsolationError,
    IsolationPolicy,
    child_environment,
    guard_urls,
    install,
)

try:
    _POLICY = IsolationPolicy.from_environment()
    guard_urls(_POLICY)
except DatabaseIsolationError as error:
    raise pytest.UsageError(str(error)) from error

install(_POLICY)
os.environ.update(child_environment(_POLICY))
