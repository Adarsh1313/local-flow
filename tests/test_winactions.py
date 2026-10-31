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


def test_launch_then_switch_finds_the_running_window(notepad):
    import winactions
    a = winactions.Actions()
    a.launch(notepad)
    assert wait_for(lambda: winactions.windows_of(notepad))
    assert a.switch_to(notepad) is True
