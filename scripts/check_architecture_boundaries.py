"""Fail CI when source dependencies cross MatchForge language and package boundaries."""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_IMPORT_RULES = (
    (
        "domain and identity code cannot import provider adapters",
        (
            "football.identity",
            "football.canonical_resources",
            "football.observations",
            "football.product.domain",
        ),
        ("football.providers",),
    ),
    (
        "features cannot depend on raw or provider schemas",
        ("football.forecasting.features",),
        (
            "football.providers",
            "football.normalization",
            "football.validation",
            "football.storage.raw",
        ),
    ),
    (
        "forecasting cannot import provider adapters or parsers",
        ("football.forecasting",),
        ("football.providers",),
    ),
    (
        "provider adapters cannot import forecasting",
        ("football.providers",),
        ("football.forecasting",),
    ),
)
_EXPERIMENT_OUTCOME_READERS = (
    "football.forecasting.calibration_analysis",
    "football.forecasting.corner_labels",
    "football.forecasting.dataset",
    "football.forecasting.evaluation",
    "football.forecasting.evaluation_run",
    "football.forecasting.execution",
    "football.forecasting.full_coverage_evaluation",
    "football.forecasting.multi_model_evaluation",
    "football.forecasting.multimodel_authorized_evaluation",
    "football.forecasting.pitchapi_v3_evaluation",
    "football.forecasting.pitchapi_v4_evaluation",
    "football.forecasting.pitchapi_v5_evaluation",
    "football.forecasting.replacement_holdout",
    "football.forecasting.v2_reevaluation",
    "duckdb",
    "psycopg",
    "sqlalchemy",
)
_FRONTEND_PROVIDER_SCHEMA_PARTS = (
    "providers/native",
    "providers/normalization",
    "provider-native",
    "provider_native",
)
_MODEL_FITTING_DEPENDENCY_PARTS = frozenset(
    {
        "catboost",
        "argmin",
        "burn",
        "candle-core",
        "golearn",
        "gorgonia",
        "gonum",
        "linfa",
        "lightgbm",
        "machine-learning",
        "ml",
        "pytorch",
        "smartcore",
        "tensorflow",
        "tch",
        "torch",
        "xgboost",
    }
)
_MODEL_FITTING_FUNCTION = re.compile(r"\bfunc\s+(?:\([^)]*\)\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_RUST_FUNCTION = re.compile(r"\bfn\s+(?:r#)?([A-Za-z_][A-Za-z0-9_]*)\s*(?:<[^>]*>)?\s*\(")
_MODEL_FITTING_PREFIXES = ("calibrate", "fit", "learn", "optimize", "train")
_RAW_PROVIDER_FIELDS = frozenset(
    {"provider_payload", "provider_payload_json", "raw_provider_payload"}
)

_WORKER_SOURCE_CONTRACTS = {
    "python/football/src/football/product/forecast_work.py": (
        "WorkRegistry(connection)",
        "football.claim_work",
    ),
    "python/football/src/football/product/history_work.py": (
        "WorkRegistry(connection)",
        "claim_history_work",
    ),
    "python/football/src/football/product/history_worker.py": (
        "claim_history_request(",
        "WorkRegistry(self.connection)",
    ),
    "python/football/src/football/product/provider_history_scopes.py": (
        "def claim_scope(",
        "football.product_provider_scope_work",
    ),
    "python/football/src/football/product/resolution_recovery.py": (
        "WorkRegistry(connection)",
        "WorkType.CANONICAL_RECONCILIATION",
        "registry.claim(",
        "registry.heartbeat(",
        ".progress(claim)",
        "registry.publication(",
    ),
    "python/football/src/football/product/resolution_stages.py": (
        "WorkRegistry(connection)",
        "WorkType.READ_MODEL_PROJECTION",
        "registry.progress(claim)",
        "registry.publication(",
    ),
    "python/football/src/football/product/resolution_parity.py": (
        "WorkRegistry(connection)",
        "WorkType.READ_MODEL_PROJECTION",
        "registry.publication(",
        "REPEATABLE READ READ ONLY",
    ),
    "go/api/internal/app/resolution_recovery.go": (
        "football.resolution_recovery_work",
        'Operation: "recover_work"',
    ),
    "python/football/src/football/product/public_reports.py": (
        "WorkRegistry(connection)",
        "WorkType.",
    ),
    "python/football/src/football/forecasting/postmatch_storage.py": (
        "WorkRegistry(connection)",
        "WorkClaim",
    ),
    "go/api/internal/app/app.go": ("syncRunner.Start(ctx, SyncRequest{",),
    "go/api/internal/app/admin_sync.go": (
        "football.product_sync_runs",
        "matchforge.sync_run_id=",
    ),
    "infrastructure/migrations/202610182000_domain_work_adapters.sql": (
        "CREATE FUNCTION football.drive_sync_run_work()",
        "CREATE FUNCTION football.drive_provider_scope_work()",
        "football.enqueue_work(",
        "football.claim_work(",
        "football.heartbeat_work(",
        "football.finish_work(",
        "football.fail_work(",
    ),
}
_NON_PRODUCTION_WORKER_CLASSES = {
    "python/football/src/football/providers/worker.py": {"ProviderSyncWorkerV1"},
}
_WORKER_CLASS_NAME = re.compile(r"(?:Worker|WorkerV[0-9]+)$")


def _matches_prefix(value: str, prefix: str) -> bool:
    return value == prefix or value.startswith(f"{prefix}.")


def _module_name(path: Path, python_root: Path) -> str:
    parts = list(path.relative_to(python_root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _relative_module(module_name: str, level: int, target: str | None, is_package: bool) -> str:
    if level == 0:
        return target or ""
    parts = module_name.split(".")
    package_parts = parts if is_package else parts[:-1]
    for _ in range(max(level - 1, 0)):
        if package_parts:
            package_parts.pop()
    if target:
        package_parts.extend(target.split("."))
    return ".".join(package_parts)


def python_imports(
    source: str, module_name: str, *, is_package: bool = False
) -> list[tuple[str, int]]:
    """Return resolved imports, including literal dynamic imports."""
    tree = ast.parse(source)
    imports: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _relative_module(module_name, node.level, node.module, is_package)
            for alias in node.names:
                candidate = f"{base}.{alias.name}" if base else alias.name
                imports.append((candidate, node.lineno))
        elif isinstance(node, ast.Call):
            function = node.func
            dynamic = isinstance(function, ast.Name) and function.id == "__import__"
            dynamic = dynamic or (
                isinstance(function, ast.Attribute)
                and function.attr == "import_module"
                and isinstance(function.value, ast.Name)
                and function.value.id == "importlib"
            )
            if dynamic and node.args and isinstance(node.args[0], ast.Constant):
                target = node.args[0].value
                if isinstance(target, str):
                    imports.append((target, node.lineno))
    return sorted(set(imports))


def python_boundary_violations(source: str, module_name: str, path: str) -> list[str]:
    violations = []
    is_package = path.endswith("__init__.py")
    for target, line in python_imports(source, module_name, is_package=is_package):
        applicable_rules = [
            (max(map(len, source_prefixes)), label, forbidden_prefixes)
            for label, source_prefixes, forbidden_prefixes in _IMPORT_RULES
            if any(_matches_prefix(module_name, prefix) for prefix in source_prefixes)
        ]
        if applicable_rules:
            _, label, forbidden_prefixes = max(applicable_rules, key=lambda item: item[0])
            if any(_matches_prefix(target, prefix) for prefix in forbidden_prefixes):
                violations.append(f"{path}:{line}: {label}: {target}")
        if module_name == "football.forecasting.experiments" and any(
            _matches_prefix(target, prefix) for prefix in _EXPERIMENT_OUTCOME_READERS
        ):
            violations.append(
                f"{path}:{line}: experiment runner cannot access protected outcome readers: "
                f"{target}"
            )
    if _matches_prefix(module_name, "football.forecasting"):
        try:
            tree = ast.parse(source)
        except SyntaxError:
            tree = None
        if tree is not None:
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and node.value in _RAW_PROVIDER_FIELDS
                ):
                    violations.append(
                        f"{path}:{node.lineno}: forecasting cannot access "
                        "raw provider payload fields: "
                        f"{node.value}"
                    )
    return violations


def _python_violations(root: Path) -> list[str]:
    python_root = root / "python/football/src"
    if not python_root.exists():
        return ["python/football/src: production Python source tree is missing"]
    violations: list[str] = []
    for path in sorted(python_root.rglob("*.py")):
        module_name = _module_name(path, python_root)
        relative = path.relative_to(root).as_posix()
        try:
            violations.extend(
                python_boundary_violations(path.read_text(encoding="utf-8"), module_name, relative)
            )
        except SyntaxError as error:
            violations.append(
                f"{relative}:{error.lineno}: cannot parse Python imports: {error.msg}"
            )
    return violations


def typescript_imports(source: str) -> list[tuple[str, int]]:
    """Return static, side-effect and dynamic TypeScript module specifiers."""
    lines = source.splitlines()
    imports: list[tuple[str, int]] = []
    statement_start = re.compile(r"^\s*(?:import|export)\b")
    from_clause = re.compile(r"\bfrom\s*([\"'])([^\"']+)\1")
    side_effect = re.compile(r"^\s*import\s*(?:type\s*)?([\"'])([^\"']+)\1")
    for index, line in enumerate(lines):
        if not statement_start.match(line):
            continue
        statement = line
        match = from_clause.search(statement) or side_effect.search(statement)
        next_index = index + 1
        while match is None and next_index < len(lines):
            if statement_start.match(lines[next_index]):
                break
            statement += "\n" + lines[next_index]
            match = from_clause.search(statement) or side_effect.search(statement)
            next_index += 1
        if match is not None:
            imports.append((match.group(2), index + 1))
    dynamic_import = re.compile(r"\bimport\s*\(\s*([\"'])([^\"']+)\1")
    for match in dynamic_import.finditer(source):
        imports.append((match.group(2), source.count("\n", 0, match.start()) + 1))
    return sorted(set(imports))


def frontend_boundary_violations(source: str, path: str) -> list[str]:
    violations = []
    for target, line in typescript_imports(source):
        normalized = target.replace(".", "/").lower()
        if any(part in normalized for part in _FRONTEND_PROVIDER_SCHEMA_PARTS):
            violations.append(
                f"{path}:{line}: frontend cannot import provider-native schemas: {target}"
            )
    return violations


def _frontend_violations(root: Path) -> list[str]:
    web_root = root / "web"
    if not web_root.exists():
        return ["web: frontend source tree is missing"]
    ignored = {"node_modules", ".next", "dist", "coverage"}
    violations = []
    for path in sorted(web_root.rglob("*.ts")) + sorted(web_root.rglob("*.tsx")):
        if (
            any(part in ignored for part in path.parts)
            or ".test." in path.name
            or ".spec." in path.name
        ):
            continue
        violations.extend(
            frontend_boundary_violations(
                path.read_text(encoding="utf-8"), path.relative_to(root).as_posix()
            )
        )
    return violations


def _dependency_uses_fitting_library(dependency: str) -> bool:
    return bool(_MODEL_FITTING_DEPENDENCY_PARTS.intersection(dependency.lower().split("/")))


def go_dependency_violations(source: str, path: str = "go/api/go.mod") -> list[str]:
    violations = []
    in_require_block = False
    for line_number, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        if stripped == "require (":
            in_require_block = True
            continue
        if in_require_block and stripped == ")":
            in_require_block = False
            continue
        if stripped.startswith("require "):
            dependency = stripped.removeprefix("require ").split()[0]
        elif in_require_block:
            dependency = stripped.split()[0]
        else:
            continue
        if _dependency_uses_fitting_library(dependency):
            violations.append(
                f"{path}:{line_number}: Go cannot depend on model-fitting library {dependency}"
            )
    return violations


def go_source_violations(source: str, path: str) -> list[str]:
    violations = []
    function_names = [match.group(1) for match in _MODEL_FITTING_FUNCTION.finditer(source)]
    for name in function_names:
        if name.lower().startswith(_MODEL_FITTING_PREFIXES):
            violations.append(f"{path}: Go cannot define model-fitting function {name}")
    return violations


def _go_violations(root: Path) -> list[str]:
    go_root = root / "go/api"
    if not go_root.exists():
        return ["go/api: Go serving source tree is missing"]
    go_mod = go_root / "go.mod"
    violations = go_dependency_violations(go_mod.read_text(encoding="utf-8"))
    for path in sorted(go_root.rglob("*.go")):
        if path.name.endswith("_test.go"):
            continue
        relative = path.relative_to(root).as_posix()
        violations.extend(go_source_violations(path.read_text(encoding="utf-8"), relative))
        if path.parent.name.lower() in {"model", "models", "modeling", "training", "forecasting"}:
            violations.append(f"{relative}: Go model implementation packages are not allowed")
    return violations


def rust_source_violations(source: str, path: str) -> list[str]:
    violations = []
    for match in _RUST_FUNCTION.finditer(source):
        name = match.group(1).lower()
        if name.startswith(_MODEL_FITTING_PREFIXES):
            violations.append(f"{path}: Rust cannot define football model-fitting function {name}")
    return violations


def rust_manifest_violations(source: str, path: str) -> list[str]:
    try:
        data = tomllib.loads(source)
    except tomllib.TOMLDecodeError as error:
        return [f"{path}: invalid Cargo manifest: {error}"]

    violations = []
    dependency_sections = {"dependencies", "dev-dependencies", "build-dependencies"}

    def visit(section: object) -> None:
        if not isinstance(section, dict):
            return
        for name, value in section.items():
            if name in dependency_sections and isinstance(value, dict):
                for dependency in value:
                    if _dependency_uses_fitting_library(dependency):
                        violations.append(
                            f"{path}: Rust cannot depend on model-fitting library {dependency}"
                        )
            else:
                visit(value)

    visit(data)
    return violations


def _rust_violations(root: Path) -> list[str]:
    rust_root = root / "rust"
    if not rust_root.exists():
        return ["rust: Rust source tree is missing"]
    violations: list[str] = []
    for manifest in sorted(rust_root.rglob("Cargo.toml")):
        relative = manifest.relative_to(root).as_posix()
        violations.extend(rust_manifest_violations(manifest.read_text(encoding="utf-8"), relative))
    for path in sorted(rust_root.rglob("*.rs")):
        violations.extend(
            rust_source_violations(
                path.read_text(encoding="utf-8"), path.relative_to(root).as_posix()
            )
        )
    return violations


def _worker_violations(root: Path) -> list[str]:
    violations = _worker_entrypoint_violations(root)
    for relative in _WORKER_SOURCE_CONTRACTS:
        path = root / relative
        if not path.is_file():
            violations.append(f"{relative}: registered production worker adapter is missing")
            continue
        source = path.read_text(encoding="utf-8")
        violations.extend(worker_source_contract_violations(relative, source))
    return violations


def _worker_entrypoint_violations(root: Path) -> list[str]:
    python_root = root / "python/football/src"
    return [
        *_python_worker_declaration_violations(root, python_root),
        *_python_test_worker_call_violations(root, python_root),
        *_go_schedule_violations(root),
    ]


def _python_worker_declaration_violations(root: Path, python_root: Path) -> list[str]:
    violations = []
    registered_paths = set(_WORKER_SOURCE_CONTRACTS)
    non_production_paths = set(_NON_PRODUCTION_WORKER_CLASSES)
    for path in sorted(python_root.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or not _WORKER_CLASS_NAME.search(node.name):
                continue
            if relative in registered_paths:
                continue
            if (
                relative in non_production_paths
                and node.name in _NON_PRODUCTION_WORKER_CLASSES[relative]
            ):
                continue
            violations.append(
                f"{relative}:{node.lineno}: worker class {node.name} needs a registered "
                "Work Orchestrator contract"
            )
    return violations


def _python_test_worker_call_violations(root: Path, python_root: Path) -> list[str]:
    violations = []
    non_production_names = {
        name for names in _NON_PRODUCTION_WORKER_CLASSES.values() for name in names
    }
    non_production_paths = set(_NON_PRODUCTION_WORKER_CLASSES)
    for path in sorted(python_root.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        if relative in non_production_paths:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called_name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else ""
            )
            if called_name in non_production_names:
                violations.append(
                    f"{relative}:{node.lineno}: test-only worker {called_name} cannot be "
                    "constructed by production source"
                )
    return violations


def _go_schedule_violations(root: Path) -> list[str]:
    violations = []
    registered_paths = set(_WORKER_SOURCE_CONTRACTS)
    go_root = root / "go/api"
    for path in sorted(go_root.rglob("*.go")):
        if path.name.endswith("_test.go"):
            continue
        relative = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8")
        if "time.NewTicker(" not in source:
            continue
        if relative not in registered_paths:
            violations.append(
                f"{relative}: Go background schedule needs a registered Work Orchestrator contract"
            )
    return violations


def worker_source_contract_violations(relative: str, source: str) -> list[str]:
    required_tokens = _WORKER_SOURCE_CONTRACTS.get(relative)
    if required_tokens is None:
        return [f"{relative}: production worker adapter is not registered with the checker"]
    return [
        f"{relative}: production work path must retain shared Work Orchestrator binding {token!r}"
        for token in required_tokens
        if token not in source
    ]


def architecture_violations(root: Path = ROOT) -> list[str]:
    """Return all source-level dependency and worker-routing violations."""
    checks: tuple[Callable[[Path], list[str]], ...] = (
        _python_violations,
        _frontend_violations,
        _go_violations,
        _rust_violations,
        _worker_violations,
    )
    violations = [violation for check in checks for violation in check(root)]
    return sorted(violations)


def main() -> int:
    violations = architecture_violations()
    if violations:
        print("Architecture dependency check failed:", file=sys.stderr)
        for violation in violations:
            print(f"- {violation}", file=sys.stderr)
        return 1
    print("Architecture dependency check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
