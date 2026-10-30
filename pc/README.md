# Android Media Shrinker (PC)

Cross-platform Python terminal app for safely selecting Android videos and JPEGs over ADB, previewing compression quality, saving recoverable PC backups, and restoring originals. The current interactive UI uses Textual; Python dependencies and commands are managed with uv.

## Requirements

- Python 3.11+ and [uv](https://docs.astral.sh/uv/).
- Android Platform Tools (`adb`) and FFmpeg (`ffmpeg` plus `ffprobe`). The app checks for these on `PATH` before asking what to do.
- USB debugging enabled and exactly one authorized Android device connected for phone operations.

Install the Python project dependencies and run the tool:

```sh
uv sync
uv run android-media-shrinker check
uv run android-media-shrinker
```

The TUI opens at `/sdcard`, the shared-storage root visible to Android file explorers. Browse folders such as `DCIM`, `Download`, `Movies`, and `Pictures`; app-private `Android/data` and `Android/obb` are excluded. Navigate with arrows; Space selects, Enter opens a folder or toggles a file, Backspace goes up, `P` previews, `C` compresses selected files after confirmation, `S` edits settings, `I` toggles JPEG visibility, and `R` lists/restores backups.

## External tools

If a required tool is missing, run `uv run android-media-shrinker setup`. It offers a global package-manager installation only after confirmation or removable project-local setup instructions. It never modifies the system or installs a binary without consent. Local executables can be placed in `pc/bins/`; this folder is added to the app process's PATH only and can be removed with the project. Local binary downloads are manual: use official sources and verify publisher checksums/signatures. Global options currently recognize winget, Homebrew, apt, dnf, pacman, and zypper where available.

## Commands

```sh
uv run android-media-shrinker list --path '/sdcard/Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Video'
uv run android-media-shrinker preview '/sdcard/DCIM/Camera/VID_001.mp4' --crf 27
uv run android-media-shrinker preview '/sdcard/DCIM/Camera/IMG_001.jpg' --include-images --jpeg-quality 85
uv run android-media-shrinker compress '/sdcard/DCIM/Camera/VID_001.mp4' --crf 27
uv run android-media-shrinker compress '/sdcard/DCIM/Camera/IMG_001.jpg' --include-images --apply
uv run android-media-shrinker backups
uv run android-media-shrinker restore <backup-id>
```

`compress` is preview/dry-run by default. Add `--apply` to replace after an interactive `REPLACE` confirmation; `--yes` skips that prompt and is intended only for deliberate scripts. JPEG work always requires `--include-images`. `preview` downloads the source and opens a side-by-side comparison in the system viewer. Video previews encode only three representative still frames (roughly 20%, 50%, and 80% of the clip), rather than re-encoding the whole video; they use FFmpeg's fast preset, so treat this as a quick quality estimate, not a guarantee of final playback quality. Adjust parameters with `--crf`, `--jpeg-quality`, and `--min-saving-percent` or the TUI settings screen.

## Safety and recovery

- Defaults follow the tested prototype: H.265/HEVC video (CRF 27, audio copied, `hvc1` tag), JPEG quality 85, and at least 20% size reduction. HEVC playback varies by device/app; JPEG is lossy. Preview carefully.
- Before a replacement, the tool checks that the phone file has not changed, creates a persistent original backup, records it in `android-originals/manifest.json`, then pushes and verifies the compressed output. Backups are never automatically deleted in this initial version.
- Use `backups` to find an ID and `restore <id>` to restore it. Existing phone files require an explicit `OVERWRITE` confirmation (or intentional `--yes`).
- Android writes are not atomic: interruption can leave an incomplete phone file. The original remains in the PC backup. A MediaStore scan is requested after replacement/restore, but preserving filesystem modification time does not guarantee Google Photos capture-date ordering.
- Keep sufficient PC and phone free space. The app cannot restore WhatsApp app-private metadata or guarantee that other apps support HEVC.

## Development

```sh
uv sync --dev
uv run pytest
```

Tests do not require a connected phone. Real-device checks should start with disposable/sample files and verify the Gallery/Files view and Google Photos dates before batch use.

GitHub Actions runs the locked dependency install, test suite, and CLI startup check on Ubuntu and Windows for changes under `pc/`.
