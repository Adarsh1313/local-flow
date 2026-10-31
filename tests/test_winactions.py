"""Real Windows desktop checks, opt-in: pytest -m windows. Uses Notepad only."""
import time

import pytest

pytestmark = pytest.mark.windows


def wait_for(cond, secs=10):
    end = time.time() + secs
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.25)
    return False


@pytest.fixture(scope="module")
def notepad():
    import winactions
    target = next(t for t in winactions.load_catalog() if t.name == "Notepad")
    yield target
    for hwnd, *_ in winactions.windows_of(target):
        winactions.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE


def test_catalog_lists_store_and_desktop_apps():
    import winactions
    names = {t.name for t in winactions.load_catalog()}
    assert {"Notepad", "File Explorer"} <= names


def test_real_icons_for_an_app_and_a_folder(notepad, tmp_path):
    import winactions
    for source in (notepad, tmp_path):
        im = winactions.icon_image(source, 32)
        assert im.size == (32, 32)
        assert im.getchannel("A").getextrema()[1] > 200  # something opaque was drawn


def test_open_place_opens_a_folder_in_explorer(tmp_path):
    import winactions
    from commands import Target
    folder = tmp_path / "LocalFlowPlaceTest"
    folder.mkdir()
    explorer = Target("Microsoft.Windows.Explorer", "File Explorer")
    winactions.Actions().open_place(Target("folder:test", folder.name, "folder", str(folder)))
    assert wait_for(lambda: any(w[3].startswith(folder.name) for w in winactions.windows_of(explorer)))
    for hwnd, _, _, title in winactions.windows_of(explorer):
        if title.startswith(folder.name):
            winactions.user32.PostMessageW(hwnd, 0x0010, 0, 0)


def test_volume_reads_and_sets_and_is_put_back():
    import winactions
    a = winactions.Actions()
    before = a.volume()
    try:
        a.set_volume(before - 1 if before else 1)
        assert a.volume() == (before - 1 if before else 1)
        assert a.change_volume(+1) == (before if before else 2)
    finally:
        a.set_volume(before)
    assert a.volume() == before


def test_launch_then_switch_finds_the_running_window(notepad):
    import winactions
    a = winactions.Actions()
    a.launch(notepad)
    assert wait_for(lambda: winactions.windows_of(notepad))
    assert a.switch_to(notepad) is True


def test_running_apps_minimise_and_close(notepad):
    import winactions
    a = winactions.Actions()
    if not winactions.windows_of(notepad):
        a.launch(notepad)
        assert wait_for(lambda: winactions.windows_of(notepad))
    assert notepad in dict(a.running_apps([notepad]))
    a.minimise(notepad)
    hwnd = winactions.windows_of(notepad)[0][0]
    assert wait_for(lambda: winactions.user32.IsIconic(hwnd))
    a.close(notepad)
    assert wait_for(lambda: not winactions.windows_of(notepad))
