import json
from pathlib import Path
from pathlib import PureWindowsPath

import pytest

from pc_shrinker.adb import AdbClient
from pc_shrinker.backups import BackupStore
from pc_shrinker.encoding import (
    EncodingSettings,
    encode,
    image_to_terminal,
    make_preview,
    make_video_quality_preview,
    make_video_quality_samples,
    make_video_thumbnail_sheet,
    persist_preview,
)
from pc_shrinker.processor import compress_one, media_kind


def test_settings_validation_and_defaults():
    settings = EncodingSettings()
    settings.validate()
    assert settings.video_crf == 27
    assert settings.jpeg_quality == 85
    with pytest.raises(ValueError):
        EncodingSettings(video_crf=36).validate()


@pytest.mark.parametrize("path", ["/sdcard/DCIM/a.mp4", "/sdcard/Android/media/a.jpg"])
def test_android_path_accepts_user_storage(path):
    assert AdbClient.validate_path(path) == path


@pytest.mark.parametrize("path", ["/data/local/tmp/a", "/sdcard/../etc/passwd", "/sdcard/a\nb"])
def test_android_path_rejects_escape_and_control_characters(path):
    with pytest.raises(ValueError):
        AdbClient.validate_path(path)


def test_android_root_can_be_browsed():
    assert AdbClient.validate_path("/sdcard") == "/sdcard"


def test_android_listing_hides_restricted_data_and_obb_folders(monkeypatch):
    import subprocess

    client = AdbClient(executable="adb")
    output = "\n".join([
        "directory|0|1|/sdcard/Android/data",
        "directory|0|1|/sdcard/Android/obb",
        "directory|0|1|/sdcard/Android/media",
    ])
    monkeypatch.setattr(
        client, "shell",
        lambda command, check=True: subprocess.CompletedProcess([], 0, output, ""),
    )

    listed = client.list_dir("/sdcard/Android")

    assert [item.path for item in listed] == ["/sdcard/Android/media"]


def test_shared_storage_root_uses_physical_path_and_returns_sdcard_alias(monkeypatch):
    import subprocess

    client = AdbClient(executable="adb")
    captured = {}
    output = "\n".join([
        "directory|0|1|/storage/emulated/0/DCIM",
        "directory|0|1|/storage/emulated/0/.hidden",
        "directory|0|1|/storage/emulated/0/$recycle$",
        "regular file|42|2|/storage/emulated/0/read me.txt",
    ])

    def fake_shell(command, check=True):
        captured["command"] = command
        return subprocess.CompletedProcess([], 0, output, "")

    monkeypatch.setattr(client, "shell", fake_shell)
    listed = client.list_dir("/sdcard")

    assert "find /storage/emulated/0 " in captured["command"]
    assert {item.path for item in listed} == {"/sdcard/DCIM", "/sdcard/read me.txt"}


def test_adb_passes_windows_paths_as_single_subprocess_arguments(monkeypatch):
    import pc_shrinker.adb as adb_module

    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(adb_module.subprocess, "run", fake_run)
    client = AdbClient(executable="adb.exe")
    local_path = str(PureWindowsPath(r"C:\Users\Test User\media file.mp4"))

    client.pull("/sdcard/DCIM/media file.mp4", local_path)

    assert captured["args"] == ["adb.exe", "pull", "-a", "/sdcard/DCIM/media file.mp4", local_path]


def test_windows_global_install_uses_separate_adb_and_ffmpeg_packages(monkeypatch):
    import pc_shrinker.cli as cli

    monkeypatch.setattr(cli.platform, "system", lambda: "Windows")
    monkeypatch.setattr(cli, "shutil_which", lambda name: "winget.exe" if name == "winget" else None)

    assert cli._global_install_command("adb") == [
        "winget", "install", "--exact", "--id", "Google.PlatformTools"
    ]
    assert cli._global_install_command("ffmpeg") == [
        "winget", "install", "--exact", "--id", "Gyan.FFmpeg.Shared"
    ]


@pytest.mark.parametrize(("path", "kind"), [
    ("/sdcard/a.mp4", "video"), ("/sdcard/a.MOV", "video"),
    ("/sdcard/a.jpeg", "image"),
])
def test_media_kind(path, kind):
    assert media_kind(path) == kind


def test_unsupported_media_is_rejected():
    with pytest.raises(ValueError):
        media_kind("/sdcard/large.heic")


def test_backup_is_manifested_and_integrity_checked(tmp_path: Path):
    source = tmp_path / "original.mp4"
    source.write_bytes(b"original bytes")
    store = BackupStore(tmp_path / "backups")

    record = store.create(source, "/sdcard/DCIM/original.mp4", media_kind="video", settings={"crf": 27})

    assert store.verify(record).read_bytes() == b"original bytes"
    assert store.get(str(record["id"])) == record
    assert json.loads(store.manifest.read_text(encoding="utf-8")) == [record]


def test_backup_integrity_failure_is_reported(tmp_path: Path):
    source = tmp_path / "original.jpg"
    source.write_bytes(b"original")
    store = BackupStore(tmp_path / "backups")
    record = store.create(source, "/sdcard/DCIM/original.jpg", media_kind="image", settings={})
    store.backup_path(record).write_bytes(b"tampered")

    with pytest.raises(RuntimeError, match="integrity"):
        store.verify(record)


class FakeAdb:
    def __init__(self, destination_exists=False):
        self.destination_exists = destination_exists
        self.pushed = None
        self.scanned = None

    def exists(self, path):
        return self.destination_exists

    def push(self, local, remote):
        self.pushed = (Path(local).read_bytes(), remote)

    def stat(self, path):
        return len(self.pushed[0]), 123 if self.pushed else 0

    def scan(self, path):
        self.scanned = path

    def ensure_parent(self, path):
        self.parent_created = path


def test_restore_refuses_to_overwrite_without_explicit_confirmation(tmp_path: Path):
    source = tmp_path / "original.mp4"
    source.write_bytes(b"safe original")
    store = BackupStore(tmp_path / "backups")
    record = store.create(source, "/sdcard/DCIM/original.mp4", media_kind="video", settings={})
    adb = FakeAdb(destination_exists=True)

    with pytest.raises(FileExistsError):
        store.restore(str(record["id"]), adb)
    assert adb.pushed is None


def test_restore_with_confirmation_verifies_and_scans(tmp_path: Path):
    source = tmp_path / "original.mp4"
    source.write_bytes(b"safe original")
    store = BackupStore(tmp_path / "backups")
    record = store.create(source, "/sdcard/DCIM/original.mp4", media_kind="video", settings={})
    adb = FakeAdb(destination_exists=True)

    store.restore(str(record["id"]), adb, overwrite=True)

    assert adb.pushed == (b"safe original", "/sdcard/DCIM/original.mp4")
    assert adb.scanned == "/sdcard/DCIM/original.mp4"


class FakeProcessingAdb:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.push_record = None
        self.scanned = None

    def stat(self, path):
        current = self.push_record[0] if self.push_record else self.payload
        return len(current), 123

    def pull(self, remote, local):
        Path(local).write_bytes(self.payload)

    def push(self, local, remote):
        self.push_record = (Path(local).read_bytes(), remote)

    def scan(self, path):
        self.scanned = path


def test_compression_creates_backup_before_phone_write(tmp_path: Path, monkeypatch):
    import pc_shrinker.processor as processor

    adb = FakeProcessingAdb(b"original video payload")
    backups = BackupStore(tmp_path / "backups")

    def fake_encode(source, destination, kind, settings):
        destination.write_bytes(b"tiny")

    monkeypatch.setattr(processor, "encode", fake_encode)
    result = compress_one(
        adb, backups, "/sdcard/DCIM/clip.mp4", EncodingSettings(min_saving_percent=20), apply=True
    )

    assert result["replaced"] is True
    assert backups.verify(backups.get(str(result["backup_id"]))).read_bytes() == b"original video payload"
    assert adb.push_record == (b"tiny", "/sdcard/DCIM/clip.mp4")
    assert adb.scanned == "/sdcard/DCIM/clip.mp4"


def test_compression_below_saving_threshold_never_backs_up_or_pushes(tmp_path: Path, monkeypatch):
    import pc_shrinker.processor as processor

    adb = FakeProcessingAdb(b"original video payload")
    backups = BackupStore(tmp_path / "backups")
    monkeypatch.setattr(processor, "encode", lambda source, output, kind, settings: output.write_bytes(b"almost same"))

    result = compress_one(
        adb, backups, "/sdcard/DCIM/clip.mp4", EncodingSettings(min_saving_percent=95), apply=True
    )

    assert result["replaced"] is False
    assert adb.push_record is None
    assert backups.records() == []


def test_jpeg_compresses_and_builds_comparison_preview(tmp_path: Path):
    from PIL import Image

    original = tmp_path / "original.jpg"
    compressed = tmp_path / "compressed.jpg"
    comparison = tmp_path / "comparison.jpg"
    Image.new("RGB", (64, 48), color=(150, 90, 40)).save(original, quality=98)

    encode(original, compressed, "image", EncodingSettings(jpeg_quality=75))
    make_preview(original, compressed, "image", comparison)

    assert compressed.is_file()
    assert Image.open(comparison).size == (960, 332)


def test_video_quality_preview_encodes_only_sample_frames(tmp_path: Path):
    import subprocess

    source = tmp_path / "source.mp4"
    comparison = tmp_path / "comparison.jpg"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
         "testsrc=size=160x120:rate=8", "-t", "1.5", "-pix_fmt", "yuv420p", "-y", str(source)],
        check=True,
    )

    make_video_quality_preview(source, EncodingSettings(video_crf=30), comparison)

    from PIL import Image
    with Image.open(comparison) as sheet:
        assert sheet.size == (960, (300 + 32) * 4)


def test_video_identification_thumbnails_and_interactive_samples(tmp_path: Path):
    import subprocess

    source = tmp_path / "source.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
         "testsrc=size=160x120:rate=8", "-t", "1.5", "-pix_fmt", "yuv420p", "-y", str(source)],
        check=True,
    )

    thumbnails = make_video_thumbnail_sheet(source, tmp_path / "thumbnails.jpg")
    samples = make_video_quality_samples(source, EncodingSettings(video_crf=30), tmp_path / "samples")
    terminal_render = image_to_terminal(thumbnails)

    assert thumbnails.is_file()
    assert len(samples) == 4 and all(path.is_file() for path in samples)
    assert terminal_render.plain and "▀" in terminal_render.plain


def test_preview_persistence_copies_to_destination_without_rename(tmp_path: Path):
    source = tmp_path / "temporary" / "preview.jpg"
    destination = tmp_path / "backups" / "previews" / "preview.jpg"
    source.parent.mkdir()
    source.write_bytes(b"preview image")

    persist_preview(source, destination)

    assert source.read_bytes() == destination.read_bytes() == b"preview image"
    assert source.exists()
