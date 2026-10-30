"""One-file compression transaction: pull, encode, back up, replace, verify."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path, PurePosixPath

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


def compress_one(
    adb: AdbClient,
    backups: BackupStore,
    phone_path: str,
    settings: EncodingSettings,
    *,
    apply: bool,
) -> dict[str, object]:
    kind = media_kind(phone_path)
    old_size, old_mtime = adb.stat(phone_path)
    with tempfile.TemporaryDirectory(prefix="android-media-shrinker-") as temp_dir:
        directory = Path(temp_dir)
        source = directory / ("source" + PurePosixPath(phone_path).suffix.lower())
        output = directory / ("compressed" + PurePosixPath(phone_path).suffix.lower())
        adb.pull(phone_path, str(source))
        if source.stat().st_size != old_size:
            raise RuntimeError("Pulled file size differs from the phone; refusing to continue")
        encode(source, output, kind, settings)
        new_size = output.stat().st_size
        savings = 100 * (old_size - new_size) / old_size if old_size else 0.0
        result: dict[str, object] = {
            "path": phone_path, "kind": kind, "old_size": old_size,
            "new_size": new_size, "saving_percent": round(savings, 2), "replaced": False,
        }
        if savings < settings.min_saving_percent:
            result["reason"] = f"Saving {savings:.1f}% is below the {settings.min_saving_percent:.1f}% minimum"
            return result
        if not apply:
            result["reason"] = "Preview only; phone unchanged"
            return result
        if adb.stat(phone_path) != (old_size, old_mtime):
            raise RuntimeError("Phone file changed during compression; refusing to replace it")

        os.utime(output, ns=(source.stat().st_atime_ns, source.stat().st_mtime_ns))
        backup = backups.create(
            source, phone_path, media_kind=kind,
            settings={"video_crf": settings.video_crf, "jpeg_quality": settings.jpeg_quality,
                      "min_saving_percent": settings.min_saving_percent},
        )
        try:
            adb.push(str(output), phone_path)
            actual_size, _ = adb.stat(phone_path)
            if actual_size != new_size:
                raise RuntimeError("Uploaded file size mismatch; original is preserved in PC backup")
            adb.scan(phone_path)
        except Exception as exc:
            raise RuntimeError(f"Replacement failed; original backup {backup['id']} is retained: {exc}") from exc
        result.update({"replaced": True, "backup_id": backup["id"]})
        return result
