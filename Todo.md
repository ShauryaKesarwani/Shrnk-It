# Todo

## PC TUI

- [ ] Add backup retention: default to 30 days; consider limiting backups to the latest 2–3 versions per original. Clarify whether the version cap supplements or replaces the age limit.
- [ ] Validate ADB browse/replace/restore on a real Android device and smoke-test the TUI on Windows; current automated tests do not require either.
- [ ] Decide whether local binary setup should download verified binaries automatically; currently it provides manual official-source instructions to avoid unverified executable downloads.
- [x] Add a video quality preview that compares several frames from the original and compressed versions before replacement.
- [x] Add a photo quality preview and controls to adjust compression parameters (including video and JPEG settings) before applying changes.
- [x] Show compression progress and ask for replacement confirmation after encoding, immediately before backup/replacement.
- [x] Keep progress indicators hidden while browsing, show batch totals and FFmpeg frame progress, improve inline thumbnail sizing, and add an `O` shortcut to open selected media on the connected phone.

## Phone app

- [x] Document agreed workflows and generate Android and web Flutter targets.
- [~] Build Material 3 interface; Android 12+ wallpaper accent seeds its palette. Validate on-device and consider full system tonal palette.
- [~] Select files with Android's photo picker (document picker fallback); search and sort selected files. Validate on a device.
- [~] Browse and search the local MediaStore library, request appropriate permissions, and show media folders. Validate partial-access and common locations on a device.
- [~] Detect H.265 encoder and decoder support; expose H.264 fallback during compression and validate detection on a device.
- [~] Implement local Media3 video compression and opt-in JPEG compression with configurable settings and savings threshold. Initial video and JPEG separate-copy paths need Android validation, broader metadata handling and support for larger photos; Media3 may transmux instead of compressing.
- [~] Generate representative quality comparisons, estimate size, and allow per-file settings and deselection before batch approval. Video and JPEG sample comparisons are connected but need full compression integration and real-device validation.
- [~] Choose a backup folder, verify backups, track versions, review cleanup, and restore originals with confirmation. Initial backup copying and restore-as-copy verify SHA-256; in-place restore, cleanup and Android testing remain outstanding.
- [~] Implement guarded in-place replacement, separate-copy fallback, MediaStore refresh, batch progress, and safe failure recovery. A tested batch coordinator exists but has no platform operations connected.
- [ ] Continue supported operations in the background with a notification.
- [ ] Add meaningful automated coverage for the above and validate permissions, interruption, codecs, backups, replacement, and restore on real Android devices.
- [ ] Measure Android release size and compression performance on the other desktop.
