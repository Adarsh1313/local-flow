"""Training recordings: each Dictation's audio kept with its final text."""
import numpy as np

from clips import Clips


def test_a_clip_and_its_final_text_land_together(tmp_path):
    clips = Clips(tmp_path / "training")
    name = clips.save(np.zeros(16000, np.float32), "I asked cloud.")
    clips.update_text(name, "I asked Claude.")
    assert clips.pairs() == {name: "I asked Claude."}
    assert (tmp_path / "training" / name).exists()


def test_size_is_reported_and_delete_all_empties_it(tmp_path):
    clips = Clips(tmp_path / "training")
    assert clips.size() == 0
    clips.save(np.zeros(16000, np.float32), "hello")
    assert clips.size() > 30000   # one second of 16-bit audio
    clips.delete_all()
    assert clips.size() == 0 and clips.pairs() == {}
