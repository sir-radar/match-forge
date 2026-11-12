"""Local encrypted Restic destination with explicit volume and key enrollment."""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import pwd
import shlex
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.backup_recovery import recovery_estimate
from scripts.capture_architecture_v2_baseline import ROOT
from scripts.recovery_scope import load_plan


class BackupError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class BackupConfig:
    mount: Path
    volume_uuid: str
    repository_id: str
    password_file: str
    keychain_service: str

    @classmethod
    def load(cls) -> BackupConfig:
        if os.environ.get("MATCHFORGE_BACKUP_ENABLED") != "true":
            raise BackupError(
                "DISABLED",
                "Backup activation is disabled. Complete drive and recovery-key setup first.",
            )
        values = [
            os.environ.get("MATCHFORGE_BACKUP_" + key, "")
            for key in ("MOUNT", "VOLUME_UUID", "REPOSITORY_ID")
        ]
        if not all(values) or os.environ.get("MATCHFORGE_BACKUP_RECOVERY_KEY_RETAINED") != "true":
            raise BackupError(
                "UNCONFIGURED", "Enroll the external drive and retain a separate recovery password."
            )
        return cls(
            Path(values[0]),
            values[1],
            values[2],
            os.environ.get("MATCHFORGE_BACKUP_PASSWORD_FILE", ""),
            os.environ.get("MATCHFORGE_BACKUP_KEYCHAIN_SERVICE", ""),
        )


def validate_volume(info: dict[str, Any], config: BackupConfig, mounted: bool) -> None:
    if not mounted or info.get("MountPoint") != str(config.mount):
        raise BackupError(
            "DISCONNECTED", "Connect the enrolled external drive at its configured mount point."
        )
    if info.get("Internal") is not False or info.get("VolumeUUID") != config.volume_uuid:
        raise BackupError(
            "WRONG_DRIVE", "This is not the enrolled external drive. Reconnect the correct drive."
        )
    if info.get("WritableVolume", info.get("Writable")) is not True:
        raise BackupError(
            "READ_ONLY", "The external drive is read-only. Check its permissions and filesystem."
        )
    if not info.get("FilesystemType"):
        raise BackupError(
            "FILESYSTEM_UNKNOWN", "The external drive filesystem could not be verified."
        )


def inspect_volume(config: BackupConfig) -> dict[str, Any]:
    if not config.mount.is_absolute() or config.mount.is_symlink():
        raise BackupError("WRONG_DRIVE", "Configure the actual external volume mount point.")
    try:
        result = subprocess.run(
            ["diskutil", "info", "-plist", str(config.mount)],
            capture_output=True,
            check=True,
            timeout=15,
        )
        info = plistlib.loads(result.stdout)
        validate_volume(info, config, os.path.ismount(config.mount))
        usage = shutil.disk_usage(config.mount)
    except (OSError, subprocess.SubprocessError, plistlib.InvalidFileException) as error:
        raise BackupError(
            "DISCONNECTED", "Connect the enrolled external drive and retry."
        ) from error
    return {
        "volume_uuid": config.volume_uuid,
        "filesystem": info["FilesystemType"],
        "filesystem_encrypted": info.get("Encryption") is True,
        "free_bytes": usage.free,
        "capacity_bytes": usage.total,
        "device_id": config.mount.stat().st_dev,
    }


def credential_environment(config: BackupConfig) -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("RESTIC_")}
    environment["GOMAXPROCS"] = "2"
    if config.password_file and not config.keychain_service:
        path = Path(config.password_file)
        try:
            metadata = path.lstat()
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or metadata.st_mode & 0o077
                or not path.read_bytes().strip()
            ):
                raise OSError("unprotected password file")
        except OSError as error:
            raise BackupError(
                "CREDENTIALS",
                "Use an owner-only nonempty password file (chmod 600), or macOS Keychain.",
            ) from error
        environment["RESTIC_PASSWORD_FILE"] = str(path.resolve())
    elif config.keychain_service and not config.password_file:
        command = [
            "/usr/bin/security",
            "find-generic-password",
            "-a",
            pwd.getpwuid(os.getuid()).pw_name,
            "-s",
            config.keychain_service,
            "-w",
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                check=True,
                timeout=15,
            )
            if not result.stdout.strip():
                raise ValueError("empty Keychain password")
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            raise BackupError(
                "CREDENTIALS", "Unlock the enrolled backup password in macOS Keychain."
            ) from error
        environment["RESTIC_PASSWORD_COMMAND"] = shlex.join(command)
    else:
        raise BackupError(
            "CREDENTIALS", "Configure exactly one password source: Keychain or an owner-only file."
        )
    return environment


class Restic:
    def __init__(
        self, repository: Path, environment: dict[str, str], device_id: int | None = None
    ) -> None:
        self.repository = repository
        self.environment = environment
        self.binary = str(ROOT / ".tools/bin/restic")
        self.device_id = device_id

    def run(self, *arguments: str) -> str:
        descriptor = os.open(self.repository, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            if self.device_id is not None and os.fstat(descriptor).st_dev != self.device_id:
                raise BackupError(
                    "WRONG_DRIVE",
                    "The repository moved to another filesystem; reconnect the enrolled drive.",
                )
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import os,sys; os.fchdir(int(sys.argv[1])); "
                    "os.execve(sys.argv[2],sys.argv[2:],os.environ)",
                    str(descriptor),
                    self.binary,
                    "--repo",
                    ".",
                    "--no-cache",
                    *arguments,
                ],
                env=self.environment,
                pass_fds=(descriptor,),
                capture_output=True,
                text=True,
                timeout=14400,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise BackupError(
                "INTERRUPTED",
                "Backup command interrupted or unavailable. Check Restic 0.19.1 "
                "and retry manually.",
            ) from error
        finally:
            os.close(descriptor)
        if result.returncode:
            # Restic never prints the password; the protected run log keeps the cause.
            print(
                json.dumps(
                    {
                        "status": "RECOVERY_DIAGNOSTIC",
                        "private_restic_command": arguments[0] if arguments else None,
                        "private_restic_exit_code": result.returncode,
                        "private_restic_stderr": result.stderr[-2000:],
                    }
                ),
                file=sys.stderr,
            )
            code = (
                "CREDENTIALS"
                if "wrong password" in result.stderr.lower()
                else "VERIFICATION_FAILED"
            )
            raise BackupError(
                code,
                "Backup repository operation failed. Check the drive, password, "
                "capacity and repository integrity.",
            )
        return result.stdout

    def require_version(self) -> None:
        version = subprocess.run(
            [self.binary, "version"], capture_output=True, text=True, check=True
        )
        if not version.stdout.startswith("restic 0.19.1 "):
            raise BackupError("TOOL_VERSION", "Use tested Restic version 0.19.1.")

    def identity(self) -> str:
        self.require_version()
        value = json.loads(self.run("cat", "config"))
        if value["version"] != 2:
            raise BackupError(
                "REPOSITORY_VERSION", "An encrypted Restic version 2 repository is required."
            )
        return str(value["id"])


def destination(config: BackupConfig) -> tuple[Restic, dict[str, Any]]:
    volume = inspect_volume(config)
    repository = config.mount / "MatchForgeBackup"
    if repository.is_symlink() or not (repository / "config").is_file():
        raise BackupError(
            "REPOSITORY_MISSING",
            "Initialize the dedicated MatchForgeBackup repository explicitly; "
            "existing drive files are preserved.",
        )
    restic = Restic(repository, credential_environment(config), volume["device_id"])
    if restic.identity() != config.repository_id:
        raise BackupError(
            "WRONG_REPOSITORY", "The encrypted repository identity differs from enrollment."
        )
    return restic, volume


def require_capacity(available: int, required: int, capacity: int) -> bool:
    if available < required:
        shortfall = required - available
        raise BackupError(
            "LOW_SPACE",
            f"Insufficient capacity: at least {shortfall:,} more bytes needed. "
            "No files were omitted or deleted.",
        )
    return available - required < capacity // 5


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Explicitly enroll a new external repository; never reformat a drive."
    )
    parser.add_argument("--mount", type=Path, required=True)
    parser.add_argument("--volume-uuid", required=True)
    secrets = parser.add_mutually_exclusive_group(required=True)
    secrets.add_argument("--password-file", default="")
    secrets.add_argument("--keychain-service", default="")
    parser.add_argument("--recovery-key-retained", action="store_true", required=True)
    parser.add_argument("--recoverable-inventory", type=Path)
    args = parser.parse_args()
    config = BackupConfig(
        args.mount, args.volume_uuid, "", args.password_file, args.keychain_service
    )
    volume = inspect_volume(config)
    repository = config.mount / "MatchForgeBackup"
    if repository.exists() or repository.is_symlink():
        raise BackupError(
            "REPOSITORY_EXISTS",
            "Destination already exists; authenticate it without reinitializing.",
        )
    restic = Restic(repository, credential_environment(config), volume["device_id"])
    restic.require_version()
    estimate = recovery_estimate(
        Path(os.environ.get("FOOTBALL_DATA_ROOT", str(ROOT / ".local/football-data"))),
        load_plan(args.recoverable_inventory) if args.recoverable_inventory else None,
    )
    headroom_warning = require_capacity(
        volume["free_bytes"], estimate["estimated_staging_bytes"], volume["capacity_bytes"]
    )
    descriptor = os.open(config.mount, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if os.fstat(descriptor).st_dev != volume["device_id"]:
            raise BackupError("WRONG_DRIVE", "Volume changed during enrollment.")
        os.mkdir("MatchForgeBackup", mode=0o700, dir_fd=descriptor)
    finally:
        os.close(descriptor)
    inspect_volume(config)
    restic.run("init", "--repository-version", "2")
    print(
        json.dumps(
            {
                "repository_id": restic.identity(),
                "operating_activation": False,
                "estimated_staging_bytes": estimate["estimated_staging_bytes"],
                "headroom_warning": headroom_warning,
            }
        )
    )


if __name__ == "__main__":
    main()
