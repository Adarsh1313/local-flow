"""Hearing the wake word."""
import numpy as np
import pytest

from wake import SpeechWake, wake_score

SR, FRAME = 16000, 800


def frames(seconds, level):
    rng = np.random.default_rng(0)
    n = int(seconds * SR / FRAME)
    return [(rng.standard_normal(FRAME) * level).astype(np.float32) for _ in range(n)]


def burst():
    return frames(1.0, 0.002) + frames(0.8, 0.08) + frames(0.8, 0.002)


def test_wake_score_accepts_close_hearings_and_rejects_others():
    for heard in ("Hey Jarvis.", "He Jarvis.", "Hay Jarvis.", "Um, hey Jarvis"):
        assert wake_score(heard, "Hey Jarvis") >= 0.85, heard
    for heard in ("She was nervous.", "Hello there, how are you?", "Hey, it's the harvest."):
        assert wake_score(heard, "Hey Jarvis") < 0.85, heard


def test_speech_wake_wakes_on_the_phrase_after_a_burst_of_speech():
    heard = []
    det = SpeechWake("Hey Jarvis", lambda audio: heard.append(len(audio)) or "Hey Jarvis.")
    assert any(det.feed(f) for f in burst())
    assert len(heard) == 1


def test_speech_wake_ignores_other_speech_and_remembers_what_it_heard():
    det = SpeechWake("Hey Jarvis", lambda audio: "Hello there.")
    assert not any(det.feed(f) for f in burst())
    assert det.last_heard == "Hello there."


def test_speech_wake_skips_long_speech_without_transcribing():
    calls = []
    det = SpeechWake("Hey Jarvis", lambda audio: calls.append(1) or "Hey Jarvis.")
    long_talk = frames(1.0, 0.002) + frames(8.0, 0.08) + frames(0.8, 0.002)
    assert not any(det.feed(f) for f in long_talk)
    assert calls == []


def _speak(text, path):
    import subprocess
    ps = ("Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
          "$f=New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000,"
          "[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,[System.Speech.AudioFormat.AudioChannel]::Mono);"
          f"$s.SetOutputToWaveFile('{path}',$f); $s.Speak('{text}'); $s.Dispose()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    import wave
    with wave.open(str(path)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768


def _woke(detector, audio):
    x = np.concatenate([np.zeros(SR // 2, np.float32), audio, np.zeros(SR, np.float32)])
    return any(detector.feed(x[i:i + FRAME]) for i in range(0, len(x) - FRAME, FRAME))


@pytest.mark.windows
def test_model_hears_hey_jarvis_quietly_and_ignores_other_speech(tmp_path):
    from wake import ModelWake
    jarvis = _speak("Hey Jarvis", tmp_path / "jarvis.wav")
    other = _speak("Hello there, it is the harvest season", tmp_path / "other.wav")
    for gain in (1.0, 0.1):   # normal and very soft
        assert _woke(ModelWake("Hey Jarvis"), jarvis * gain), gain
        assert not _woke(ModelWake("Hey Jarvis"), other * gain), gain
