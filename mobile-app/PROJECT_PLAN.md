# Android Media Shrinker — Project Plan

## Goal

Build an Android-only Flutter app that compresses media locally with a simple Material You interface. The PC implementation and root reference scripts inform behavior; Android storage and codec APIs have different constraints.

## Agreed experience

- Browse the Android media library, search quickly, sort by size, select multiple items, and show shortcuts to common locations such as Camera, WhatsApp, and Downloads when available. Offer Android's media picker for quick selection as well.
- Support videos and opt-in lossy JPEG compression. Select shared settings, preview a short sample with representative comparison frames and an estimated final size, optionally preview individual files, override their settings or deselect them, then approve the batch once.
- Detect available H.265 encoders and decoders, explain that playback elsewhere can differ, and offer H.264 when H.265 encoding is unavailable. Settings and the minimum saving threshold are adjustable; start with 20% savings.
- Back up and verify each original in a user-selected phone folder before replacing it. Provide a backup browser and restore with overwrite confirmation. Propose cleanup for backups older than 30 days or beyond the latest three versions per original, and require approval before deletion. Never delete an active backup.
- If replacement is not safe or permitted, preserve the original and offer a separate compressed copy. Explain when a picker item is cloud-only or not writable. Continue a batch after individual failures where safe, reporting each result.
- Continue work when the app is backgrounded or the screen is locked, where Android permits, with a progress notification.

## Technical decisions still open

Use Android Media3 Transformer and device codecs first, as approved. The original FFmpegKit is retired; revisit FFmpeg only if needed. Media3 should not be assumed to match the PC's libx265 CRF behavior. Evaluate actual device capabilities and measure release sizes before making claims.

Use MediaStore for local media discovery and investigate appropriate per-item write consent and picker permissions for supported Android versions. MediaStore indexing does not itself grant write permission. Folder shortcuts depend on what Android exposes, and cloud picker items may not support in-place replacement. Refresh the media index after writes where needed; preserve metadata where feasible without promising gallery ordering.

## Delivery and verification

1. Approve the engine and Android version/permission approach; establish Flutter and Android build foundations.
2. Implement media browsing, search, selection, sorting, picker, and Material You UI.
3. Implement configurable compression and sample comparisons, including codec capability checks.
4. Implement verified backups, batch review, guarded writes, background progress, and restore.
5. Test interruption and recovery, metadata, permissions, unsupported formats, insufficient storage, cloud selections, and actual devices. Measure package size, speed, quality and savings on representative media.

Replacement may be interrupted and may not be atomic. Preserve verified backups and report recovery steps. Backups on the same phone consume space and do not protect against loss of the device. Real-device testing is essential; no compatibility or compression result is guaranteed from the PC tests.

## Current status

Flutter Android and web project files and an initial Material 3 screen exist. The Android document picker selects media, with search and sorting within the selection; this native integration has not yet been tested on a device. MediaStore browsing, dynamic wallpaper colors, codecs, backups and all processing are still pending. The web target is for UI development only. Android SDK and device validation will happen on the other desktop.

Initial pure Dart search, size sorting, and minimum-savings rules have unit tests; they are not yet connected to Android media or replacement operations.
