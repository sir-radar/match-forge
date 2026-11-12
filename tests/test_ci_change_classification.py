import subprocess
from pathlib import Path

import pytest

CLASSIFIER = Path(__file__).resolve().parents[1] / ".github/scripts/classify-changes.sh"


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", tmp_path], check=True)
    subprocess.run(
        ["git", "config", "user.email", "ci-test@example.invalid"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "CI Test"], cwd=tmp_path, check=True)
    return tmp_path


def commit(repository: Path, files: dict[str, str | None]) -> str:
    for path, content in files.items():
        target = repository / path
        if content is None:
            target.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "Fixture"], cwd=repository, check=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()


@pytest.mark.parametrize(
    ("before", "changes", "full_ci"),
    [
        pytest.param(
            {"README.md": "[Report](docs/evidence/summary report.json)\n"},
            {"docs/evidence/summary report.json": '{"file":"summary report.json"}\n'},
            False,
            id="documentation-only",
        ),
        pytest.param(
            {"docs/reference/example.json": "{}\n"},
            {"docs/reference/example.json": None, "docs/reference/renamed.json": "{}\n"},
            False,
            id="rename-documentation",
        ),
        pytest.param(
            {"scripts/read.py": 'Path("docs") / "data.json"\n', "docs/data.json": "{}\n"},
            {"docs/data.json": None},
            True,
            id="delete-program-input",
        ),
        pytest.param(
            {"scripts/read.py": 'Path("docs/new-data.json")\n'},
            {"docs/new-data.json": "{}\n"},
            True,
            id="add-program-input",
        ),
        pytest.param(
            {"Makefile": "validate: docs/make-input.json\n"},
            {"docs/make-input.json": "{}\n"},
            True,
            id="make-input",
        ),
        pytest.param(
            {"docs/project-status.json": '{"evidence_ref":"docs/evidence/receipt.json"}\n'},
            {"docs/evidence/receipt.json": "{}\n"},
            True,
            id="status-evidence-input",
        ),
        pytest.param(
            {"docs/input.json": "{}\n", "docs/manifest.json": '{"input":"input.json"}\n'},
            {"docs/input.json": None, "docs/manifest.json": "{}\n"},
            True,
            id="reference-in-base-only",
        ),
        *[
            pytest.param({}, {path: "{}\n"}, True, id=path)
            for path in (
                "docs/project-status.json",
                "docs/evidence/owner-decision-new.json",
                "docs/evidence/v4-issue-02-identity.json",
                "docs/evaluation/model.json",
                "docs/contracts/example.schema.json",
                "config/example.json",
            )
        ],
        pytest.param(
            {},
            {"docs/example.json": "{}\n", "scripts/task.py": "pass\n"},
            True,
            id="mixed-code-and-docs",
        ),
    ],
)
def test_ci_classifies_changed_json(
    repository: Path, before: dict[str, str | None], changes: dict[str, str | None], full_ci: bool
) -> None:
    base = commit(repository, {"README.md": "# Test\n", **before})
    commit(repository, changes)

    output = subprocess.check_output(["bash", CLASSIFIER, base], cwd=repository, text=True)

    assert output == f"code_changed={str(full_ci).lower()}\n"


def test_ci_runs_full_suite_when_base_is_unavailable(repository: Path) -> None:
    commit(repository, {"docs/example.json": "{}\n"})

    output = subprocess.check_output(["bash", CLASSIFIER, "f" * 40], cwd=repository, text=True)

    assert output == "code_changed=true\n"


def test_ci_checks_whitespace_for_documentation_json(repository: Path) -> None:
    base = commit(repository, {"README.md": "# Test\n"})
    commit(repository, {"docs/example.json": "{} \n"})

    result = subprocess.run(
        ["bash", CLASSIFIER, base], cwd=repository, capture_output=True, text=True
    )

    assert result.returncode != 0
    assert "trailing whitespace" in result.stderr
    assert result.stdout == ""
