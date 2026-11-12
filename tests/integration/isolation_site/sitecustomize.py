"""Install the integration-test database guard in Python child processes.

Integration tests prepend this directory to ``PYTHONPATH`` for the processes they start,
so a CLI or worker launched by a test is held to the same rule as the test itself.
"""

import os
import sys

if os.environ.get("MATCHFORGE_TEST_ISOLATION_ACTIVE") == "1":
    import importlib.util
    from pathlib import Path

    _path = Path(__file__).resolve().parent.parent / "database_isolation.py"
    _name = "tests.integration.database_isolation"
    _spec = importlib.util.spec_from_file_location(_name, _path)
    if _spec is None or _spec.loader is None:
        raise RuntimeError("cannot load the integration-test database guard")
    _module = importlib.util.module_from_spec(_spec)
    # One module object per process, so its error class and saved connect are shared.
    sys.modules[_name] = _module
    _spec.loader.exec_module(_module)
    _module.install(_module.IsolationPolicy.from_environment())
