#!/usr/bin/env python3
"""Terminal file picker for compress_android.py. Browses Android through ADB."""
import argparse
import curses
import os
import shlex
import shutil
import sys
from pathlib import Path
from dataclasses import dataclass

from compress_android import run, shell, stamp, encode, scan
import tempfile
import json
from datetime import datetime

ROOT = '/sdcard'
PRESETS = [
    ('High quality', 23, 92),
    ('Balanced', 27, 85),
    ('Smaller files', 30, 78),
    ('Strong', 33, 70),
]
VIDEO = {'.mp4', '.mov', '.m4v'}
IMAGE = {'.jpg', '.jpeg'}

@dataclass
class Item:
    path: str
    folder: bool
    size: int = 0
    mtime: int = 0
    kind: str = ''


def list_dir(path, video_only=True):
    """One ADB round-trip per folder, not one per file.

    Android's toybox find/stat run locally on the phone. A fallback handles
    devices where find does not implement batched -exec ... +.
    """
    quoted = shlex.quote(path)
    fmt = shlex.quote('%F|%s|%Y|%n')
    command = f'find {quoted} -mindepth 1 -maxdepth 1 -exec stat -c {fmt} {{}} +'
    result = shell(command, check=False)
    if result.returncode:
        # Fallback: still one ADB round-trip, despite local stat loop.
        command = (f'find {quoted} -mindepth 1 -maxdepth 1 | '
                   f'while IFS= read -r p; do stat -c {fmt} "$p"; done')
        result = shell(command, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'Cannot list folder')
    items = []
    for line in result.stdout.splitlines():
        try:
            ftype, size, mtime, p = line.split('|', 3)
            if not p or p.startswith(('/sdcard/Android/data/', '/sdcard/Android/obb/')):
                continue
            is_dir = 'directory' in ftype
            ext = Path(p).suffix.lower()
            kind = 'video' if ext in VIDEO else 'image' if ext in IMAGE else ''
            if is_dir or kind == 'video' or (not video_only and kind == 'image'):
                items.append(Item(p, is_dir, int(size), int(mtime), kind))
        except (ValueError, IndexError):
            continue
    return sorted(items, key=lambda x: (not x.folder, -x.size if not x.folder else 0, x.path.lower()))


def pretty(n):
    return f'{n/1024**3:.2f}G' if n >= 1024**3 else f'{n/1024**2:.1f}M' if n >= 1024**2 else f'{n/1024:.0f}K'


def draw(stdscr, path, items, cursor, offset, selected, preset, msg):
    h, w = stdscr.getmaxyx()
    stdscr.erase()
    def write(y, s, attr=0):
        if 0 <= y < h:
            try: stdscr.addnstr(y, 0, s, max(0,w-1), attr)
            except curses.error: pass
    write(0, 'Android Media Compressor | Folder browser', curses.A_BOLD)
    write(1, 'Path: ' + path)
    write(2, '↑↓ navigate  SPACE select  ENTER folder/continue  BACKSPACE up  S strength  Q quit')
    write(3, f'Selected: {len(selected)} files ({pretty(sum(x.size for x in selected.values()))})  | Strength: {PRESETS[preset][0]}  |  Folders first, files largest first')
    visible = max(1, h-7)
    for row, item in enumerate(items[offset:offset+visible], 4):
        active = (offset+row-4 == cursor)
        mark = '[x]' if item.path in selected else '[ ]'
        name = Path(item.path).name
        if item.folder:
            s = f'    <DIR>        {name}/'
        else:
            s = f'{mark} {pretty(item.size):>9}  {name}'
        write(row, s, curses.A_REVERSE if active else 0)
    write(h-3, 'Folders: Enter opens. Files: Space toggles. Enter with selections begins review.')
    write(h-2, msg)
    write(h-1, f'{cursor+1 if items else 0}/{len(items)} items')
    stdscr.refresh()


def picker(stdscr, start, video_only=True):
    curses.curs_set(0)
    path, cursor, offset, preset = start, 0, 0, 1
    selected = {}
    message = 'Video-only fast listing.' if video_only else 'Video + JPEG listing.'
    while True:
        try: items = list_dir(path, video_only=video_only)
        except Exception as ex:
            items = []
            message = f'Cannot open: {ex}'
        while True:
            visible = max(1, stdscr.getmaxyx()[0]-7)
            offset = min(offset, max(0, cursor-visible+1))
            if cursor < offset: offset = cursor
            draw(stdscr, path, items, cursor, offset, selected, preset, message)
            key = stdscr.getch()
            if key in (ord('q'), ord('Q')): return None
            if key == curses.KEY_UP: cursor = max(0, cursor-1)
            elif key == curses.KEY_DOWN: cursor = min(len(items)-1, cursor+1) if items else 0
            elif key == curses.KEY_NPAGE: cursor = min(len(items)-1,cursor+visible) if items else 0
            elif key == curses.KEY_PPAGE: cursor = max(0,cursor-visible)
            elif key in (ord('s'), ord('S')):
                preset = (preset+1) % len(PRESETS)
                message = f'Strength: {PRESETS[preset][0]} (H.265 CRF {PRESETS[preset][1]}, JPEG quality {PRESETS[preset][2]})'
            elif key == ord(' '):
                if items and not items[cursor].folder:
                    item = items[cursor]
                    if item.path in selected: del selected[item.path]
                    else: selected[item.path] = item
                    message = 'Selection updated.'
            elif key in (curses.KEY_BACKSPACE, 127, 8, ord('h')):
                if path != ROOT:
                    parent = str(Path(path).parent)
                    path = parent if parent.startswith(ROOT) else ROOT
                    cursor, offset = 0,0
                    break
            elif key in (10, 13, curses.KEY_ENTER):
                if items and items[cursor].folder:
                    path = items[cursor].path
                    cursor, offset = 0,0
                    break
                if selected:
                    return list(selected.values()), preset
                message = 'Select files with SPACE first.'


def process(items, preset, backup_dir, minimum):
    crf, jpgq = PRESETS[preset][1:]
    backup_root = Path(backup_dir).expanduser().resolve()
    backup_root.mkdir(parents=True, exist_ok=True)
    for index, item in enumerate(items, 1):
        print(f'\n[{index}/{len(items)}] {item.path} ({pretty(item.size)})', flush=True)
        backup = backup_root / item.path.lstrip('/')
        if backup.exists():
            print('SKIP: backup already exists; possible prior processing')
            continue
        try:
            current_size, current_mtime = stamp(item.path)
            if (current_size, current_mtime) != (item.size,item.mtime):
                raise RuntimeError('Phone file changed since selection')
            with tempfile.TemporaryDirectory(prefix='media-tui-') as td:
                ext = Path(item.path).suffix
                src, dst = Path(td)/('original'+ext), Path(td)/('compressed'+ext)
                run(['adb','pull','-a',item.path,str(src)], capture=False)
                if src.stat().st_size != item.size:
                    raise RuntimeError('Pulled file size mismatch')
                encode(src, dst, item.kind, crf, jpgq)
                new_size = dst.stat().st_size
                pct = 100 * (1-new_size/item.size)
                print(f'  Result: {pretty(item.size)} -> {pretty(new_size)}, saved {pct:.1f}%')
                if pct < minimum:
                    print(f'  SKIP: below {minimum}% minimum saving')
                    continue
                if stamp(item.path) != (item.size,item.mtime):
                    raise RuntimeError('Phone file changed during compression')
                backup.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(src, backup)
                os.utime(dst, ns=(src.stat().st_atime_ns,src.stat().st_mtime_ns))
                run(['adb','push','-a',str(dst),item.path],capture=False)
                got_size,got_mtime = stamp(item.path)
                if got_size != new_size:
                    raise RuntimeError('Push size mismatch, original retained in backup!')
                scan(item.path)
                if abs(got_mtime-item.mtime)>2:
                    print('  WARNING: original modification timestamp not preserved')
                with open('media-tui-results.jsonl','a',encoding='utf-8') as out:
                    out.write(json.dumps({'path':item.path,'backup':str(backup),'original_bytes':item.size,
                             'new_bytes':new_size,'original_mtime':item.mtime,'new_mtime':got_mtime,
                             'preset':PRESETS[preset][0],'time':datetime.now().isoformat()})+'\n')
        except Exception as ex:
            print(f'  ERROR: {ex}')
            if backup.exists(): print(f'  Backup: {backup}')


def main():
    parser = argparse.ArgumentParser(description='Select Android media interactively using arrows and space')
    parser.add_argument('--path', default='/sdcard/DCIM/Camera', help='Start directly in this Android folder (default: /sdcard/DCIM/Camera)')
    parser.add_argument('--include-images', action='store_true', help='Also show JPEG files (videos only by default)')
    parser.add_argument('--files', nargs='+', metavar='ANDROID_PATH', help='Skip folder browsing; directly select specific Android video paths')
    parser.add_argument('--backup-dir', default='android-originals')
    parser.add_argument('--min-saving-percent', type=float, default=20)
    args = parser.parse_args()
    if not sys.stdin.isatty(): parser.error('Run in a real terminal')
    for binary in ('adb','ffmpeg','ffprobe'):
        if not shutil.which(binary): parser.error(f'Missing dependency: {binary}')
    if args.include_images:
        try:
            from PIL import Image  # noqa
        except ImportError:
            parser.error('Missing Pillow: install python-pillow or pip install Pillow')
    devices = run(['adb','devices']).stdout.splitlines()[1:]
    if len([line for line in devices if line.strip().endswith('\tdevice')]) != 1:
        parser.error('Connect exactly one authorized Android device')
    start = args.path.rstrip('/') or ROOT
    if not (start==ROOT or start.startswith(ROOT+'/')):
        parser.error('--path must start with /sdcard/')
    if args.files:
        direct = []
        for raw in args.files:
            p = raw.rstrip('/')
            if not p.startswith(ROOT + '/') or Path(p).suffix.lower() not in VIDEO:
                parser.error(f'--files expects full Android video paths: {p}')
            size, mtime = stamp(p)
            direct.append(Item(p, False, size, mtime, 'video'))
        choice = (direct, 1)
    else:
        choice = curses.wrapper(picker, start, not args.include_images)
    if choice is None:
        print('Cancelled. No changes made.')
        return
    items,preset = choice
    print(f'\nSelected {len(items)} files, total {pretty(sum(x.size for x in items))}')
    print(f'Compression: {PRESETS[preset][0]} (H.265 CRF {PRESETS[preset][1]}, JPEG quality {PRESETS[preset][2]})')
    print('Originals kept in:',Path(args.backup_dir).resolve())
    print('Replacement occurs only if file is at least',args.min_saving_percent,'% smaller.')
    print('NOTE: MediaStore re-scan corrects pending entries, but Google Photos sorting date may change.')
    if input('Type REPLACE to proceed (anything else cancels): ').strip() != 'REPLACE':
        print('Cancelled. No changes made.')
        return
    process(items,preset,args.backup_dir,args.min_saving_percent)
    print('\nFinished. Check files in WhatsApp/Gallery. Originals remain on laptop.')

if __name__=='__main__': main()
