"""One-file compression transaction: pull, encode, back up, replace, verify."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable

from .adb import AdbClient
from .backups import BackupStore
from .encoding import EncodingSettings, encode


def media_kind(path: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in {".mp4", ".mov", ".m4v"}:
        return "video"
    if suffix in {".jpg", ".jpeg"}:
        return "image"
    raise ValueError(f"Unsupported media type: {suffix or '(no extension)'}")


@dataclass
class PreparedCompression:
    """A local encoded candidate that has not changed the phone."""

    temp_dir: tempfile.TemporaryDirectory[str]
    phone_path: str
    kind: str
    source: Path
    output: Path
    old_size: int
    old_mtime: int
    new_size: int
    saving_percent: float
    settings: EncodingSettings

    def result(self) -> dict[str, object]:
        return {
            "path": self.phone_path,
            "kind": self.kind,
            "old_size": self.old_size,
            "new_size": self.new_size,
            "saving_percent": round(self.saving_percent, 2),
            "replaced": False,
        }

    def cleanup(self) -> None:
        self.temp_dir.cleanup()


def prepare_one(
    adb: AdbClient,
    phone_path: str,
    settings: EncodingSettings,
    *,
    on_stage: Callable[[str], None] | None = None,
    on_progress: Callable[[int, int | None], None] | None = None,
) -> PreparedCompression:
    """Pull and encode a candidate without modifying the Android device."""
    kind = media_kind(phone_path)
    settings.validate()
    old_size, old_mtime = adb.stat(phone_path)
    temp_dir = tempfile.TemporaryDirectory(prefix="android-media-shrinker-")
    try:
        directory = Path(temp_dir.name)
        source = directory / ("source" + PurePosixPath(phone_path).suffix.lower())
        output = directory / ("compressed" + PurePosixPath(phone_path).suffix.lower())
        if on_stage:
            on_stage("Pulling original from phone")
        adb.pull(phone_path, str(source))
        if source.stat().st_size != old_size:
            raise RuntimeError("Pulled file size differs from the phone; refusing to continue")
        if on_stage:
            on_stage("Encoding compressed candidate")
        if on_progress is None:
            encode(source, output, kind, settings)
        else:
            encode(source, output, kind, settings, on_progress=on_progress)
        new_size = output.stat().st_size
        savings = 100 * (old_size - new_size) / old_size if old_size else 0.0
        return PreparedCompression(
            temp_dir, phone_path, kind, source, output, old_size, old_mtime,
            new_size, savings, settings,
        )
    except Exception:
        temp_dir.cleanup()
        raise


def replace_prepared(
    adb: AdbClient,
    backups: BackupStore,
    prepared: PreparedCompression,
    *,
    on_stage: Callable[[str], None] | None = None,
) -> dict[str, object]:
    """Back up and replace a candidate only after the caller confirms."""
    result = prepared.result()
    if prepared.saving_percent < prepared.settings.min_saving_percent:
        result["reason"] = (
            f"Saving {prepared.saving_percent:.1f}% is below the "
            f"{prepared.settings.min_saving_percent:.1f}% minimum"
        )
        return result
    if adb.stat(prepared.phone_path) != (prepared.old_size, prepared.old_mtime):
        raise RuntimeError("Phone file changed during compression; refusing to replace it")

    os.utime(prepared.output, ns=(prepared.source.stat().st_atime_ns, prepared.source.stat().st_mtime_ns))
    if on_stage:
        on_stage("Saving original backup")
    backup = backups.create(
        prepared.source,
        prepared.phone_path,
        media_kind=prepared.kind,
        settings={
            "video_crf": prepared.settings.video_crf,
            "jpeg_quality": prepared.settings.jpeg_quality,
            "min_saving_percent": prepared.settings.min_saving_percent,
        },
    )
    try:
        if on_stage:
            on_stage("Replacing phone file")
        adb.push(str(prepared.output), prepared.phone_path)
        actual_size, _ = adb.stat(prepared.phone_path)
        if actual_size != prepared.new_size:
            raise RuntimeError("Uploaded file size mismatch; original is preserved in PC backup")
        if on_stage:
            on_stage("Refreshing Android media library")
        adb.scan(prepared.phone_path)
    except Exception as exc:
        raise RuntimeError(f"Replacement failed; original backup {backup['id']} is retained: {exc}") from exc
    result.update({"replaced": True, "backup_id": backup["id"]})
    return result


def compress_one(
    adb: AdbClient,
    backups: BackupStore,
    phone_path: str,
    settings: EncodingSettings,
    *,
    apply: bool,
) -> dict[str, object]:
    prepared = prepare_one(adb, phone_path, settings)
    try:
        result = prepared.result()
        if prepared.saving_percent < settings.min_saving_percent:
            result["reason"] = (
                f"Saving {prepared.saving_percent:.1f}% is below the "
                f"{settings.min_saving_percent:.1f}% minimum"
            )
            return result
        if not apply:
            result["reason"] = "Preview only; phone unchanged"
            return result
        return replace_prepared(adb, backups, prepared)
    finally:
        prepared.cleanup()
