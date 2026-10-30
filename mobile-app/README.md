# Shrnk It mobile

Android-first Flutter prototype for local media. The web target is for UI development only; Android selection, previews, encoding and backup operations are not available in a browser.

## Run

On this laptop, run `flutter pub get` and `flutter run -d chrome` for the web interface. On a machine with Flutter and the Android SDK configured, run `flutter doctor`, `flutter pub get`, then `flutter run -d <device-id>` with an authorized Android phone. `flutter devices` lists available targets. To build a debug APK, run `flutter build apk --debug`. The project currently uses Flutter's example application ID and debug signing; do not publish it as-is.

Run `flutter analyze` and `flutter test` for Dart and widget checks. Android Gradle compilation and real-device behavior have not been verified yet. Start device testing with copies of disposable media. The current interface explicitly saves separate files; original replacement is not implemented.

## Current prototype

The Android bridge contains a MediaStore browser and photo picker, codec capability detection, video/JPEG quality samples, separate-copy export, user-selected backup folder, backup SHA-256 verification, a backup list and restore-as-copy. Backup and restore paths verify the bytes by reading them back; storage providers may not support every operation. The backup metadata index is stored privately by the app, with JSON sidecars in the chosen folder. Sidecar import after reinstall is not implemented.

JPEG encoding supports photos up to 16 megapixels and copies orientation and basic date/camera metadata; other metadata can be lost. Video uses Android Media3; devices can ignore the target bitrate, and Media3 may copy an already matching stream without recompression. Both copy paths require a configurable minimum saving and never replace the original. Background processing, reliable quality estimation, batch compression, in-place replacement, in-place restore and full wallpaper-derived color schemes are still pending. See [PROJECT_PLAN.md](PROJECT_PLAN.md) and the root [Todo.md](../Todo.md).
