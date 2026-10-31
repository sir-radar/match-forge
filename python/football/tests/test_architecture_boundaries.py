from pathlib import Path

from scripts.check_architecture_boundaries import (
    _worker_entrypoint_violations,
    architecture_violations,
    frontend_boundary_violations,
    go_dependency_violations,
    go_source_violations,
    python_boundary_violations,
    rust_manifest_violations,
    rust_source_violations,
    worker_source_contract_violations,
)

ROOT = Path(__file__).resolve().parents[3]


def test_repository_source_obeys_architecture_boundaries() -> None:
    assert architecture_violations(ROOT) == []


def test_python_domain_and_forecasting_rules_resolve_imports() -> None:
    domain = python_boundary_violations(
        "from ..providers import native\n",
        "football.identity.repository",
        "identity/repository.py",
    )
    feature = python_boundary_violations(
        'import importlib\nimportlib.import_module("football.providers.native.fotmob")\n',
        "football.forecasting.features",
        "forecasting/features.py",
    )

    assert len(domain) == 1
    assert "domain and identity code cannot import provider adapters" in domain[0]
    assert len(feature) == 1
    assert "features cannot depend on raw or provider schemas" in feature[0]


def test_experiment_runner_cannot_import_protected_outcome_readers() -> None:
    violations = python_boundary_violations(
        "from football.forecasting.evaluation_run import Sprint2EvaluationRunner\n",
        "football.forecasting.experiments",
        "forecasting/experiments.py",
    )

    assert len(violations) == 1
    assert "protected outcome readers" in violations[0]


def test_experiment_runner_cannot_import_outcome_reader_from_package() -> None:
    violations = python_boundary_violations(
        "from football.forecasting import evaluation_run\n",
        "football.forecasting.experiments",
        "forecasting/experiments.py",
    )

    assert len(violations) == 1
    assert "protected outcome readers" in violations[0]


def test_features_cannot_import_normalizers_or_raw_provider_fields() -> None:
    feature_import = python_boundary_violations(
        "from football.normalization import statsbomb_events\n",
        "football.forecasting.features",
        "forecasting/features.py",
    )
    raw_field = python_boundary_violations(
        'payload = row["provider_payload_json"]\n',
        "football.forecasting.runtime_models",
        "forecasting/runtime_models.py",
    )

    assert len(feature_import) == 1
    assert "raw or provider schemas" in feature_import[0]
    assert len(raw_field) == 1
    assert "raw provider payload fields" in raw_field[0]


def test_provider_adapters_cannot_import_forecasting() -> None:
    violations = python_boundary_violations(
        "from football.forecasting import runtime_models\n",
        "football.providers.fotmob",
        "providers/fotmob.py",
    )

    assert len(violations) == 1
    assert "provider adapters cannot import forecasting" in violations[0]


def test_frontend_rejects_static_and_dynamic_provider_native_imports() -> None:
    source = """\
import type {
  NativeFixture,
} from "@/providers/native/fotmob";
const parser = await import("@/providers/normalization/fotmob");
"""
    violations = frontend_boundary_violations(source, "web/components/fixture.tsx")

    assert len(violations) == 2
    assert all("provider-native schemas" in item for item in violations)


def test_go_and_rust_reject_model_fitting_entrypoints() -> None:
    go = go_source_violations("func FitModel(input []float64) {}\n", "go/api/model.go")
    rust = rust_source_violations("pub fn train_model(input: &[f64]) {}\n", "rust/model.rs")

    assert len(go) == 1
    assert "Go cannot define model-fitting function FitModel" in go[0]
    assert len(rust) == 1
    assert "Rust cannot define football model-fitting function train_model" in rust[0]


def test_go_and_rust_reject_fitting_dependencies_in_all_manifest_forms() -> None:
    go = go_dependency_violations(
        "module example.test/api\n"
        "require github.com/gonum/gonum v0.15.0\n"
        "require (\n"
        "    github.com/gorgonia/gorgonia v0.9.18\n"
        ")\n"
    )
    rust = rust_manifest_violations(
        "[workspace.dependencies]\n"
        'linfa = "0.7"\n'
        "[target.'cfg(unix)'.dev-dependencies]\n"
        'smartcore = "0.3"\n',
        "rust/Cargo.toml",
    )

    assert len(go) == 2
    assert all("model-fitting library" in item for item in go)
    assert len(rust) == 2
    assert all("model-fitting library" in item for item in rust)


def test_registered_worker_cannot_drop_its_orchestrator_contract() -> None:
    missing_binding = worker_source_contract_violations(
        "python/football/src/football/product/forecast_work.py",
        "def run_forecast_work():\n    return None\n",
    )
    assert len(missing_binding) == 2
    assert all("Work Orchestrator binding" in item for item in missing_binding)


def test_unregistered_python_workers_and_go_schedules_fail(tmp_path: Path) -> None:
    python_worker = tmp_path / "python/football/src/football/product/roster_worker.py"
    generic_worker = tmp_path / "python/football/src/football/providers/worker.py"
    production_call = tmp_path / "python/football/src/football/product/legacy_sync.py"
    go_schedule = tmp_path / "go/api/internal/app/roster_schedule.go"
    python_worker.parent.mkdir(parents=True, exist_ok=True)
    generic_worker.parent.mkdir(parents=True, exist_ok=True)
    production_call.parent.mkdir(parents=True, exist_ok=True)
    go_schedule.parent.mkdir(parents=True)
    python_worker.write_text("class RosterSyncWorker:\n    pass\n", encoding="utf-8")
    generic_worker.write_text("class ProviderSyncWorkerV1:\n    pass\n", encoding="utf-8")
    production_call.write_text("ProviderSyncWorkerV1()\n", encoding="utf-8")
    go_schedule.write_text(
        "package app\nfunc scheduleRoster() { time.NewTicker(time.Minute) }\n",
        encoding="utf-8",
    )

    violations = _worker_entrypoint_violations(tmp_path)

    assert len(violations) == 3
    assert any("worker class RosterSyncWorker" in item for item in violations)
    assert any("test-only worker ProviderSyncWorkerV1" in item for item in violations)
    assert any("Go background schedule" in item for item in violations)
