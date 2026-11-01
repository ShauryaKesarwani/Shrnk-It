# Shrnk-It

**A safer way to shrink Android media—with a PC terminal app today and an Android app prototype in progress.** The PC app browses videos and JPEGs on a connected phone, previews likely quality changes, makes recoverable backups, and only replaces a phone file after you approve the encoded result.

[![PC app checks](https://github.com/ShauryaKesarwani/Shrnk-It/actions/workflows/pc-ci.yml/badge.svg)](https://github.com/ShauryaKesarwani/Shrnk-It/actions/workflows/pc-ci.yml)
![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![Textual TUI](https://img.shields.io/badge/Interface-Textual-7B2CBF)
![PC platforms](https://img.shields.io/badge/PC-Windows%20%7C%20Linux%20%7C%20macOS-informational)
![Android prototype](https://img.shields.io/badge/Android-Flutter%20prototype-3DDC84?logo=android&logoColor=white)

> **Current status:** The PC application is the practical, tested tool. The Flutter Android app is an experimental prototype; its Android storage and compression flows still need build and real-device validation. See [the mobile app notes](mobile-app/README.md).

## What it does

- Connects to Android over **ADB** and browses shared storage such as `DCIM`, `Movies`, and `Download`.
- Compresses videos to H.265/HEVC and optionally recompresses JPEG photos. Video and photo settings are adjustable.
- Offers four original-only video thumbnails for identifying a clip and a separate original/compressed quality preview.
- Shows batch and encoding progress, then asks for approval **after encoding and immediately before replacing each file**.
- Saves and verifies an original backup on the computer before any replacement; supports restoring backups.
- Can send a selected photo or video to Android's registered viewer with the `O` shortcut.

## Screenshots

**Identify a video** with four frames from the original clip:

![Textual video thumbnail preview showing four original video frames](docs/screenshots/pc-video-thumbnails.png)

**Track compression** with overall file progress and the current processing stage:

![Textual file browser during compression, showing the active encoding stage](docs/screenshots/pc-compression-progress.png)

## PC app: install and setup

The PC app works on **Windows and Linux**; macOS is also supported where the same ADB and FFmpeg setup works. It uses [uv](https://docs.astral.sh/uv/) to manage Python and project dependencies. You also need Android Platform Tools (`adb`) and FFmpeg (`ffmpeg` and `ffprobe`).

### 1. Install system tools

Install `uv` using its [official installation guide](https://docs.astral.sh/uv/getting-started/installation/), then install ADB and FFmpeg for your system:

<details>
<summary>Windows (PowerShell)</summary>

Install [Android Platform Tools](https://developer.android.com/tools/releases/platform-tools) and [FFmpeg](https://ffmpeg.org/download.html). If [winget](https://learn.microsoft.com/windows/package-manager/winget/) is available, these commands install the packages recognized by the app's setup helper:

```powershell
winget install --exact --id Google.PlatformTools
winget install --exact --id Gyan.FFmpeg.Shared
```

Open a new terminal after installation, then check that `adb`, `ffmpeg`, and `ffprobe` are on `PATH`.
</details>

<details>
<summary>Ubuntu / Debian Linux</summary>

```sh
sudo apt update
sudo apt install android-tools-adb ffmpeg
```

Install `uv` using the [official guide](https://docs.astral.sh/uv/getting-started/installation/).
</details>

<details>
<summary>macOS</summary>

With [Homebrew](https://brew.sh/):

```sh
brew install android-platform-tools ffmpeg
```

Install `uv` using the [official guide](https://docs.astral.sh/uv/getting-started/installation/).
</details>

After installing the project dependencies in step 3, the app can also check for tools and guide optional installs. It asks before running a system package-manager install. Alternatively, put trusted executables in `pc/bins/`; the app adds that directory to its own process `PATH`. It does not download unchecked binaries.

### 2. Connect and authorize your Android phone

1. Enable **Developer options** and **USB debugging** on the phone.
2. Connect the phone by USB, unlock it, and accept the debugging authorization prompt.
3. Confirm ADB sees exactly one authorized device:

```sh
adb devices
```

The PC app initially supports one authorized device at a time. Keep the phone connected and awake during file transfers.

### 3. Install the Python app and start it

```sh
git clone https://github.com/ShauryaKesarwani/Shrnk-It.git
cd Shrnk-It/pc
uv sync
uv run android-media-shrinker check
# If a required system tool is missing:
uv run android-media-shrinker setup
uv run android-media-shrinker
```

The app opens at `/sdcard`, Android's shared-storage root. If tools are missing, `check` reports that; run the `setup` command above to see install options.

## Using the PC app

| Key | Action |
| --- | --- |
| `↑` / `↓` | Move through folders and files |
| `Enter` | Open a folder or toggle file selection |
| `Space` | Select or deselect a file |
| `V` | Show four original-only video frames to identify the clip |
| `P` | Compare original and compressed quality samples; adjust and regenerate settings |
| `O` | Open the highlighted or selected file on the phone; Android may show an app chooser |
| `C` | Compress selected files |
| `S` | Edit compression settings |
| `I` | Show or hide JPEG files |
| `R` | List backups and restore an original |
| `Backspace` | Go to the parent folder |
| `Q` | Quit |

Compression progress is hidden while browsing. During a batch, the overall bar tracks files; while FFmpeg encodes a video, the stage indicator reports encoded frames against an estimated total. Each candidate is prepared first, then the app asks whether to replace that specific phone file. Canceling keeps the original untouched.

## CLI examples

Run these from `pc/`. The CLI is useful for explicit paths or scripting; compression is a dry run unless you pass `--apply`.

```sh
# Check tools and device connection
uv run android-media-shrinker check

# List a folder on the phone
uv run android-media-shrinker list --path /sdcard/DCIM/Camera

# Preview a video or JPEG (JPEG requires --include-images)
uv run android-media-shrinker preview /sdcard/DCIM/Camera/clip.mp4 --crf 27
uv run android-media-shrinker preview /sdcard/DCIM/Camera/photo.jpg --include-images --jpeg-quality 85

# Dry run: encode and report expected savings; phone remains unchanged
uv run android-media-shrinker compress /sdcard/DCIM/Camera/clip.mp4

# Apply: prepare first, then type REPLACE when prompted for that file
uv run android-media-shrinker compress /sdcard/DCIM/Camera/clip.mp4 --apply

# Find and restore an original backup
uv run android-media-shrinker backups
uv run android-media-shrinker restore <backup-id>
```

`--yes` with `--apply` skips the per-file replacement prompts; use it only when that unattended behavior is intentional. JPEG compression is opt-in and requires `--include-images` for both preview and compression.

## Safety and limitations

- The default video output is H.265/HEVC (CRF 27); audio is copied. Playback support varies by Android device and player.
- JPEG recompression is lossy. Preview samples are an estimate, not a guarantee of final playback or image quality.
- The original is backed up on the PC before replacement. Backups are stored in `android-originals/` by default (relative to the current working directory) and are not automatically deleted. Keep the backup folder safe and make separate copies for important media.
- Phone replacement is not atomic. If a transfer is interrupted, the backup remains available for recovery; inspect the phone file before retrying.
- ADB requires the phone to be connected and authorized. Android may restrict file access, and opening media depends on a compatible viewer being installed.

## Development

```sh
cd pc
uv sync --dev
uv run pytest -q
uv run python -m compileall -q src tests
uv build
```

The automated PC tests use local fixtures and mocks; they do not require a connected phone. GitHub Actions runs the PC checks on Ubuntu and Windows and installs FFmpeg for the video integration tests. Real-device behavior still needs manual verification.

## Project layout

- [`pc/`](pc/): cross-platform Python/uv TUI and CLI application.
- [`mobile-app/`](mobile-app/): Flutter Android prototype; see its [README](mobile-app/README.md) for status and limitations.
- [`docs/`](docs/): project notes and screenshots.

## License

No license has been added yet. Until one is chosen, the repository is not licensed for reuse or redistribution; please contact the maintainer before doing so.
