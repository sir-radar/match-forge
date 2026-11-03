"""Exercise the pinned MCP server locally; all Git changes occur in a temporary repo."""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


class Client:
    def __init__(self, command: list[str], cwd: Path, env: dict[str, str], log: Any) -> None:
        self.process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=log,
            text=True,
            bufsize=1,
        )
        self.responses: queue.Queue[str] = queue.Queue()
        self.serial = 0
        threading.Thread(target=self._read, daemon=True).start()
        self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "matchforge-local-verification", "version": "1"},
            },
        )
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _read(self) -> None:
        assert self.process.stdout
        for line in self.process.stdout:
            self.responses.put(line)

    def send(self, message: dict[str, Any]) -> None:
        assert self.process.stdin
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def request(self, method: str, params: dict[str, Any]) -> Any:
        self.serial += 1
        self.send({"jsonrpc": "2.0", "id": self.serial, "method": method, "params": params})
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            response = json.loads(self.responses.get(timeout=max(0.1, deadline - time.monotonic())))
            if response.get("id") != self.serial:
                continue
            if "error" in response:
                raise RuntimeError(response["error"])
            return response["result"]
        raise TimeoutError(method)

    def call(self, name: str, **arguments: Any) -> Any:
        result = self.request("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise RuntimeError(result)
        text = "\n".join(c.get("text", "") for c in result.get("content", []))
        return json.loads(text)

    def close(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=10)


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def wait_symbol(
    client: Client, root: Path, present: str, absent: str = "", expected_path: str = ""
) -> float:
    start = time.monotonic()
    while time.monotonic() - start < 60:
        data = client.call(
            "search_graph",
            project=str(root),
            name_pattern=present,
            limit=8,
            max_output_tokens=1200,
            format="json",
        )
        rendered = json.dumps(data)
        old = (
            client.call(
                "search_graph",
                project=str(root),
                name_pattern=absent,
                limit=8,
                max_output_tokens=1200,
                format="json",
            )
            if absent
            else {}
        )
        if (
            present in rendered
            and (not absent or absent not in json.dumps(old))
            and (not expected_path or expected_path in rendered)
        ):
            return round(time.monotonic() - start, 3)
        time.sleep(1)
    raise AssertionError(f"Automatic synchronization failed: present={present}, absent={absent}")


def fixture_checks(binary: Path, env: dict[str, str], log: Any) -> dict[str, Any]:
    results: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="matchforge-cbm-probe-") as directory:
        root = Path(directory).resolve()
        git(root, "init", "-q", "-b", "base")
        git(root, "config", "user.name", "Local verification")
        git(root, "config", "user.email", "verification@localhost")
        (root / "branch.py").write_text("def mf_probe_base():\n    return 1\n")
        (root / "stable.py").write_text("def mf_probe_stable():\n    return 1\n")
        git(root, "add", ".")
        git(root, "commit", "-qm", "base fixture")
        git(root, "checkout", "-qb", "alternate")
        (root / "branch.py").write_text("def mf_probe_alternate():\n    return 2\n")
        git(root, "add", ".")
        git(root, "commit", "-qm", "alternate fixture")
        git(root, "checkout", "-q", "base")
        client = Client(
            [str(binary), "--ui=false"], root, env | {"CBM_ALLOWED_ROOT": str(root)}, log
        )
        try:
            client.call("index_repository", repo_path=str(root), mode="full", doc_candidates=False)
            results["watch"] = client.call("index_status", project=str(root), format="json")
            nested = root / "new/deep/source.py"
            nested.parent.mkdir(parents=True)
            nested.write_text("def mf_probe_created():\n    return 1\n")
            results["new_file_and_recursive_directory_seconds"] = wait_symbol(
                client, root, "mf_probe_created"
            )
            nested.write_text("def mf_probe_modified():\n    return 2\n")
            results["modified_seconds"] = wait_symbol(
                client, root, "mf_probe_modified", "mf_probe_created"
            )
            moved = root / "moved/source.py"
            moved.parent.mkdir()
            shutil.move(str(nested.parent.parent), str(moved.parent / "renamed"))
            moved = moved.parent / "renamed/deep/source.py"
            moved.write_text("def mf_probe_moved():\n    return 3\n")
            results["directory_move_seconds"] = wait_symbol(
                client, root, "mf_probe_moved", "mf_probe_modified"
            )
            renamed = moved.with_name("renamed.py")
            moved.rename(renamed)
            moved = renamed
            results["file_rename_seconds"] = wait_symbol(
                client, root, "mf_probe_moved", expected_path="moved/renamed/deep/renamed.py"
            )
            for number in range(30):
                moved.write_text(f"def mf_probe_burst_{number}():\n    return {number}\n")
            results["burst_seconds"] = wait_symbol(
                client, root, "mf_probe_burst_29", "mf_probe_moved"
            )
            shutil.rmtree(root / "moved")
            results["deleted_directory_seconds"] = wait_symbol(
                client, root, "mf_probe_stable", "mf_probe_burst_29"
            )
            git(root, "checkout", "-q", "alternate")
            results["branch_switch_seconds"] = wait_symbol(
                client, root, "mf_probe_alternate", "mf_probe_base"
            )
            git(root, "checkout", "-q", "base")
            results["branch_return_seconds"] = wait_symbol(
                client, root, "mf_probe_base", "mf_probe_alternate"
            )
            for filename, content in {
                "contract.schema.json": '{"title":"MatchForge probe","type":"object"}',
                "migration.sql": "CREATE TABLE mf_probe_table (id integer);",
                "architecture.md": "# mf_probe_architecture\nCurrent contract.\n",
            }.items():
                (root / filename).write_text(content)
            results["architecture_document_seconds"] = wait_symbol(
                client, root, "mf_probe_architecture"
            )
            results["sql_table_seconds"] = wait_symbol(client, root, "mf_probe_table")
            (root / "architecture.md").write_text(
                "# mf_probe_changed_contract\nChanged contract.\n"
            )
            results["architecture_change_seconds"] = wait_symbol(
                client, root, "mf_probe_changed_contract", "mf_probe_architecture"
            )
            results["contract_coverage"] = client.call(
                "check_index_coverage",
                project=str(root),
                paths=["contract.schema.json", "migration.sql", "architecture.md"],
                format="json",
            )
            assert all(
                item["freshness"] == "metadata_match"
                for item in results["contract_coverage"]["paths"]
            )
            client.close()
            (root / "offline.py").write_text("def mf_probe_offline():\n    return 4\n")
            client = Client(
                [str(binary), "--ui=false"], root, env | {"CBM_ALLOWED_ROOT": str(root)}, log
            )
            results["native_restart_seconds"] = wait_symbol(client, root, "mf_probe_offline")
            results["final_status"] = client.call("index_status", project=str(root), format="json")
        finally:
            try:
                client.call("delete_project", project=str(root))
            finally:
                client.close()
    results["temporary_repo_removed"] = not root.exists()
    return results


def main() -> None:
    common = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        text=True,
    ).strip()
    shared = Path(common).parent
    binary = shared / ".tools/code-intelligence/0.12.1/codebase-memory-mcp"
    output = ROOT / ".local/code-intelligence-verification.json"
    output.parent.mkdir(exist_ok=True)
    env = os.environ | {"CBM_CACHE_DIR": str(shared / ".local/code-intelligence")}
    with (output.with_suffix(".log")).open("w") as log:
        client = Client(["sh", str(ROOT / "scripts/code-intelligence.sh"), "serve"], ROOT, env, log)
        try:
            tools = client.request("tools/list", {})
            status = client.call(
                "index_status", project=str(ROOT), diagnostics="summary", format="json"
            )
            navigation = client.call(
                "search_graph",
                project=str(ROOT),
                name_pattern="normalize_resource",
                limit=8,
                max_output_tokens=1200,
                format="json",
            )
            assert "normalization/pipeline.py" in json.dumps(navigation)
            assert "search_graph" in json.dumps(tools)
        finally:
            client.close()
        results = {
            "launcher_status": status,
            "navigation": navigation,
            "synchronization": fixture_checks(binary, env, log),
        }
    output.write_text(json.dumps(results, indent=2) + "\n")
    print(f"PASS: launcher, targeted navigation and native synchronization; {output}")


if __name__ == "__main__":
    main()
