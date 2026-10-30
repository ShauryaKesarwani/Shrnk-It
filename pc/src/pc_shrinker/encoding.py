"""Encoding and visual-preview helpers backed by FFmpeg and Pillow."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageOps


VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg"}


@dataclass(frozen=True)
class EncodingSettings:
    video_crf: int = 27
    jpeg_quality: int = 85
    min_saving_percent: float = 20.0

    def validate(self) -> None:
        if not 17 <= self.video_crf <= 35:
            raise ValueError("Video CRF must be between 17 and 35")
        if not 60 <= self.jpeg_quality <= 95:
            raise ValueError("JPEG quality must be between 60 and 95")
        if not 0 <= self.min_saving_percent <= 95:
            raise ValueError("Minimum saving must be between 0 and 95 percent")


class EncodingError(RuntimeError):
    pass


def available_tools() -> dict[str, str | None]:
    return {name: shutil.which(name) for name in ("adb", "ffmpeg", "ffprobe")}


def persist_preview(source: Path, destination: Path) -> Path:
    """Copy preview artifacts across filesystems (e.g. system /tmp to a home directory)."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def encode(
    source: Path,
    destination: Path,
    kind: str,
    settings: EncodingSettings,
    *,
    on_progress: Callable[[int, int | None], None] | None = None,
) -> None:
    settings.validate()
    if kind == "video":
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            raise EncodingError("FFmpeg and ffprobe are required for video compression")
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-progress", "pipe:1",
            "-stats_period", "0.25", "-i", str(source),
            "-map", "0:v:0", "-map", "0:a?", "-map_metadata", "0", "-map_chapters", "0",
            "-c:v", "libx265", "-preset", "medium", "-crf", str(settings.video_crf),
            "-pix_fmt", "yuv420p", "-tag:v", "hvc1", "-c:a", "copy", "-movflags", "+faststart",
            str(destination),
        ]
        if on_progress is None:
            result = subprocess.run(command, text=True, capture_output=True, check=False)
            if result.returncode:
                raise EncodingError(result.stderr.strip() or "FFmpeg encoding failed")
        else:
            total_frames = _estimated_video_frames(source)
            process = subprocess.Popen(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            assert process.stdout is not None
            last_frame = 0
            for line in process.stdout:
                key, separator, value = line.strip().partition("=")
                if separator and key == "frame":
                    try:
                        last_frame = int(value)
                        on_progress(last_frame, total_frames)
                    except ValueError:
                        continue
            stderr = process.stderr.read() if process.stderr else ""
            return_code = process.wait()
            if return_code:
                raise EncodingError(stderr.strip() or "FFmpeg encoding failed")
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=codec_name", "-of", "default=nw=1:nk=1", str(destination)],
            text=True, capture_output=True, check=False,
        )
        if probe.returncode or probe.stdout.strip() != "hevc":
            raise EncodingError("Output verification failed: expected HEVC video")
        return

    if kind != "image":
        raise ValueError(f"Unsupported media kind: {kind}")
    with Image.open(source) as image:
        if image.format != "JPEG":
            raise EncodingError("Only JPEG images are supported")
        options: dict[str, object] = {"format": "JPEG", "quality": settings.jpeg_quality, "optimize": True}
        for field in ("exif", "icc_profile", "comment"):
            if field in image.info:
                options[field] = image.info[field]
        image.save(destination, **options)
    with Image.open(destination) as result:
        result.verify()


def make_preview(source: Path, compressed: Path, kind: str, destination: Path) -> Path:
    """Build a side-by-side contact sheet and open it in the system image viewer."""
    if kind == "image":
        with Image.open(source) as original, Image.open(compressed) as encoded:
            originals = [ImageOps.exif_transpose(original).convert("RGB")]
            encodeds = [ImageOps.exif_transpose(encoded).convert("RGB")]
    else:
        if not shutil.which("ffmpeg"):
            raise EncodingError("FFmpeg is required to make video previews")
        originals, encodeds = [], []
        with tempfile.TemporaryDirectory(prefix="media-preview-") as td:
            duration = _video_duration(source)
            for label, clip in (("original", source), ("compressed", compressed)):
                for index, fraction in enumerate((0.2, 0.5, 0.8)):
                    output = Path(td) / f"{label}-{index}.jpg"
                    result = subprocess.run(
                        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(duration * fraction),
                         "-i", str(clip), "-frames:v", "1", "-y", str(output)],
                        text=True, capture_output=True, check=False,
                    )
                    if result.returncode or not output.exists():
                        raise EncodingError(result.stderr.strip() or "Could not extract preview frame")
                    (originals if label == "original" else encodeds).append(Image.open(output).convert("RGB"))
            _write_contact_sheet(originals, encodeds, destination)
            for image in originals + encodeds:
                image.close()
            return destination
    _write_contact_sheet(originals, encodeds, destination)
    return destination


def make_video_quality_preview(source: Path, settings: EncodingSettings, destination: Path) -> Path:
    """Save a contact sheet of four frame-level original/compressed comparisons."""
    with tempfile.TemporaryDirectory(prefix="video-quality-sheet-") as td:
        samples = make_video_quality_samples(source, settings, Path(td))
        sheets = []
        for path in samples:
            with Image.open(path) as image:
                sheets.append(image.convert("RGB"))
        width = max(image.width for image in sheets)
        height = sum(image.height for image in sheets)
        combined = Image.new("RGB", (width, height), "#202124")
        y = 0
        for image in sheets:
            combined.paste(image, (0, y))
            y += image.height
            image.close()
        destination.parent.mkdir(parents=True, exist_ok=True)
        combined.save(destination, format="JPEG", quality=92)
        combined.close()
    return destination


def make_video_quality_samples(source: Path, settings: EncodingSettings, destination_dir: Path) -> list[Path]:
    """Encode four still-frame comparisons for the interactive quality-preview screen."""
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise EncodingError("FFmpeg and ffprobe are required for video previews")
    settings.validate()
    duration = _video_duration(source)
    destination_dir.mkdir(parents=True, exist_ok=True)
    samples: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="video-quality-preview-") as td:
        directory = Path(td)
        for index, fraction in enumerate((0.15, 0.38, 0.62, 0.85)):
            timestamp = max(0.0, min(duration * fraction, duration - 0.05))
            original_frame = directory / f"original-{index}.jpg"
            encoded_frame = directory / f"encoded-{index}.mp4"
            decoded_frame = directory / f"compressed-{index}.jpg"
            _run_preview_ffmpeg([
                "-ss", f"{timestamp:.3f}", "-i", str(source), "-frames:v", "1",
                "-q:v", "2", "-y", str(original_frame),
            ])
            _run_preview_ffmpeg([
                "-ss", f"{timestamp:.3f}", "-i", str(source), "-frames:v", "1", "-an",
                "-c:v", "libx265", "-preset", "ultrafast", "-crf", str(settings.video_crf),
                "-pix_fmt", "yuv420p", "-tag:v", "hvc1", "-y", str(encoded_frame),
            ])
            _run_preview_ffmpeg([
                "-i", str(encoded_frame), "-frames:v", "1", "-q:v", "2", "-y", str(decoded_frame),
            ])
            with Image.open(original_frame) as image:
                original = image.convert("RGB")
            with Image.open(decoded_frame) as image:
                encoded = image.convert("RGB")
            sample = destination_dir / f"quality-{index + 1}.jpg"
            _write_contact_sheet([original], [encoded], sample, [f"{fraction:.0%}"])
            original.close()
            encoded.close()
            samples.append(sample)
    return samples


def make_video_thumbnail_sheet(source: Path, destination: Path) -> Path:
    """Extract four uncompressed source frames into a quick identification sheet."""
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise EncodingError("FFmpeg and ffprobe are required for video thumbnails")
    duration = _video_duration(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    frames: list[Image.Image] = []
    with tempfile.TemporaryDirectory(prefix="video-thumbnails-") as td:
        directory = Path(td)
        for index, fraction in enumerate((0.15, 0.38, 0.62, 0.85)):
            timestamp = max(0.0, min(duration * fraction, duration - 0.05))
            frame_path = directory / f"frame-{index}.jpg"
            _run_preview_ffmpeg([
                "-ss", f"{timestamp:.3f}", "-i", str(source), "-frames:v", "1",
                "-q:v", "3", "-y", str(frame_path),
            ])
            with Image.open(frame_path) as image:
                frames.append(image.convert("RGB"))
        _write_thumbnail_grid(frames, destination)
    for frame in frames:
        frame.close()
    return destination


def image_to_terminal(path: Path, *, max_width: int = 120, max_rows: int = 22):
    """Render an image as ANSI true-color half blocks for a Textual Static widget."""
    from rich.style import Style
    from rich.text import Text

    with Image.open(path) as source:
        image = source.convert("RGB")
        image.thumbnail((max_width, max_rows * 2), Image.Resampling.LANCZOS)
        if image.height % 2:
            padded = Image.new("RGB", (image.width, image.height + 1), "#202124")
            padded.paste(image, (0, 0))
            image.close()
            image = padded
        pixels = image.load()
        output = Text()
        for y in range(0, image.height, 2):
            for x in range(image.width):
                top = pixels[x, y]
                bottom = pixels[x, y + 1]
                fg = "#%02x%02x%02x" % top
                bg = "#%02x%02x%02x" % bottom
                output.append("▀", style=Style(color=fg, bgcolor=bg))
            if y + 2 < image.height:
                output.append("\n")
        image.close()
        return output


def _run_preview_ffmpeg(arguments: list[str]) -> None:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", *arguments],
        text=True, capture_output=True, check=False,
    )
    if result.returncode:
        raise EncodingError(result.stderr.strip() or "Could not generate video quality preview")


def _video_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        text=True, capture_output=True, check=False,
    )
    try:
        duration = float(result.stdout.strip())
    except ValueError as exc:
        raise EncodingError("Could not determine video duration for quality preview") from exc
    if result.returncode or duration <= 0:
        raise EncodingError("Could not determine video duration for quality preview")
    return duration


def _estimated_video_frames(path: Path) -> int | None:
    """Estimate video frame count from duration and average frame rate."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=avg_frame_rate", "-show_entries", "format=duration", "-of", "default=nw=1", str(path)],
        text=True, capture_output=True, check=False,
    )
    values = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    try:
        numerator, denominator = values["avg_frame_rate"].split("/", 1)
        fps = float(numerator) / float(denominator)
        total = round(float(values["duration"]) * fps)
        return total if total > 0 else None
    except (KeyError, ValueError, ZeroDivisionError):
        return None


def _write_contact_sheet(
    originals: list[Image.Image],
    encodeds: list[Image.Image],
    destination: Path,
    sample_labels: list[str] | None = None,
) -> None:
    width, height = 480, 300
    rows = max(len(originals), len(encodeds))
    sheet = Image.new("RGB", (width * 2, (height + 32) * rows), "#202124")
    from PIL import ImageDraw

    draw = ImageDraw.Draw(sheet)
    for index, (original, encoded) in enumerate(zip(originals, encodeds)):
        y = index * (height + 32)
        label = f"at {sample_labels[index]}" if sample_labels else ""
        draw.text((8, y + 6), f"Original {label}", fill="white")
        draw.text((width + 8, y + 6), f"Compressed {label}", fill="white")
        for image, x in ((original, 0), (encoded, width)):
            image.thumbnail((width - 16, height - 16))
            sheet.paste(image, (x + (width - image.width) // 2, y + 32))
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, format="JPEG", quality=92)
    sheet.close()


def _write_thumbnail_grid(frames: list[Image.Image], destination: Path) -> None:
    from PIL import ImageDraw

    tile_width, tile_height, label_height = 480, 240, 30
    sheet = Image.new("RGB", (tile_width * 2, (tile_height + label_height) * 2), "#202124")
    draw = ImageDraw.Draw(sheet)
    for index, frame in enumerate(frames):
        x = (index % 2) * tile_width
        y = (index // 2) * (tile_height + label_height)
        draw.text((x + 8, y + 7), f"Original video at {(0.15, 0.38, 0.62, 0.85)[index]:.0%}", fill="white")
        sample = frame.copy()
        sample.thumbnail((tile_width - 16, tile_height - 8))
        sheet.paste(sample, (x + (tile_width - sample.width) // 2, y + label_height))
        sample.close()
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, format="JPEG", quality=88)
    sheet.close()
