# Android media compression via Linux + ADB

## What worked in the WhatsApp test (29 Oct 2026)

- An MP4 was re-encoded from H.264 to HEVC/H.265 with `ffmpeg -c:v libx265 -crf 27 -tag:v hvc1` and worked in WhatsApp.
- On replacing WhatsApp originals, files initially vanished from Google Photos and Files' videos view even though WhatsApp could play them.
- Android MediaStore showed `is_pending=1`, `date_modified=NULL`. **Explicit `scan_file` fixed it**, setting `is_pending=0`, and videos appeared again.
- Space savings on one 12-second sample: 1,555,534 bytes down to 744,098 bytes (52.2%).
- Protect spaces in ADB shell path using **outer double quotes and inner single quotes**, e.g.:

```bash
adb shell "content call --uri content://media --method scan_file --arg '/sdcard/Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Video/VID-20261027-WA0031.mp4'"
```

- Check MediaStore:

```bash
adb shell content query --uri content://media/external/video/media \
  --projection '_id:_display_name:is_pending:is_trashed:date_modified:date_added:datetaken:duration:_size' \
  | grep 'VID-20261027-WA0031'
```

Android stores distinct time fields: filesystem modification time, MediaStore `date_modified`, `date_added`, and capture metadata (`datetaken` or EXIF/MP4 creation). **Preserving mtime alone does not guarantee Google Photos will group media under its old capture date.** Files replaced or rescanned can obtain new MediaStore IDs and `date_added` values. The script keeps originals and logs results; it does not edit WhatsApp's database or force creation dates.

## Prerequisites

Arch Linux:

```bash
sudo pacman -S android-tools ffmpeg python python-pillow
adb devices
```

Enable USB debugging on your phone and authorize the laptop. Python 3.10+ recommended. Do not use root. Keep significant free space on the laptop for originals, and sufficient phone space to perform writes. Android device must be connected and unlocked as needed.

## Commands (from the folder containing compress_android.py)

Scan all camera/WhatsApp videos and JPEG images; **does not change anything**:

```bash
python compress_android.py
```

Scan camera videos only:

```bash
python compress_android.py --category camera --type video
```

Test up to two qualifying WhatsApp videos, preserving laptop backups:

```bash
python compress_android.py --category whatsapp --type video --apply --limit 2
```

Test up to two JPEG photos:

```bash
python compress_android.py --category camera --type image --min-image-mb 2 --apply --limit 2
```

Process videos at least 100 MB from camera folders, but only after testing:

```bash
python compress_android.py --category camera --type video --min-video-mb 100 --apply
```

The script backs up the **original phone file** to `android-originals/sdcard/...` on your laptop before replacing it. It never deletes backups automatically. When a backup for a phone path already exists, the script skips that path to prevent double compression. Processed outcomes are in `android-compress-results.jsonl`.

Defaults: video x265 CRF 27, preserves original pixel dimensions, original audio stream, and metadata tags where possible; JPEG quality 85 with retained EXIF/ICC when possible; keeps the smaller output only when >=20% saved. Camera video in HEVC may not work in every older app/device; review samples before batch processing. **Do not recompress irreplaceable images without inspecting quality**. PNG, HEIC, DNG, GIF, and other formats are intentionally skipped. WhatsApp Sent and Statuses folders are skipped.

After each replacement, script requests MediaStore `scan_file`. Verify Gallery/Files and timestamps on samples. For recording/capture dates, check Google Photos' Info panel; if it's still sorting under today, do not batch until you decide whether preserving that chronology is essential.

**Safety:** ADB writes do not make an atomic transaction; unexpected interruption or low space can leave a partial file. Originals on laptop are the recovery source. An unreadable/partial output can be restored with `adb push -a 'android-originals/sdcard/...' '/sdcard/...'` then `scan_file`. There is no guarantee WhatsApp's app-private metadata will remain stable. Videos that are already HEVC might be recompressed again; the tool skips paths with an existing backup but does not proactively inspect codecs or perceptual quality. Use the scan/dry-run before applying.

## Faster TUI (video-only by default)

The previous TUI queried `adb shell stat` once **per entry**, which could be very slow for folders with hundreds of camera files. The updated `media_tui.py` runs **one ADB shell request per folder**, using `find ... -exec stat ... +` on the phone (with a one-request fallback). It displays folders plus MP4/MOV/M4V videos and sorts files largest first. `--include-images` optionally shows JPEG photos, too.

```bash
# Fast video browser starts directly at /sdcard/DCIM/Camera:
python media_tui.py

# Open WhatsApp's videos directly:
python media_tui.py --path '/sdcard/Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Video'

# Choose one or more exact phone paths without browsing, then review and confirm:
python media_tui.py --files '/sdcard/DCIM/Camera/VID_001.mp4' '/sdcard/DCIM/Camera/VID_002.mp4'

# Show JPEG photos too (slower than video-only on very large folders):
python media_tui.py --include-images
```

Arrow keys navigate, Space toggles selection, `S` cycles compression strength, Enter enters a directory or reviews selected files; Backspace goes up; Q quits. On the review screen, processing only starts after typing `REPLACE`. Backups go to `android-originals/` on the laptop; after replacement, `scan_file` refreshes MediaStore to clear pending entries on the tested phone.

**Limits:** Video-only filtering happens on the Android side of the listing results after one bulk retrieval; Android may still stat all direct entries. There is no encoding on browsing. Very large directories may still take a little time to enumerate. Google Photos ordering may depend on `date_added` or capture metadata even with modification times restored. Test a couple of files before large batches and ensure enough phone space for the replacement operation.
