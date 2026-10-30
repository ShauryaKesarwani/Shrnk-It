"""Durable original backups and restore operations."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .adb import AdbClient


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class BackupStore:
    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest = self.root / "manifest.json"

    def records(self) -> list[dict[str, object]]:
        if not self.manifest.exists():
            return []
        try:
            data = json.loads(self.manifest.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Cannot read backup manifest {self.manifest}: {exc}") from exc

    def create(self, source: Path, phone_path: str, *, media_kind: str, settings: dict[str, object]) -> dict[str, object]:
        backup_id = uuid.uuid4().hex[:12]
        relative = Path("files") / backup_id / Path(*phone_path.strip("/").split("/"))
        destination = self.root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        record: dict[str, object] = {
            "id": backup_id,
            "phone_path": phone_path,
            "backup_path": relative.as_posix(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "size": destination.stat().st_size,
            "sha256": sha256(destination),
            "media_kind": media_kind,
            "settings": settings,
        }
        records = self.records()
        records.append(record)
        self._write(records)
        return record

    def backup_path(self, record: dict[str, object]) -> Path:
        path = (self.root / str(record["backup_path"])).resolve()
        if not path.is_relative_to(self.root):
            raise RuntimeError("Backup path escapes backup directory")
        return path

    def get(self, backup_id: str) -> dict[str, object]:
        for record in self.records():
            if record.get("id") == backup_id:
                return record
        raise KeyError(f"No backup with id {backup_id}")

    def verify(self, record: dict[str, object]) -> Path:
        path = self.backup_path(record)
        if not path.is_file() or path.stat().st_size != record.get("size"):
            raise RuntimeError("Backup is missing or has an unexpected size")
        if sha256(path) != record.get("sha256"):
            raise RuntimeError("Backup integrity check failed (SHA-256 mismatch)")
        return path

    def restore(self, backup_id: str, adb: AdbClient, *, overwrite: bool = False) -> None:
        record = self.get(backup_id)
        backup = self.verify(record)
        phone_path = str(record["phone_path"])
        if adb.exists(phone_path) and not overwrite:
            raise FileExistsError(f"Destination exists on phone: {phone_path}; confirm overwrite explicitly")
        adb.ensure_parent(phone_path)
        adb.push(str(backup), phone_path)
        size, _ = adb.stat(phone_path)
        if size != int(record["size"]):
            raise RuntimeError("Restored file size does not match the backup")
        adb.scan(phone_path)

    def _write(self, records: list[dict[str, object]]) -> None:
        temporary = self.manifest.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.manifest)
