import asyncio
import tempfile
from pathlib import Path

from PIL import Image

from pc_shrinker.adb import RemoteItem
from pc_shrinker.encoding import EncodingSettings
from pc_shrinker.tui import BackupScreen, DecisionScreen, MediaApp, QualityPreviewScreen


class FakeAdb:
    def __init__(self):
        self.listed_paths = []

    def validate_path(self, path):
        return path

    def require_one_device(self):
        return "test-device"

    def list_dir(self, path):
        self.listed_paths.append(path)
        if path == "/sdcard":
            return [RemoteItem("/sdcard/DCIM", True, 0, 0)]
        return [RemoteItem(path + "/sample.mp4", False, 1234, 0)]


def test_tui_starts_at_shared_storage_root_and_space_marks_selection(monkeypatch, tmp_path: Path):
    import pc_shrinker.tui as tui_module

    monkeypatch.setattr(tui_module, "AdbClient", FakeAdb)
    app = MediaApp(backup_dir=tmp_path)

    async def exercise():
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.path == "/sdcard"
            table = app.query_one("#files", tui_module.DataTable)
            await pilot.press("enter")  # Enter the DCIM folder.
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            table = app.query_one("#files", tui_module.DataTable)
            assert table.get_row_at(0)[0] == "[x]"
            assert len(app.selected) == 1
            assert table.cursor_row == 0

    asyncio.run(exercise())


def test_compress_key_starts_preparation_before_confirmation(monkeypatch, tmp_path: Path):
    import pc_shrinker.tui as tui_module

    monkeypatch.setattr(tui_module, "AdbClient", FakeAdb)
    prepared = []
    monkeypatch.setattr(tui_module.MediaApp, "_prepare_next", lambda self: prepared.append(self._batch_items[0].path))
    app = MediaApp(start="/sdcard", backup_dir=tmp_path)

    async def exercise():
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("space")
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()
            assert not isinstance(app.screen, DecisionScreen)
            assert prepared == ["/sdcard/DCIM/sample.mp4"]

    asyncio.run(exercise())


def test_preview_key_dispatches_for_highlighted_video(monkeypatch, tmp_path: Path):
    import pc_shrinker.tui as tui_module

    monkeypatch.setattr(tui_module, "AdbClient", FakeAdb)
    calls = []
    monkeypatch.setattr(tui_module.MediaApp, "_preview_worker", lambda self, item: calls.append(item.path))
    app = MediaApp(start="/sdcard", backup_dir=tmp_path)

    async def exercise():
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()
            assert calls == ["/sdcard/DCIM/sample.mp4"]

    asyncio.run(exercise())


def test_priority_hotkeys_do_not_steal_modal_text_input(monkeypatch, tmp_path: Path):
    import pc_shrinker.tui as tui_module

    monkeypatch.setattr(tui_module, "AdbClient", FakeAdb)
    app = MediaApp(start="/sdcard", backup_dir=tmp_path)

    async def exercise():
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(BackupScreen([]))
            await pilot.pause()
            field = app.screen.query_one("#backup-id", tui_module.Input)
            field.focus()
            await pilot.press("p")
            assert field.value == "p"

    asyncio.run(exercise())


def test_video_thumbnail_hotkey_dispatches_for_highlighted_file(monkeypatch, tmp_path: Path):
    import pc_shrinker.tui as tui_module

    monkeypatch.setattr(tui_module, "AdbClient", FakeAdb)
    calls = []
    monkeypatch.setattr(tui_module.MediaApp, "_thumbnail_worker", lambda self, item: calls.append(item.path))
    app = MediaApp(start="/sdcard", backup_dir=tmp_path)

    async def exercise():
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("v")
            await pilot.pause()
            assert calls == ["/sdcard/DCIM/sample.mp4"]

    asyncio.run(exercise())


def test_quality_preview_can_regenerate_and_accept_settings_in_place(monkeypatch, tmp_path: Path):
    import pc_shrinker.tui as tui_module

    monkeypatch.setattr(tui_module, "AdbClient", FakeAdb)
    samples = []
    for index in range(4):
        sample = tmp_path / f"sample-{index}.jpg"
        Image.new("RGB", (32, 24), (40 + index * 20, 90, 140)).save(sample)
        samples.append(sample)
    temp_dir = tempfile.TemporaryDirectory(prefix="quality-screen-test-")
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    screen = QualityPreviewScreen(
        "sample.mp4", "video", samples[0], sample_dir, samples,
        EncodingSettings(), temp_dir,
    )
    monkeypatch.setattr(
        tui_module.QualityPreviewScreen,
        "_regenerate_worker",
        lambda self, settings: self._preview_updated(self.sample_paths, settings, None),
    )
    app = MediaApp(start="/sdcard", backup_dir=tmp_path / "backups")

    async def exercise():
        async with app.run_test() as pilot:
            await pilot.pause()
            app.push_screen(screen, callback=app._quality_preview_closed)
            await pilot.pause()
            await pilot.click("#auto")
            await pilot.pause(delay=0.35)
            assert screen.sample_index != 0
            await pilot.click("#auto")
            screen.query_one("#crf", tui_module.Input).value = "30"
            await pilot.click("#regenerate")
            await pilot.pause()
            assert screen.previewed_settings.video_crf == 30
            await pilot.click("#use")
            await pilot.pause()
            assert app.settings.video_crf == 30

    asyncio.run(exercise())


def test_preview_key_opens_inline_quality_screen(monkeypatch, tmp_path: Path):
    import pc_shrinker.tui as tui_module

    class PreviewAdb(FakeAdb):
        def pull(self, remote, local):
            Path(local).write_bytes(b"local preview fixture")

    monkeypatch.setattr(tui_module, "AdbClient", PreviewAdb)

    def fake_samples(source, settings, destination):
        destination.mkdir(parents=True, exist_ok=True)
        samples = []
        for index in range(4):
            sample = destination / f"quality-{index}.jpg"
            Image.new("RGB", (24, 16), (index * 40, 80, 140)).save(sample)
            samples.append(sample)
        return samples

    monkeypatch.setattr(tui_module, "make_video_quality_samples", fake_samples)
    app = MediaApp(start="/sdcard", backup_dir=tmp_path / "backups")

    async def exercise():
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("p")
            for _ in range(30):
                await pilot.pause(delay=0.05)
                if isinstance(app.screen, QualityPreviewScreen):
                    break
            assert isinstance(app.screen, QualityPreviewScreen)
            assert len(app.screen.sample_paths) == 4
            await pilot.press("escape")

    asyncio.run(exercise())


def test_video_thumbnail_key_opens_inline_original_sheet(monkeypatch, tmp_path: Path):
    import pc_shrinker.tui as tui_module

    from pc_shrinker.tui import ThumbnailScreen

    class PreviewAdb(FakeAdb):
        def pull(self, remote, local):
            Path(local).write_bytes(b"local video fixture")

    monkeypatch.setattr(tui_module, "AdbClient", PreviewAdb)

    def fake_sheet(source, destination):
        Image.new("RGB", (48, 32), (100, 140, 190)).save(destination)
        return destination

    monkeypatch.setattr(tui_module, "make_video_thumbnail_sheet", fake_sheet)
    app = MediaApp(start="/sdcard", backup_dir=tmp_path / "backups")

    async def exercise():
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("v")
            for _ in range(30):
                await pilot.pause(delay=0.05)
                if isinstance(app.screen, ThumbnailScreen):
                    break
            assert isinstance(app.screen, ThumbnailScreen)
            await pilot.press("escape")

    asyncio.run(exercise())


def test_progress_indicators_are_hidden_until_batch_processing(monkeypatch, tmp_path: Path):
    import pc_shrinker.tui as tui_module

    monkeypatch.setattr(tui_module, "AdbClient", FakeAdb)
    app = MediaApp(start="/sdcard", backup_dir=tmp_path)

    async def exercise():
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.query_one("#batch-progress", tui_module.ProgressBar).styles.display == "none"
            assert app.query_one("#stage-progress", tui_module.ProgressBar).styles.display == "none"
            app._batch_items = [RemoteItem("/sdcard/a.mp4", False, 1, 0)] * 5
            app._batch_index = 2
            app._set_progress_visible(True)
            messages = []
            app._status = messages.append
            app._encoding_progress(120, 500)
            assert "3/5" in messages[-1]
            assert "120/500 frames" in messages[-1]

    asyncio.run(exercise())
