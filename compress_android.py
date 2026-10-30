#!/usr/bin/env python3
"""ADB Android photo/video optimizer. Dry-run by default; --apply replaces after backup."""
import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOTS = {
    'camera': ['/sdcard/DCIM', '/sdcard/Pictures', '/sdcard/Movies'],
    'whatsapp': ['/sdcard/Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Video',
                 '/sdcard/Android/media/com.whatsapp/WhatsApp/Media/WhatsApp Images'],
}
VIDEO = {'.mp4', '.mov', '.m4v'}
IMAGE = {'.jpg', '.jpeg'}

def run(cmd, check=True, capture=True):
    return subprocess.run(cmd, check=check, text=True, stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None)

def shell(cmd, check=True):
    return run(['adb', 'shell', cmd], check=check)

def stamp(path):
    r = shell("stat -c '%s|%Y' " + shlex.quote(path), check=False)
    if r.returncode != 0:
        raise RuntimeError(f'Cannot stat: {path}: {r.stderr.strip()}')
    parts = r.stdout.strip().split('|')
    if len(parts) != 2:
        raise RuntimeError(f'Unexpected stat: {r.stdout!r}')
    return int(parts[0]), int(parts[1])

def discover(group, media_type):
    roots = ROOTS['camera'] + ROOTS['whatsapp'] if group == 'all' else ROOTS[group]
    result = []
    for root in roots:
        # The output is newline delimited: ordinary camera/WhatsApp filenames do not contain newlines.
        r = shell('find ' + shlex.quote(root) + ' -type f', check=False)
        if r.returncode != 0:
            print(f'Note: cannot list {root}: {r.stderr.strip()}', file=sys.stderr)
            continue
        for path in r.stdout.splitlines():
            if '/Sent/' in path or '/.Statuses/' in path or '/Private/' in path:
                continue
            ext = Path(path).suffix.lower()
            if (ext in VIDEO and media_type in ('all', 'video')) or (ext in IMAGE and media_type in ('all', 'image')):
                result.append((path, 'video' if ext in VIDEO else 'image'))
    return sorted(set(result))

def encode(src, dst, kind, crf, jpeg_quality):
    if kind == 'video':
        command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-i', str(src),
                   '-map', '0:v:0', '-map', '0:a?', '-map_metadata', '0', '-map_chapters', '0',
                   '-c:v', 'libx265', '-preset', 'medium', '-crf', str(crf), '-pix_fmt', 'yuv420p',
                   '-tag:v', 'hvc1', '-c:a', 'copy', '-movflags', '+faststart', str(dst)]
        run(command)
        chk = run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                   '-show_entries', 'stream=codec_name', '-of', 'default=nw=1:nk=1', str(dst)])
        if chk.stdout.strip() != 'hevc':
            raise RuntimeError('Output verification failed (no HEVC video stream)')
    else:
        from PIL import Image
        with Image.open(src) as im:
            if im.format != 'JPEG':
                raise RuntimeError('Not a JPEG image')
            info = im.info
            params = {'format':'JPEG', 'quality':jpeg_quality, 'optimize':True}
            for key in ('exif', 'icc_profile', 'comment'):
                if key in info:
                    params[key] = info[key]
            im.save(dst, **params)
        with Image.open(dst) as test:
            test.verify()

def scan(path):
    command = ('content call --uri content://media --method scan_file --arg ' + shlex.quote(path))
    result = shell(command, check=False)
    if result.returncode != 0:
        print(f'  WARNING: MediaStore scan failed: {result.stderr.strip()}')
    else:
        print('  MediaStore scan requested')

def main():
    p = argparse.ArgumentParser(description='Compress camera/WhatsApp media via ADB, without losing originals.')
    p.add_argument('--category', choices=['camera','whatsapp','all'], default='all')
    p.add_argument('--type', choices=['video','image','all'], default='all')
    p.add_argument('--apply', action='store_true', help='Actually compress and replace (default: list only)')
    p.add_argument('--limit', type=int, default=0, help='Limit matching files (0 = all)')
    p.add_argument('--min-video-mb', type=float, default=20)
    p.add_argument('--min-image-mb', type=float, default=3)
    p.add_argument('--min-saving-percent', type=float, default=20)
    p.add_argument('--crf', type=int, default=27)
    p.add_argument('--jpeg-quality', type=int, default=85)
    p.add_argument('--backup-dir', default='android-originals')
    p.add_argument('--log-file', default='android-compress-results.jsonl')
    args = p.parse_args()
    if not 17 <= args.crf <= 35 or not 60 <= args.jpeg_quality <= 95:
        p.error('CRF must be 17..35; JPEG quality must be 60..95')
    if not shutil.which('adb'):
        p.error('adb is required')
    if args.apply and (not shutil.which('ffmpeg') or not shutil.which('ffprobe')):
        p.error('ffmpeg and ffprobe required for --apply')
    if args.apply and args.type != 'video':
        try:
            from PIL import Image  # noqa
        except ImportError:
            p.error('Install Pillow for JPEG compression: python -m pip install Pillow')
    devices = run(['adb','devices']).stdout.splitlines()[1:]
    if len([x for x in devices if x.strip().endswith('\tdevice')]) != 1:
        p.error('Connect and authorize exactly one Android device (adb devices)')
    entries = []
    for path, kind in discover(args.category, args.type):
        try:
            size, mtime = stamp(path)
        except Exception as exc:
            print(f'Skip: {exc}', file=sys.stderr)
            continue
        threshold = args.min_video_mb if kind == 'video' else args.min_image_mb
        if size >= threshold * 1024 * 1024:
            entries.append((path, kind, size, mtime))
    entries.sort(key=lambda x: -x[2])
    if args.limit > 0:
        entries = entries[:args.limit]
    print(f'Found {len(entries)} qualifying files; total {sum(e[2] for e in entries)/1024**3:.2f} GiB')
    for path, kind, size, _ in entries:
        print(f'  {size/1024**2:8.1f} MB [{kind}] {path}')
    if not args.apply:
        print('\nDRY RUN ONLY. Use --apply --limit 2 to test safely.')
        return
    backups = Path(args.backup_dir).expanduser().resolve()
    backups.mkdir(parents=True, exist_ok=True)
    for path, kind, old_size, original_mtime in entries:
        backup = backups / path.lstrip('/')
        if backup.exists():
            print(f'\nSKIP {path}: backup already exists (avoid processing twice)')
            continue
        print(f'\nProcessing: {path}')
        try:
            with tempfile.TemporaryDirectory(prefix='adb-compress-') as td:
                tmp = Path(td)
                src = tmp / ('source' + Path(path).suffix)
                out = tmp / ('encoded' + Path(path).suffix)
                run(['adb','pull','-a',path,str(src)], capture=False)
                if src.stat().st_size != old_size:
                    raise RuntimeError('File changed or transfer incomplete')
                encode(src, out, kind, args.crf, args.jpeg_quality)
                new_size = out.stat().st_size
                saving = (old_size-new_size)/old_size*100
                print(f'  {old_size/1024**2:.1f} -> {new_size/1024**2:.1f} MB ({saving:.1f}% saved)')
                if saving < args.min_saving_percent:
                    print('  Skip replacement: insufficient savings')
                    continue
                if stamp(path) != (old_size, original_mtime):
                    raise RuntimeError('Phone file changed during compression: not replacing')
                # Copy original to a persistent laptop backup before attempting any phone write.
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, backup)
                os.utime(out, ns=(src.stat().st_atime_ns, src.stat().st_mtime_ns))
                # ADB push -a preserves local mtime. Do not use shell mv.
                run(['adb','push','-a',str(out),path], capture=False)
                actual_size, actual_mtime = stamp(path)
                if actual_size != new_size:
                    raise RuntimeError('Pushed size mismatch; restore from backup manually!')
                if abs(actual_mtime-original_mtime) > 2:
                    print(f'  WARNING: changed filesystem mtime {original_mtime} -> {actual_mtime}')
                scan(path)
                log = {'timestamp':datetime.now().isoformat(), 'path':path, 'type':kind,
                       'old_bytes':old_size, 'new_bytes':new_size, 'saved_percent':round(saving,2),
                       'original_mtime':original_mtime, 'phone_mtime':actual_mtime,
                       'backup':str(backup)}
                with open(args.log_file,'a',encoding='utf-8') as f:
                    f.write(json.dumps(log)+'\n')
        except Exception as exc:
            print(f'  ERROR: {exc}', file=sys.stderr)
            if backup.exists():
                print(f'  Original backup is at {backup}', file=sys.stderr)

if __name__ == '__main__':
    main()
