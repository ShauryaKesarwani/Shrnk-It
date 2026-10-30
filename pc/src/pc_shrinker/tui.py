"""Cross-platform Textual browser for safe Android media operations."""

from __future__ import annotations

import tempfile
import webbrowser
from pathlib import Path, PurePosixPath

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Static

from .adb import AdbClient, RemoteItem
from .backups import BackupStore
from .encoding import EncodingSettings, VIDEO_EXTENSIONS, IMAGE_EXTENSIONS, available_tools, encode, make_preview
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
        Binding("q", "quit", "Quit"), Binding("space", "toggle", "Select"),
        Binding("enter", "open_or_toggle", "Open/select"), Binding("backspace", "parent", "Parent"),
        Binding("p", "preview", "Preview"), Binding("c", "compress", "Compress"),
        Binding("s", "settings", "Settings"), Binding("r", "restore", "Backups/restore"),
        Binding("ctrl+r", "refresh", "Refresh"),
        Binding("i", "toggle_images", "Toggle JPEGs"),
    ]

    def __init__(self, start: str = "/sdcard/DCIM/Camera", backup_dir: Path | None = None):
        super().__init__()
        self.adb = AdbClient()
        self.path = self.adb.validate_path(start)
        self.backups = BackupStore(backup_dir or Path("android-originals"))
        self.items: list[RemoteItem] = []
        self.selected: dict[str, RemoteItem] = {}
        self.settings = EncodingSettings()
        self.include_images = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self.path, id="path")
        yield Static("↑↓ navigate · Space select · Enter open/select · P preview · C compress · S settings · R backups · Backspace up · Q quit", id="help")
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
            else:
                self.selected[item.path] = item
            self.refresh_listing()

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

    async def action_settings(self) -> None:
        changed = await self.push_screen_wait(SettingsScreen(self.settings))
        if changed:
            self.settings = changed
            self._status(f"Settings updated · CRF {changed.video_crf} / JPEG {changed.jpeg_quality} / minimum saving {changed.min_saving_percent:g}%")

    async def action_preview(self) -> None:
        item = next(iter(self.selected.values()), None) or self._current()
        if not item or item.is_dir:
            self._status("Select or highlight a supported video/JPEG first")
            return
        if item.suffix in IMAGE_EXTENSIONS and not self.include_images:
            self._status("JPEG preview is disabled")
            return
        self._preview_worker(item)

    @work(thread=True, exclusive=True)
    def _preview_worker(self, item: RemoteItem) -> None:
        try:
            kind = "video" if item.suffix in VIDEO_EXTENSIONS else "image"
            with tempfile.TemporaryDirectory(prefix="media-preview-") as td:
                directory = Path(td)
                source = directory / ("original" + item.suffix)
                compressed = directory / ("compressed" + item.suffix)
                preview = directory / "quality-comparison.jpg"
                self.adb.pull(item.path, str(source))
                encode(source, compressed, kind, self.settings)
                make_preview(source, compressed, kind, preview)
                # The comparison file must survive the temporary-directory cleanup.
                persistent = self.backups.root / "previews" / f"{Path(item.name).stem}-comparison.jpg"
                persistent.parent.mkdir(parents=True, exist_ok=True)
                preview.replace(persistent)
                webbrowser.open(persistent.resolve().as_uri())
            self.call_from_thread(self._status, f"Quality comparison opened: {persistent}")
        except Exception as exc:
            self.call_from_thread(self._status, f"Preview failed: {exc}")

    async def action_compress(self) -> None:
        items = list(self.selected.values())
        if not items:
            self._status("Select one or more files before compressing")
            return
        unsupported = [item.name for item in items if item.suffix not in VIDEO_EXTENSIONS | IMAGE_EXTENSIONS]
        if unsupported:
            self._status("Unsupported selection: " + ", ".join(unsupported))
            return
        accepted = await self.push_screen_wait(DecisionScreen(
            f"Compress and replace {len(items)} phone file(s)? Originals will be backed up first.\n"
            f"CRF {self.settings.video_crf}, JPEG {self.settings.jpeg_quality}, minimum saving {self.settings.min_saving_percent:g}%."
        ))
        if accepted:
            self._compress_worker(items, self.settings)

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

    async def action_restore(self) -> None:
        records = self.backups.records()
        if not records:
            self._status(f"No backups found in {self.backups.root}")
            return
        backup_id = await self.push_screen_wait(BackupScreen(records))
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
            overwrite = await self.push_screen_wait(DecisionScreen(
                f"{record['phone_path']} already exists on the phone. Overwrite it with backup {backup_id}?"
            ))
            if not overwrite:
                self._status("Restore cancelled")
                return
        self._restore_worker(backup_id, overwrite)

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
