"""Small, testable ADB wrapper. Android paths are always POSIX paths."""

from __future__ import annotations

import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import quote
import mimetypes
import re

SHARED_STORAGE = "/storage/emulated/0"


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
        # /sdcard commonly resolves to /storage/self/primary. Toybox find does not
        # follow that symlink when it is the starting point, yielding zero entries.
        shell_path = SHARED_STORAGE + path.removeprefix("/sdcard")
        fmt = shlex.quote("%F|%s|%Y|%n")
        command = f"find {shlex.quote(shell_path)} -mindepth 1 -maxdepth 1 -exec stat -c {fmt} {{}} +"
        result = self.shell(command, check=False)
        if result.returncode:
            # Some Android toybox versions lack batched -exec; still one ADB round trip.
            command = (
                f"find {shlex.quote(shell_path)} -mindepth 1 -maxdepth 1 | "
                f"while IFS= read -r p; do stat -c {fmt} \"$p\"; done"
            )
            result = self.shell(command, check=False)
        if result.returncode:
            raise AdbError(result.stderr.strip() or f"Cannot list {path}")

        entries: list[RemoteItem] = []
        for line in result.stdout.splitlines():
            try:
                kind, size, mtime, remote_path = line.split("|", 3)
                if remote_path == SHARED_STORAGE:
                    remote_path = "/sdcard"
                elif remote_path.startswith(SHARED_STORAGE + "/"):
                    remote_path = "/sdcard" + remote_path.removeprefix(SHARED_STORAGE)
                remote_path = self.validate_path(remote_path)
                name = PurePosixPath(remote_path).name
                if name.startswith((".", "$")) or name.endswith("$"):
                    continue
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

    def open_on_device(self, path: str) -> None:
        """Launch Android's registered viewer for a shared-storage media file."""
        path = self.validate_path(path)
        mime_type = mimetypes.guess_type(path)[0]
        if not mime_type or not mime_type.startswith(("video/", "image/")):
            raise ValueError("Only supported video and image files can be opened on the phone")

        # Prefer MediaStore content URIs: unlike file:// URIs, Android apps can
        # safely receive them through the standard VIEW intent and show a chooser.
        physical_path = SHARED_STORAGE + path.removeprefix("/sdcard")
        sql_path = physical_path.replace("'", "''")
        where = f"_data='{sql_path}'"
        query = self.shell(
            "content query --uri content://media/external/file --projection _id "
            f"--where {shlex.quote(where)}",
            check=False,
        )
        row = re.search(r"_id=(\d+)", query.stdout)
        uri = f"content://media/external/file/{row.group(1)}" if row else "file://" + quote(physical_path, safe="/")
        result = self.shell(
            "am start -a android.intent.action.VIEW "
            f"-d {shlex.quote(uri)} -t {shlex.quote(mime_type)}",
            check=False,
        )
        if result.returncode:
            raise AdbError(result.stderr.strip() or result.stdout.strip() or "No phone app can open this file")
