# Todo

## PC TUI

- [ ] Add backup retention: default to 30 days; consider limiting backups to the latest 2–3 versions per original. Clarify whether the version cap supplements or replaces the age limit.
- [ ] Validate ADB browse/replace/restore on a real Android device and smoke-test the TUI on Windows; current automated tests do not require either.
- [ ] Decide whether local binary setup should download verified binaries automatically; currently it provides manual official-source instructions to avoid unverified executable downloads.
- [x] Add a video quality preview that compares several frames from the original and compressed versions before replacement.
- [x] Add a photo quality preview and controls to adjust compression parameters (including video and JPEG settings) before applying changes.

## Phone app

- [~] Document the agreed Android app workflows and evaluate the compression engine and storage permissions.
- [ ] Set up the Android-only Flutter app and Material You interface.
- [ ] Browse and search local media, show common locations, support the Android media picker, and sort by size.
- [ ] Add local video and opt-in JPEG compression, device codec checks, settings, and per-file quality previews.
- [ ] Add batch review, verified phone backups, guarded replacement, progress, and restore.
- [ ] Validate failure recovery, Android permissions, codec compatibility, and real-device behavior.
