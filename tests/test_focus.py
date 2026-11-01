"""Hold-to-talk runs a Command only when there's clearly nowhere to type."""
from winactions import classify_focus


def test_text_fields_and_editors_are_typeable():
    assert classify_focus("EditControl") is True
    assert classify_focus("DocumentControl", editable=True) is True
    assert classify_focus("PaneControl", caret=True) is True   # a classic app showing a text caret


def test_links_buttons_lists_and_read_only_pages_are_not():
    for kind in ("HyperlinkControl", "ButtonControl", "ListItemControl", "WindowControl"):
        assert classify_focus(kind) is False
    assert classify_focus("DocumentControl", editable=False) is False   # a web page, Spotify


def test_unclear_focus_stays_dictation():
    assert classify_focus("PaneControl") is None
    assert classify_focus("DocumentControl") is None
