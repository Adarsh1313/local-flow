"""Floating windows drawn with real per-pixel transparency (needs a desktop: -m windows)."""
import pytest

pytestmark = pytest.mark.windows


@pytest.fixture(scope="module")
def ui():
    import tkinter as tk
    import localflow
    root = tk.Tk()
    root.withdraw()
    localflow.init_fonts(root)
    yield localflow
    root.destroy()


def test_pill_has_clear_corners_and_smooth_edges(ui):
    ops = [("image", ui._shape(200, 40, 20, ui.T["surface"], ui.T["popup_border"], 1, ""), 10, 10, "nw", 0),
           ("text", 110, 30, "Listening", ui.T["text"], ui.F["body"], "center")]
    im = ui.render_ops(ops, 220, 60)
    alpha = im.getchannel("A")
    for corner in ((0, 0), (219, 0), (0, 59), (219, 59), (10, 10), (209, 49)):   # window and pill corners
        assert alpha.getpixel(corner) == 0, corner
    assert alpha.getpixel((110, 30)) == 255                                  # inside is solid
    soft = sum(n for a, n in enumerate(alpha.histogram()) if 0 < a < 255)
    assert soft > 20                                                         # antialiased, not jagged


def test_layer_shows_and_moves_without_redrawing(ui):
    layer = ui.Layer(ui.tk._default_root)
    layer.config(width=120, height=40)
    layer.create_image(0, 0, image=ui.shape(120, 40, 20, ui.T["surface"]))
    layer.present(100, 100)
    first = layer.shown
    layer.present(100, 110)               # moved: same picture
    assert layer.shown[:3] == first[:3] and layer.shown[4] == 110
    layer.park()
    layer.win.destroy()
