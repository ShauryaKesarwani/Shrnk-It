"""Small, testable ADB wrapper. Android paths are always POSIX paths."""

from __future__ import annotations

import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True)
class RemoteItem:
    path: str
    is_dir: bool
    size: int
    mtime: int

    @property
    def name(self) -> str:
        return PurePosixPath(self.path).name or self.path

    @property
    def suffix(self) -> str:
        return PurePosixPath(self.path).suffix.lower()


class AdbError(RuntimeError):
    """ADB command failed or returned unexpected output."""


class AdbClient:
    def __init__(self, executable: str | None = None):
        self.executable = executable or shutil.which("adb")
        if not self.executable:
            raise AdbError("ADB (adb) is not installed or not on PATH")

    def run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [self.executable, *args], text=True, capture_output=True, check=False
        )
        if check and result.returncode:
            raise AdbError(result.stderr.strip() or result.stdout.strip() or "ADB command failed")
        return result

    def shell(self, command: str, *, check: bool = True) -> subprocess.CompletedProcess[str]:
        return self.run("shell", command, check=check)

    def devices(self) -> list[str]:
        result = self.run("devices")
        return [
            line.split("\t", 1)[0]
            for line in result.stdout.splitlines()[1:]
            if line.rstrip().endswith("\tdevice")
        ]

    def require_one_device(self) -> str:
        devices = self.devices()
        if len(devices) != 1:
            raise AdbError(f"Expected exactly one authorized device; found {len(devices)}")
        return devices[0]

    @staticmethod
    def validate_path(path: str) -> str:
        normalized = str(PurePosixPath(path))
        if (normalized != "/sdcard" and not normalized.startswith("/sdcard/")) or ".." in PurePosixPath(path).parts or "\n" in path or "\r" in path:
            raise ValueError("Phone paths must be files under /sdcard/")
        return normalized

    def stat(self, path: str) -> tuple[int, int]:
        path = self.validate_path(path)
        result = self.shell(f"stat -c '%s|%Y' {shlex.quote(path)}")
        try:
            size, mtime = result.stdout.strip().split("|", 1)
            return int(size), int(mtime)
        except (ValueError, TypeError) as exc:
            raise AdbError(f"Unexpected stat response for {path}: {result.stdout!r}") from exc

    def exists(self, path: str) -> bool:
        path = self.validate_path(path)
        command = f"if [ -e {shlex.quote(path)} ]; then echo exists; else echo missing; fi"
        result = self.shell(command)
        answer = result.stdout.strip()
        if answer not in {"exists", "missing"}:
            raise AdbError(f"Unexpected existence response for {path}: {answer!r}")
        return answer == "exists"

    def ensure_parent(self, path: str) -> None:
        parent = str(PurePosixPath(self.validate_path(path)).parent)
        result = self.shell(f"mkdir -p {shlex.quote(parent)}", check=False)
        if result.returncode:
            raise AdbError(result.stderr.strip() or f"Cannot create destination folder {parent}")

    def list_dir(self, path: str) -> list[RemoteItem]:
        path = self.validate_path(path)
        fmt = shlex.quote("%F|%s|%Y|%n")
        command = f"find {shlex.quote(path)} -mindepth 1 -maxdepth 1 -exec stat -c {fmt} {{}} +"
        result = self.shell(command, check=False)
        if result.returncode:
            # Some Android toybox versions lack batched -exec; still one ADB round trip.
            command = (
                f"find {shlex.quote(path)} -mindepth 1 -maxdepth 1 | "
                f"while IFS= read -r p; do stat -c {fmt} \"$p\"; done"
            )
            result = self.shell(command, check=False)
        if result.returncode:
            raise AdbError(result.stderr.strip() or f"Cannot list {path}")

        entries: list[RemoteItem] = []
        for line in result.stdout.splitlines():
            try:
                kind, size, mtime, remote_path = line.split("|", 3)
                remote_path = self.validate_path(remote_path)
                if remote_path in {"/sdcard/Android/data", "/sdcard/Android/obb"} or remote_path.startswith(
                    ("/sdcard/Android/data/", "/sdcard/Android/obb/")
                ):
                    continue
                entries.append(RemoteItem(remote_path, "directory" in kind, int(size), int(mtime)))
            except (ValueError, TypeError):
                continue
        return sorted(entries, key=lambda item: (not item.is_dir, -item.size, item.name.casefold()))

    def pull(self, remote: str, local: str) -> None:
        self.run("pull", "-a", self.validate_path(remote), local)

    def push(self, local: str, remote: str) -> None:
        self.run("push", "-a", local, self.validate_path(remote))

    def scan(self, path: str) -> None:
        path = self.validate_path(path)
        # The command is parsed by Android's POSIX shell; keep its argument quoted.
        result = self.shell(
            "content call --uri content://media --method scan_file --arg " + shlex.quote(path),
            check=False,
        )
        if result.returncode:
            raise AdbError(result.stderr.strip() or "MediaStore scan failed")
