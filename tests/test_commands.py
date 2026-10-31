"""Behaviour of a Hands-free turn: heard text in, outcome and Windows actions out."""
from commands import Context, Dictation, Done, Failed, NoMatch, Target, handle


class FakeActions:
    def __init__(self, running=()):
        self.running = set(running)
        self.calls = []

    def switch_to(self, target):
        self.calls.append(("switch_to", target.id))
        return target.id in self.running

    def launch(self, target):
        self.calls.append(("launch", target.id))


SPOTIFY = Target("spotify", "Spotify")
CHROME = Target("chrome", "Google Chrome")
VSCODE = Target("vscode", "Visual Studio Code")


def ctx(actions=None, catalog=(SPOTIFY, CHROME, VSCODE)):
    return Context(catalog=list(catalog), actions=actions or FakeActions())


def test_open_spotify_launches_it_and_says_opening():
    actions = FakeActions()
    out = handle("Open Spotify.", ctx(actions))
    assert isinstance(out, Done)
    assert (out.card.verb, out.card.obj) == ("Opening", "Spotify")
    assert ("launch", "spotify") in actions.calls


def test_open_a_running_app_switches_to_it_instead_of_launching_again():
    actions = FakeActions(running={"chrome"})
    out = handle("open chrome", ctx(actions))
    assert (out.card.verb, out.card.obj) == ("Switching to", "Google Chrome")
    assert ("launch", "chrome") not in actions.calls


def test_short_and_misheard_names_still_find_the_app():
    assert handle("Open VS code", ctx()).card.obj == "Visual Studio Code"
    assert handle("launch spotfy", ctx()).card.obj == "Spotify"


def test_a_command_that_fits_no_app_is_a_no_match_and_does_nothing():
    actions = FakeActions()
    out = handle("Open the blender thing", ctx(actions))
    assert isinstance(out, NoMatch)
    assert (out.card.verb, out.card.obj) == ("No app called", "the blender thing")
    assert actions.calls == []


def test_long_dictation_that_starts_with_open_is_pasted():
    text = "Open the report and send it to the whole team before Friday."
    assert handle(text, ctx()) == Dictation(text)


def test_an_app_that_fails_to_launch_says_couldnt_open():
    class Broken(FakeActions):
        def launch(self, target):
            raise OSError("not installed")
    out = handle("open spotify", ctx(Broken()))
    assert isinstance(out, Failed)
    assert (out.card.verb, out.card.obj) == ("Couldn't open", "Spotify")


def test_speech_without_a_command_word_is_dictation():
    assert handle("Remind the team about Friday", ctx()) == Dictation("Remind the team about Friday")
