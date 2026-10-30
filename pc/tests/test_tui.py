import asyncio
from pathlib import Path

from pc_shrinker.adb import RemoteItem
from pc_shrinker.tui import BackupScreen, DecisionScreen, MediaApp


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

    asyncio.run(exercise())


def test_compress_key_opens_confirmation_screen_without_crashing(monkeypatch, tmp_path: Path):
    import pc_shrinker.tui as tui_module

    monkeypatch.setattr(tui_module, "AdbClient", FakeAdb)
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
            assert isinstance(app.screen, DecisionScreen)

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
