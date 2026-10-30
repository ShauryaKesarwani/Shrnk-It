"""Encoding and visual-preview helpers backed by FFmpeg and Pillow."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

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


def encode(source: Path, destination: Path, kind: str, settings: EncodingSettings) -> None:
    settings.validate()
    if kind == "video":
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            raise EncodingError("FFmpeg and ffprobe are required for video compression")
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(source),
            "-map", "0:v:0", "-map", "0:a?", "-map_metadata", "0", "-map_chapters", "0",
            "-c:v", "libx265", "-preset", "medium", "-crf", str(settings.video_crf),
            "-pix_fmt", "yuv420p", "-tag:v", "hvc1", "-c:a", "copy", "-movflags", "+faststart",
            str(destination),
        ]
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        if result.returncode:
            raise EncodingError(result.stderr.strip() or "FFmpeg encoding failed")
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
    """Encode only three representative still frames, not the entire video."""
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise EncodingError("FFmpeg and ffprobe are required for video previews")
    duration = _video_duration(source)
    originals: list[Image.Image] = []
    compressed: list[Image.Image] = []
    with tempfile.TemporaryDirectory(prefix="video-quality-preview-") as td:
        directory = Path(td)
        for index, fraction in enumerate((0.2, 0.5, 0.8)):
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
                originals.append(image.convert("RGB"))
            with Image.open(decoded_frame) as image:
                compressed.append(image.convert("RGB"))
        _write_contact_sheet(originals, compressed, destination)
    for image in originals + compressed:
        image.close()
    return destination


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


def _write_contact_sheet(originals: list[Image.Image], encodeds: list[Image.Image], destination: Path) -> None:
    width, height = 480, 300
    rows = max(len(originals), len(encodeds))
    sheet = Image.new("RGB", (width * 2, (height + 32) * rows), "#202124")
    from PIL import ImageDraw

    draw = ImageDraw.Draw(sheet)
    for index, (original, encoded) in enumerate(zip(originals, encodeds)):
        y = index * (height + 32)
        draw.text((8, y + 6), f"Original — sample {index + 1}", fill="white")
        draw.text((width + 8, y + 6), f"Compressed — sample {index + 1}", fill="white")
        for image, x in ((original, 0), (encoded, width)):
            image.thumbnail((width - 16, height - 16))
            sheet.paste(image, (x + (width - image.width) // 2, y + 32))
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, format="JPEG", quality=92)
    sheet.close()
