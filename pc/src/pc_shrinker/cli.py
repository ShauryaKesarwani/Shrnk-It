"""CLI entry point and interactive setup assistant."""

from __future__ import annotations

import argparse
import os
import platform
import shlex
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path

from .adb import AdbClient
from .backups import BackupStore
from .encoding import EncodingSettings, available_tools, encode, make_preview
from .processor import compress_one, media_kind

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_BIN = PROJECT_ROOT / "bins"


def configure_local_bins() -> None:
    """Use removable project-local tools without editing the user's PATH."""
    if LOCAL_BIN.is_dir():
        os.environ["PATH"] = str(LOCAL_BIN) + os.pathsep + os.environ.get("PATH", "")


def _backup_dir(value: str) -> Path:
    return Path(value).expanduser()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="android-media-shrinker",
        description="Preview and safely compress Android media over ADB.",
    )
    parser.add_argument("--backup-dir", default="android-originals", help="Persistent PC backup folder")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("ui", help="Open the interactive Textual browser")
    sub.add_parser("check", help="Check required tools and connected device")
    sub.add_parser("setup", help="Choose how to install missing external tools")

    listing = sub.add_parser("list", help="List supported files in an Android folder")
    listing.add_argument("--path", default="/sdcard/DCIM/Camera")
    listing.add_argument("--include-images", action="store_true")

    preview = sub.add_parser("preview", help="Create a local quality comparison for one phone file")
    preview.add_argument("path")
    preview.add_argument("--include-images", action="store_true")
    preview.add_argument("--crf", type=int, default=27)
    preview.add_argument("--jpeg-quality", type=int, default=85)
    preview.add_argument("--min-saving-percent", type=float, default=20)

    compress = sub.add_parser("compress", help="Preview or replace explicitly selected phone files")
    compress.add_argument("paths", nargs="+")
    compress.add_argument("--include-images", action="store_true")
    compress.add_argument("--apply", action="store_true", help="Replace phone files after verified backup")
    compress.add_argument("--yes", action="store_true", help="Skip the final confirmation (requires --apply)")
    compress.add_argument("--crf", type=int, default=27)
    compress.add_argument("--jpeg-quality", type=int, default=85)
    compress.add_argument("--min-saving-percent", type=float, default=20)

    sub.add_parser("backups", help="List available original-file backups")
    restore = sub.add_parser("restore", help="Restore a PC backup to its original phone path")
    restore.add_argument("backup_id")
    restore.add_argument("--yes", action="store_true", help="Confirm restore; required for non-interactive use")
    return parser


def main() -> None:
    configure_local_bins()
    parser = build_parser()
    args = parser.parse_args()
    command = args.command or "ui"
    backup_dir = _backup_dir(args.backup_dir)
    backups = BackupStore(backup_dir)

    try:
        if command == "setup":
            setup_tools()
        elif command == "check":
            check_tools()
        elif command == "ui":
            from .tui import MediaApp
            MediaApp(backup_dir=backup_dir).run()
        elif command == "list":
            list_files(args.path, args.include_images)
        elif command == "preview":
            show_preview(args.path, args.include_images, settings_from(args), backups)
        elif command == "compress":
            compress_files(args, backups)
        elif command == "backups":
            list_backups(backups)
        elif command == "restore":
            restore_backup(args, backups)
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def check_tools() -> None:
    tools = available_tools()
    for name, path in tools.items():
        print(f"{'OK' if path else 'MISSING':7} {name}: {path or 'not found on PATH'}")
    if tools["adb"]:
        try:
            device = AdbClient().require_one_device()
            print(f"OK      authorized Android device: {device}")
        except RuntimeError as exc:
            print(f"DEVICE  {exc}")


def setup_tools() -> None:
    missing = [name for name, path in available_tools().items() if path is None]
    if not missing:
        print("ADB, FFmpeg, and ffprobe are already available.")
        return
    print("Missing: " + ", ".join(missing))
    handled: set[str] = set()
    for name in missing:
        target = "ffmpeg" if name == "ffprobe" else name
        if target in handled:
            continue
        handled.add(target)
        print(f"\n{name}: [g] global package-manager install, [l] local pc/bins setup instructions, [s] skip")
        choice = input("Choose (g/l/s): ").strip().lower()
        if choice == "g":
            command = _global_install_command(target)
            if not command:
                print("No supported package manager detected. Use the local/manual option.")
                continue
            print("Will run: " + " ".join(shlex.quote(part) for part in command))
            if input("Type INSTALL to run this system package-manager command: ").strip() != "INSTALL":
                print("Skipped.")
                continue
            result = subprocess.run(command, check=False)
            if result.returncode:
                print(f"Installer exited with status {result.returncode}.")
        elif choice == "l":
            LOCAL_BIN.mkdir(parents=True, exist_ok=True)
            print(f"Place the platform's adb/ffmpeg/ffprobe executables in {LOCAL_BIN}.")
            print("Android Platform Tools: https://developer.android.com/tools/releases/platform-tools")
            print("FFmpeg downloads: https://ffmpeg.org/download.html")
            print("Use official sources and check publisher-provided signatures/checksums.")
            print("This app does not download unchecked executable binaries.")
        else:
            print("Skipped.")
    print("\nRun `uv run android-media-shrinker check` to verify setup.")


def _global_install_command(binary: str) -> list[str] | None:
    system = platform.system()
    if system == "Windows":
        if not shutil_which("winget"):
            return None
        package = "Google.PlatformTools" if binary == "adb" else "Gyan.FFmpeg.Shared"
        return ["winget", "install", "--exact", "--id", package]
    if system == "Darwin":
        if shutil_which("brew"):
            package = "android-platform-tools" if binary == "adb" else "ffmpeg"
            return ["brew", "install", package]
        return None
    if system == "Linux":
        if shutil_which("pacman"):
            package = "android-tools" if binary == "adb" else "ffmpeg"
            return ["sudo", "pacman", "-S", package]
        if shutil_which("apt-get"):
            package = "android-tools-adb" if binary == "adb" else "ffmpeg"
            return ["sudo", "apt-get", "install", package]
        if shutil_which("dnf"):
            package = "android-tools" if binary == "adb" else "ffmpeg"
            return ["sudo", "dnf", "install", package]
        if shutil_which("zypper"):
            package = "android-tools" if binary == "adb" else "ffmpeg"
            return ["sudo", "zypper", "install", package]
    return None


def shutil_which(name: str) -> str | None:
    import shutil
    return shutil.which(name)


def settings_from(args: argparse.Namespace) -> EncodingSettings:
    settings = EncodingSettings(args.crf, args.jpeg_quality, args.min_saving_percent)
    settings.validate()
    return settings


def list_files(path: str, include_images: bool) -> None:
    adb = AdbClient()
    adb.require_one_device()
    for item in adb.list_dir(path):
        if item.is_dir or item.suffix in {".mp4", ".mov", ".m4v"} or (include_images and item.suffix in {".jpg", ".jpeg"}):
            print(f"{'DIR ' if item.is_dir else f'{item.size:>12}'}  {item.path}")


def show_preview(path: str, include_images: bool, settings: EncodingSettings, backups: BackupStore) -> None:
    adb = AdbClient()
    adb.require_one_device()
    kind = media_kind(path)
    if kind == "image" and not include_images:
        raise ValueError("JPEG preview is opt-in; pass --include-images")
    with tempfile.TemporaryDirectory(prefix="media-preview-") as td:
        directory = Path(td)
        source = directory / ("original" + Path(path).suffix.lower())
        compressed = directory / ("compressed" + Path(path).suffix.lower())
        sheet = directory / "quality-comparison.jpg"
        adb.pull(path, str(source))
        encode(source, compressed, kind, settings)
        make_preview(source, compressed, kind, sheet)
        persistent = backups.root / "previews" / f"{Path(path).stem}-comparison.jpg"
        persistent.parent.mkdir(parents=True, exist_ok=True)
        sheet.replace(persistent)
    webbrowser.open(persistent.resolve().as_uri())
    print(f"Opened original/compressed comparison: {persistent}")


def compress_files(args: argparse.Namespace, backups: BackupStore) -> None:
    settings = settings_from(args)
    for path in args.paths:
        kind = media_kind(path)
        if kind == "image" and not args.include_images:
            raise ValueError(f"JPEG is opt-in; pass --include-images for {path}")
    if args.yes and not args.apply:
        raise ValueError("--yes requires --apply")
    adb = AdbClient()
    adb.require_one_device()
    if args.apply and not args.yes:
        print("This will replace phone files after backing up the originals.")
        if input("Type REPLACE to continue: ").strip() != "REPLACE":
            print("Cancelled; phone unchanged.")
            return
    for path in args.paths:
        result = compress_one(adb, backups, path, settings, apply=args.apply)
        if result.get("replaced"):
            print(f"Replaced {path}; saved {result['saving_percent']}%; backup id {result['backup_id']}")
        else:
            print(f"Skipped {path}: {result.get('reason')}")


def list_backups(backups: BackupStore) -> None:
    records = backups.records()
    if not records:
        print(f"No backups in {backups.root}")
        return
    for record in records:
        print(f"{record['id']}  {record['created_at']}  {record['size']} bytes  {record['phone_path']}")


def restore_backup(args: argparse.Namespace, backups: BackupStore) -> None:
    record = backups.get(args.backup_id)
    adb = AdbClient()
    adb.require_one_device()
    exists = adb.exists(str(record["phone_path"]))
    overwrite = False
    if exists:
        if args.yes:
            overwrite = True
        else:
            overwrite = input(f"{record['phone_path']} exists. Type OVERWRITE to restore over it: ").strip() == "OVERWRITE"
            if not overwrite:
                print("Cancelled; phone unchanged.")
                return
    elif not args.yes:
        if input(f"Restore backup {args.backup_id} to {record['phone_path']}? Type RESTORE: ").strip() != "RESTORE":
            print("Cancelled; phone unchanged.")
            return
    backups.restore(args.backup_id, adb, overwrite=overwrite)
    print(f"Restored {args.backup_id} to {record['phone_path']}; MediaStore scan requested.")


if __name__ == "__main__":
    main()
