"""Cross-platform Textual browser for safe Android media operations."""

from __future__ import annotations

import tempfile
from pathlib import Path, PurePosixPath

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.coordinate import Coordinate
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Static

from .adb import AdbClient, RemoteItem
from .backups import BackupStore
from .encoding import (
    EncodingSettings,
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    available_tools,
    encode,
    image_to_terminal,
    make_preview,
    make_video_quality_samples,
    make_video_thumbnail_sheet,
)
from .processor import compress_one

ANDROID_ROOT = "/sdcard"


class DecisionScreen(ModalScreen[bool]):
    def __init__(self, message: str):
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self.message)
            with Horizontal():
                yield Button("Continue", variant="error", id="yes")
                yield Button("Cancel", id="no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")


class SettingsScreen(ModalScreen[EncodingSettings | None]):
    def __init__(self, settings: EncodingSettings):
        super().__init__()
        self.settings = settings

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Compression settings (video CRF: lower = higher quality)")
            yield Label("Video CRF (17–35)")
            yield Input(str(self.settings.video_crf), id="crf", type="integer")
            yield Label("JPEG quality (60–95)")
            yield Input(str(self.settings.jpeg_quality), id="jpeg", type="integer")
            yield Label("Minimum size saving (%)")
            yield Input(str(self.settings.min_saving_percent), id="saving")
            with Horizontal():
                yield Button("Save", variant="primary", id="save")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "save":
            self.dismiss(None)
            return
        try:
            settings = EncodingSettings(
                video_crf=int(self.query_one("#crf", Input).value),
                jpeg_quality=int(self.query_one("#jpeg", Input).value),
                min_saving_percent=float(self.query_one("#saving", Input).value),
            )
            settings.validate()
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            return
        self.dismiss(settings)


class BackupScreen(ModalScreen[str | None]):
    def __init__(self, records: list[dict[str, object]]):
        super().__init__()
        self.records = records

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Backups (enter an ID to restore)")
            for record in reversed(self.records[-20:]):
                yield Label(f"{record['id']}  {record['phone_path']}  {record['created_at']}")
            yield Input(placeholder="Backup ID", id="backup-id")
            with Horizontal():
                yield Button("Restore", variant="warning", id="restore")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "restore":
            self.dismiss(self.query_one("#backup-id", Input).value.strip() or None)
        else:
            self.dismiss(None)


class QualityPreviewScreen(ModalScreen[EncodingSettings | None]):
    """Inline frame/photo comparison with controls to tune and regenerate quality."""

    CSS = """
    #quality-dialog { width: 100%; height: 100%; padding: 0 1; background: $surface; }
    #quality-heading { height: 1; color: $accent; }
    #quality-image { height: 1fr; content-align: center middle; overflow: hidden; }
    #quality-nav, #quality-settings, #quality-actions { height: 3; align: center middle; }
    #quality-settings Input { width: 12; margin: 0 1; }
    #quality-settings Label { margin-left: 1; }
    #quality-actions Button, #quality-nav Button { margin: 0 1; }
    """
    BINDINGS = [Binding("escape", "cancel", "Close")]

    def __init__(
        self,
        title: str,
        kind: str,
        source: Path,
        sample_dir: Path,
        sample_paths: list[Path],
        settings: EncodingSettings,
        temp_dir: tempfile.TemporaryDirectory[str],
    ):
        super().__init__()
        self.title_text = title
        self.kind = kind
        self.source = source
        self.sample_dir = sample_dir
        self.sample_paths = sample_paths
        self.settings = settings
        self.previewed_settings = settings
        self.temp_dir = temp_dir
        self.sample_index = 0
        self._timer = None
        self._regenerating = False

    def compose(self) -> ComposeResult:
        with Vertical(id="quality-dialog"):
            yield Static(self._heading(), id="quality-heading")
            yield Static(image_to_terminal(self.sample_paths[0]), id="quality-image")
            with Horizontal(id="quality-nav"):
                yield Button("Previous", id="previous", disabled=len(self.sample_paths) < 2)
                yield Button("Auto 0.3s", id="auto", disabled=len(self.sample_paths) < 2)
                yield Button("Next", id="next", disabled=len(self.sample_paths) < 2)
            with Horizontal(id="quality-settings"):
                yield Label("CRF")
                yield Input(str(self.settings.video_crf), id="crf", type="integer")
                yield Label("JPEG quality")
                yield Input(str(self.settings.jpeg_quality), id="jpeg", type="integer")
                yield Label("Min saving %")
                yield Input(str(self.settings.min_saving_percent), id="saving")
            with Horizontal(id="quality-actions"):
                yield Button("Update preview", variant="primary", id="regenerate")
                yield Button("Use these settings", variant="success", id="use")
                yield Button("Cancel", id="cancel")

    def _heading(self) -> str:
        point = (15, 38, 62, 85)[min(self.sample_index, 3)] if self.kind == "video" else None
        sample = f" · source point {point}%" if point else ""
        return f"{self.title_text} · original vs compressed{sample} · CRF lower = higher quality"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "cancel":
            self.action_cancel()
        elif button_id == "previous":
            self._show_sample(self.sample_index - 1)
        elif button_id == "next":
            self._show_sample(self.sample_index + 1)
        elif button_id == "auto":
            self._toggle_auto_cycle()
        elif button_id == "regenerate":
            self._start_regenerate()
        elif button_id == "use":
            self._accept_settings()

    def _show_sample(self, index: int) -> None:
        self.sample_index = index % len(self.sample_paths)
        self.query_one("#quality-heading", Static).update(self._heading())
        self.query_one("#quality-image", Static).update(image_to_terminal(self.sample_paths[self.sample_index]))

    def _toggle_auto_cycle(self) -> None:
        button = self.query_one("#auto", Button)
        if self._timer is None:
            self._timer = self.set_interval(0.3, self._advance_sample)
            button.label = "Stop auto"
        else:
            self._timer.stop()
            self._timer = None
            button.label = "Auto 0.3s"

    def _advance_sample(self) -> None:
        self._show_sample(self.sample_index + 1)

    def _read_settings(self) -> EncodingSettings | None:
        try:
            settings = EncodingSettings(
                video_crf=int(self.query_one("#crf", Input).value),
                jpeg_quality=int(self.query_one("#jpeg", Input).value),
                min_saving_percent=float(self.query_one("#saving", Input).value),
            )
            settings.validate()
            return settings
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            return None

    def _start_regenerate(self) -> None:
        settings = self._read_settings()
        if settings is None or self._regenerating:
            return
        self._regenerating = True
        self.query_one("#regenerate", Button).disabled = True
        self.query_one("#quality-heading", Static).update("Generating preview samples with the new settings…")
        self._regenerate_worker(settings)

    @work(thread=True, exclusive=True)
    def _regenerate_worker(self, settings: EncodingSettings) -> None:
        try:
            if self.kind == "video":
                samples = make_video_quality_samples(self.source, settings, self.sample_dir)
            else:
                compressed = self.sample_dir / "photo-compressed.jpg"
                comparison = self.sample_dir / "photo-comparison.jpg"
                encode(self.source, compressed, "image", settings)
                make_preview(self.source, compressed, "image", comparison)
                samples = [comparison]
            self.app.call_from_thread(self._preview_updated, samples, settings, None)
        except Exception as exc:
            self.app.call_from_thread(self._preview_updated, None, settings, str(exc))

    def _preview_updated(
        self, samples: list[Path] | None, settings: EncodingSettings, error: str | None
    ) -> None:
        self._regenerating = False
        self.query_one("#regenerate", Button).disabled = False
        if error:
            self.query_one("#quality-heading", Static).update(f"Preview failed: {error}")
            return
        self.sample_paths = samples or []
        self.settings = settings
        self.previewed_settings = settings
        self.sample_index = 0
        self._show_sample(0)

    def _accept_settings(self) -> None:
        if self._regenerating:
            self.notify("Wait for the preview update to finish", severity="warning")
            return
        settings = self._read_settings()
        if settings is None:
            return
        if settings != self.previewed_settings:
            self.notify("Update the preview before accepting changed settings", severity="warning")
            return
        self.dismiss(settings)

    def action_cancel(self) -> None:
        if self._regenerating:
            self.notify("Wait for the preview update to finish", severity="warning")
            return
        if self._timer is not None:
            self._timer.stop()
        self.dismiss(None)

    def on_unmount(self) -> None:
        if self._timer is not None:
            self._timer.stop()
        self.temp_dir.cleanup()


class ThumbnailScreen(ModalScreen[None]):
    """Original-only four-frame video sheet used for fast visual identification."""

    CSS = """
    #thumbnail-dialog { width: 100%; height: 100%; padding: 1; background: $surface; }
    #thumbnail-image { height: 1fr; content-align: center middle; overflow: hidden; }
    #thumbnail-heading { height: 1; color: $accent; }
    #thumbnail-close { height: 3; align: center middle; }
    """
    BINDINGS = [Binding("escape", "close", "Close")]

    def __init__(self, title: str, image_path: Path, temp_dir: tempfile.TemporaryDirectory[str]):
        super().__init__()
        self.title_text = title
        self.image_path = image_path
        self.temp_dir = temp_dir

    def compose(self) -> ComposeResult:
        with Vertical(id="thumbnail-dialog"):
            yield Static(f"{self.title_text} · original video samples", id="thumbnail-heading")
            yield Static(image_to_terminal(self.image_path, max_width=100, max_rows=26), id="thumbnail-image")
            with Horizontal(id="thumbnail-close"):
                yield Button("Close", variant="primary", id="close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)


class MediaApp(App[None]):
    TITLE = "Android Media Shrinker"
    CSS = """
    #path { height: 1; color: $accent; }
    #help { height: 2; }
    DataTable { height: 1fr; }
    #status { height: 2; border-top: solid $primary; }
    #dialog { width: 80%; height: auto; max-height: 90%; margin: 2 4; padding: 1 2; border: thick $accent; background: $surface; }
    #dialog Input { margin-bottom: 1; }
    #dialog Button { margin-right: 2; }
    """
    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("space", "toggle", "Select", priority=True),
        Binding("enter", "open_or_toggle", "Open/select", priority=True),
        Binding("backspace", "parent", "Parent", priority=True),
        Binding("p", "preview", "Preview", priority=True),
        Binding("v", "thumbnails", "Video thumbs", priority=True),
        Binding("c", "compress", "Compress", priority=True),
        Binding("s", "settings", "Settings", priority=True),
        Binding("r", "restore", "Backups/restore", priority=True),
        Binding("ctrl+r", "refresh", "Refresh", priority=True),
        Binding("i", "toggle_images", "Toggle JPEGs", priority=True),
    ]
    _MAIN_ACTIONS = {
        "quit", "toggle", "open_or_toggle", "parent", "preview", "thumbnails", "compress",
        "settings", "restore", "refresh", "toggle_images",
    }

    def __init__(self, start: str = "/sdcard", backup_dir: Path | None = None):
        super().__init__()
        self.adb = AdbClient()
        self.path = self.adb.validate_path(start)
        self.backups = BackupStore(backup_dir or Path("android-originals"))
        self.items: list[RemoteItem] = []
        self.selected: dict[str, RemoteItem] = {}
        self.settings = EncodingSettings()
        self.include_images = False

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        # Priority app bindings beat DataTable's built-in Space/Enter actions, but
        # should not steal keystrokes or button navigation from modal screens.
        if len(self.screen_stack) > 1 and action in self._MAIN_ACTIONS:
            return False
        return True

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self.path, id="path")
        yield Static("↑↓ navigate · Space select · Enter open/select · V identify video · P quality/settings preview · C compress · S settings · R backups · Backspace up · Q quit", id="help")
        table = DataTable(id="files", cursor_type="row", zebra_stripes=True)
        table.add_columns("Sel", "Type", "Size", "Name")
        yield table
        yield Static("Checking connected device…", id="status")
        yield Footer()

    def on_mount(self) -> None:
        try:
            device = self.adb.require_one_device()
            tools = available_tools()
            missing = [name for name in ("ffmpeg", "ffprobe") if not tools[name]]
            if missing:
                self.query_one("#status", Static).update(
                    f"Device {device}; missing {', '.join(missing)}. Install options: uv run android-media-shrinker setup"
                )
            else:
                self.query_one("#status", Static).update(f"Connected: {device} · backups: {self.backups.root}")
            self.refresh_listing()
        except Exception as exc:
            self.query_one("#status", Static).update(f"Preflight failed: {exc}")

    def refresh_listing(self) -> None:
        table = self.query_one("#files", DataTable)
        table.clear()
        self.query_one("#path", Static).update(self.path)
        try:
            self.items = self.adb.list_dir(self.path)
            for item in self.items:
                allowed = item.is_dir or item.suffix in VIDEO_EXTENSIONS or (
                    self.include_images and item.suffix in IMAGE_EXTENSIONS
                )
                if not allowed:
                    continue
                kind = "Folder" if item.is_dir else ("Video" if item.suffix in VIDEO_EXTENSIONS else "JPEG")
                selected = "[x]" if item.path in self.selected else "[ ]"
                table.add_row(selected, kind, "—" if item.is_dir else _pretty(item.size), item.name, key=item.path)
            self._status(f"{len(self.items)} entries · {len(self.selected)} selected · CRF {self.settings.video_crf} / JPEG {self.settings.jpeg_quality}")
        except Exception as exc:
            self.items = []
            self._status(f"Cannot list folder: {exc}")

    def _current(self) -> RemoteItem | None:
        table = self.query_one("#files", DataTable)
        if not table.row_count:
            return None
        key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        return next((item for item in self.items if item.path == key), None)

    def action_toggle(self) -> None:
        item = self._current()
        if item and not item.is_dir:
            if item.path in self.selected:
                del self.selected[item.path]
                marker = "[ ]"
            else:
                self.selected[item.path] = item
                marker = "[x]"
            table = self.query_one("#files", DataTable)
            table.update_cell_at(Coordinate(table.cursor_row, 0), marker)
            self._status(
                f"{len(self.selected)} selected · {sum(entry.size for entry in self.selected.values()) / 1024**2:.1f} MiB · "
                f"CRF {self.settings.video_crf} / JPEG {self.settings.jpeg_quality}"
            )

    def action_open_or_toggle(self) -> None:
        item = self._current()
        if item and item.is_dir:
            self.path = item.path
            self.refresh_listing()
        else:
            self.action_toggle()

    def action_parent(self) -> None:
        if self.path != ANDROID_ROOT:
            parent = str(PurePosixPath(self.path).parent)
            self.path = parent if parent == ANDROID_ROOT or parent.startswith(ANDROID_ROOT + "/") else ANDROID_ROOT
            self.refresh_listing()

    def action_refresh(self) -> None:
        self.refresh_listing()

    def action_toggle_images(self) -> None:
        self.include_images = not self.include_images
        self.selected = {
            path: item for path, item in self.selected.items()
            if item.suffix not in IMAGE_EXTENSIONS or self.include_images
        }
        self._status("JPEG files included" if self.include_images else "JPEG files hidden (video-only mode)")
        self.refresh_listing()

    def action_settings(self) -> None:
        self.push_screen(SettingsScreen(self.settings), callback=self._apply_settings)

    def _apply_settings(self, changed: EncodingSettings | None) -> None:
        if changed:
            self.settings = changed
            self._status(f"Settings updated · CRF {changed.video_crf} / JPEG {changed.jpeg_quality} / minimum saving {changed.min_saving_percent:g}%")

    def action_preview(self) -> None:
        item = next(iter(self.selected.values()), None) or self._current()
        if not item or item.is_dir:
            self._status("Select or highlight a supported video/JPEG first")
            return
        if item.suffix in IMAGE_EXTENSIONS and not self.include_images:
            self._status("JPEG preview is disabled")
            return
        self._status(f"Preparing quick quality preview for {item.name}…")
        self._preview_worker(item)

    def action_thumbnails(self) -> None:
        item = next(iter(self.selected.values()), None) or self._current()
        if not item or item.is_dir or item.suffix not in VIDEO_EXTENSIONS:
            self._status("Highlight or select a video first")
            return
        self._status(f"Reading video for identification thumbnails: {item.name}…")
        self._thumbnail_worker(item)

    @work(thread=True, exclusive=True)
    def _preview_worker(self, item: RemoteItem) -> None:
        temp_dir = tempfile.TemporaryDirectory(prefix="media-quality-preview-")
        try:
            kind = "video" if item.suffix in VIDEO_EXTENSIONS else "image"
            directory = Path(temp_dir.name)
            source = directory / ("original" + item.suffix)
            sample_dir = directory / "samples"
            sample_dir.mkdir()
            settings = self.settings
            self.adb.pull(item.path, str(source))
            if kind == "video":
                samples = make_video_quality_samples(source, settings, sample_dir)
            else:
                compressed = sample_dir / "photo-compressed.jpg"
                comparison = sample_dir / "photo-comparison.jpg"
                encode(source, compressed, kind, settings)
                make_preview(source, compressed, kind, comparison)
                samples = [comparison]
            screen = QualityPreviewScreen(item.name, kind, source, sample_dir, samples, settings, temp_dir)
            self.call_from_thread(self._open_quality_preview, screen)
        except Exception as exc:
            temp_dir.cleanup()
            self.call_from_thread(self._status, f"Preview failed: {exc}")

    def _open_quality_preview(self, screen: QualityPreviewScreen) -> None:
        self.push_screen(screen, callback=self._quality_preview_closed)

    def _quality_preview_closed(self, settings: EncodingSettings | None) -> None:
        if settings is not None:
            self.settings = settings
            self._status(
                f"Preview settings saved · CRF {settings.video_crf} / JPEG {settings.jpeg_quality} / "
                f"minimum saving {settings.min_saving_percent:g}%"
            )

    @work(thread=True, exclusive=True)
    def _thumbnail_worker(self, item: RemoteItem) -> None:
        temp_dir = tempfile.TemporaryDirectory(prefix="media-identification-thumbnails-")
        try:
            source = Path(temp_dir.name) / ("original" + item.suffix)
            sheet = Path(temp_dir.name) / "video-thumbnails.jpg"
            self.adb.pull(item.path, str(source))
            make_video_thumbnail_sheet(source, sheet)
            screen = ThumbnailScreen(item.name, sheet, temp_dir)
            self.call_from_thread(self._open_thumbnail_preview, screen)
        except Exception as exc:
            temp_dir.cleanup()
            self.call_from_thread(self._status, f"Thumbnail preview failed: {exc}")

    def _open_thumbnail_preview(self, screen: ThumbnailScreen) -> None:
        self.push_screen(screen, callback=lambda _: self._status("Video thumbnail preview closed"))

    def action_compress(self) -> None:
        items = list(self.selected.values())
        if not items:
            self._status("Select one or more files before compressing")
            return
        unsupported = [item.name for item in items if item.suffix not in VIDEO_EXTENSIONS | IMAGE_EXTENSIONS]
        if unsupported:
            self._status("Unsupported selection: " + ", ".join(unsupported))
            return
        self.push_screen(DecisionScreen(
            f"Compress and replace {len(items)} phone file(s)? Originals will be backed up first.\n"
            f"CRF {self.settings.video_crf}, JPEG {self.settings.jpeg_quality}, minimum saving {self.settings.min_saving_percent:g}%."
        ), callback=lambda accepted: self._confirm_compression(accepted, items, self.settings))

    def _confirm_compression(
        self, accepted: bool, items: list[RemoteItem], settings: EncodingSettings
    ) -> None:
        if accepted:
            self._compress_worker(items, settings)

    @work(thread=True, exclusive=True)
    def _compress_worker(self, items: list[RemoteItem], settings: EncodingSettings) -> None:
        for index, item in enumerate(items, start=1):
            self.call_from_thread(self._status, f"Processing {index}/{len(items)}: {item.name}")
            try:
                result = compress_one(self.adb, self.backups, item.path, settings, apply=True)
                self.call_from_thread(self._status, _result_text(result))
            except Exception as exc:
                self.call_from_thread(self._status, f"Failed {item.name}: {exc}")
        self.call_from_thread(self.refresh_listing)

    def action_restore(self) -> None:
        records = self.backups.records()
        if not records:
            self._status(f"No backups found in {self.backups.root}")
            return
        self.push_screen(BackupScreen(records), callback=self._backup_selected)

    def _backup_selected(self, backup_id: str | None) -> None:
        if not backup_id:
            return
        try:
            record = self.backups.get(backup_id)
        except KeyError as exc:
            self._status(str(exc))
            return
        exists = self.adb.exists(str(record["phone_path"]))
        overwrite = False
        if exists:
            self.push_screen(DecisionScreen(
                f"{record['phone_path']} already exists on the phone. Overwrite it with backup {backup_id}?"
            ), callback=lambda confirmed: self._confirm_restore(confirmed, backup_id))
            return
        self._restore_worker(backup_id, overwrite)

    def _confirm_restore(self, confirmed: bool, backup_id: str) -> None:
        if confirmed:
            self._restore_worker(backup_id, overwrite=True)
        else:
            self._status("Restore cancelled")

    @work(thread=True, exclusive=True)
    def _restore_worker(self, backup_id: str, overwrite: bool) -> None:
        try:
            self.backups.restore(backup_id, self.adb, overwrite=overwrite)
            self.call_from_thread(self._status, f"Restored backup {backup_id} and refreshed MediaStore")
        except Exception as exc:
            self.call_from_thread(self._status, f"Restore failed: {exc}")

    def _status(self, message: str) -> None:
        self.query_one("#status", Static).update(message)


def _pretty(size: int) -> str:
    if size >= 1024**3:
        return f"{size / 1024**3:.2f} GiB"
    if size >= 1024**2:
        return f"{size / 1024**2:.1f} MiB"
    return f"{size / 1024:.0f} KiB"


def _result_text(result: dict[str, object]) -> str:
    if result.get("replaced"):
        return f"Replaced {result['path']}; saved {result['saving_percent']}% · backup {result['backup_id']}"
    return f"Skipped {result['path']}: {result.get('reason', 'not replaced')}"
