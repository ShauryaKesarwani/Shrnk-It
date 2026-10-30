# PC Android Media Shrinker — Project Plan

## Goal

Build a safe, cross-platform desktop terminal tool for browsing Android media over ADB, previewing compression quality, replacing files only after confirmation, and restoring originals from PC backups. The initial PC targets are Windows and Linux; macOS support should be kept practical where the same design works.

The existing `pc/` directory is a uv project (`pyproject.toml`, `uv.lock`) with a Python 3.13 starter module and no runtime dependencies yet. The root `compress_android.py`, `media_tui.py`, and `TESTS_INFO_CONCLUSION.md` are reference implementations and test notes, not the target architecture.

## Confirmed product decisions

- Use **Textual** for a keyboard-friendly, cross-platform TUI. Keep a CLI entry point for common/non-interactive operations where useful.
- Check whether `adb`, `ffmpeg`, and `ffprobe` are already available before asking about installation.
- If a required binary is missing, ask the user whether to install globally with a detected package manager or locally under removable `pc/bins/`. Never install without consent. Prefer official sources and verify downloads where upstream checksums/signatures are available; otherwise give manual installation guidance rather than silently trusting an unverified binary.
- Support video compression and **opt-in JPEG** compression. Other image formats are out of initial scope.
- Keep original backups on the PC. Restore must require explicit confirmation before overwriting an existing phone file.
- Require a dry-run/review and explicit confirmation before replacing phone files; never delete backups as part of normal processing.

## User workflows

1. **Preflight:** show detected OS/architecture, required tools and versions, ADB device state, and available local backup space. Support exactly one authorized device initially.
2. **Browse and select:** navigate Android directories, filter supported video/JPEG files, show file sizes, and select items for processing.
3. **Configure and preview:** let the user adjust encoding settings, generate a temporary compressed sample, and compare several representative original/compressed video frames or an original/compressed photo. Preview must not modify the phone file. Allow parameter changes and regeneration before approval.
4. **Review and replace:** show the selected files, settings, expected output, and backup destination. Before transfer, confirm the source has not changed; persist and verify the original backup before pushing the replacement. Verify the result and request an Android MediaStore scan.
5. **Restore:** list available backups with original phone path and date, let the user select one, check the destination, ask before overwriting, push and verify the restored file, then request a MediaStore scan.

## Safety and compatibility requirements

- Preserve originals before any phone write. Use a manifest recording original path, backup path, timestamps, sizes, media type, settings, and processing outcome so backups can be listed and restored reliably.
- Avoid treating a backup's mere existence as proof a file was processed; distinguish backup identity from each compression run.
- Detect transfer and encode failures, verify local output and uploaded size, retain backups after partial failures, and clearly report when manual recovery may be needed. ADB replacement is not atomic.
- Use argument arrays for local subprocesses and carefully quote commands passed through Android's shell. Handle paths with spaces on Windows and Android.
- Preserve audio, dimensions, and metadata where possible. Request `scan_file` after replacement/restoration, but do not promise that Google Photos capture-date grouping will remain unchanged: MediaStore dates/IDs can change independently of filesystem mtime.
- Default video behavior should match the tested reference where appropriate (HEVC/H.265 via `libx265`, CRF 27, `hvc1`, audio copied, faststart); JPEG quality 85. Keep output only if it meets a configurable minimum saving threshold (reference default: 20%). Expose these as adjustable settings and clearly warn that HEVC compatibility varies and JPEG is lossy.
- Preview and validation must work without a connected phone when given local sample files, enabling automated tests.

## Proposed code organization

Keep the Python package small and modular rather than growing one large script:

- `src/pc_shrinker/cli.py` — entry point, command-line arguments, startup flow.
- `src/pc_shrinker/tui/` — Textual screens/widgets for browsing, preview, settings, backup listing, and confirmation.
- `src/pc_shrinker/adb.py` — device checks and Android listing/stat/pull/push/scan operations.
- `src/pc_shrinker/encoding.py` — FFmpeg/Pillow detection, compression, and output validation.
- `src/pc_shrinker/backups.py` — backup manifest, retention, listing, and restore operations.
- `src/pc_shrinker/previews.py` — local frame/photo preview generation.
- `tests/` — unit tests with mocked subprocesses plus platform-independent media/manifest tests.

Use uv to manage Python and project dependencies. Keep required dependencies minimal: Textual for the TUI and Pillow only for JPEG processing/preview if its functionality cannot be covered adequately by the chosen existing options. FFmpeg/ADB remain external tools, not Python packages.

## Backup retention decision (not finalized)

The requested policy is either a default age limit of **30 days** or keeping only the latest **2–3 versions** per original. Recommended first release: retain backups for 30 days by default, show the policy clearly, and never remove a backup while a restore/operation is active. Confirm before implementation whether the 2–3-version limit is an additional cap or an alternative policy. Provide a way to disable automatic cleanup; do not silently delete backups.

## Delivery sequence

1. **Foundation:** define package/CLI shape, uv dependencies, settings and manifest formats; add cross-platform tool/device detection. No phone writes yet.
2. **Read-only browsing:** implement ADB device checks, folder listing, filtering, and selection; exercise Linux and Windows path handling.
3. **Local encode and preview:** implement configurable video/JPEG encoding, validation, representative frame/photo comparisons, and parameter adjustment using local fixtures.
4. **Backup, replace, restore:** add durable backup manifests, preflight/review confirmations, guarded ADB transfers, verification, MediaStore scan, and restore flow.
5. **Hardening:** test failures, paths with spaces, missing tools, multiple/no devices, interrupted transfers, and backup-retention behavior; document manual Android/Windows/Linux checks.

## Acceptance criteria

- Runs from the uv project on supported Windows and Linux environments; reports missing tools with an explicit install choice and never installs without consent.
- Browsing and previewing are read-only. Phone replacement requires a final explicit confirmation and a verified PC original backup.
- Video and opt-in JPEG settings can be adjusted and previewed before use; previews visibly compare original and compressed quality.
- A user can identify and restore a selected backup, with overwrite confirmation and transfer verification.
- Automated tests cover core selection, settings validation, backup manifest/retention, output checks, and failure handling without requiring a live phone. Manual tests verify ADB and MediaStore behavior on a real Android device.
- Documentation states that Android writes are non-atomic and capture-date ordering may change.

## Known risks and open points

- ADB push may be interrupted and leave an incomplete destination; preserve the original backup and make recovery instructions explicit.
- H.265 playback support differs across devices/apps; quality previews cannot guarantee compatibility or perceptual quality.
- Package-manager availability differs by Linux distribution. Only offer known managers (for example, winget, apt, dnf, pacman, and Homebrew); otherwise provide manual setup instructions.
- Local binary installation needs secure source and integrity verification and must be removable without affecting the rest of the system.
- Backup retention details (30-day default versus a 2–3-version cap) need confirmation before automatic cleanup is implemented.

## Implementation status

The initial PC app is implemented in `src/pc_shrinker/`: Textual browsing/selection from shared storage root `/sdcard`, CLI commands, settings, JPEG/video compression, side-by-side preview images, backup manifests with SHA-256 verification, guarded replace/restore, and a setup assistant. Video previews encode only three representative still frames, not the entire clip. Modal actions use callbacks so Textual hotkeys do not crash; app hotkeys take priority over DataTable defaults while remaining inactive inside dialogs. `uv run pytest` exercises local/core behavior without a device. External tools are checked and existing PATH installations are reused. Global installation is opt-in; the local `bins/` option currently provides secure manual installation guidance rather than downloading executable binaries. Automatic backup cleanup is intentionally not implemented until the retention policy is settled. `.github/workflows/pc-ci.yml` runs the locked install, tests, and CLI check on Ubuntu and Windows; real-device behavior still requires a connected phone and manual verification.
