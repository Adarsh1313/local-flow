"""Behaviour of a Hands-free turn: heard text in, outcome and Windows actions out."""
from datetime import datetime

from commands import (Alias, Context, Dictation, Done, Failed, NeedsConfirmation, NoMatch, Routine, RoutineStep,
                      Target, answer,
                      append_command, confirm, handle, is_complete_command, read_command_usage, suggested_aliases,
                      suggested_routines, top_apps)


class FakeActions:
    def __init__(self, running=()):
        self.running = set(running)
        self.calls = []

    def switch_to(self, target):
        self.calls.append(("switch_to", target.id))
        return target.id in self.running

    def launch(self, target):
        self.calls.append(("launch", target.id))

    player = "Spotify"   # what the Windows media pop-up is showing
    volume = 50

    def media(self, action, target=None):
        self.calls.append(("media", action, target and target.id))
        return target.name if target else self.player

    def set_volume(self, level):
        self.calls.append(("set_volume", level))
        self.volume = level

    def change_volume(self, step):
        self.volume = max(0, min(100, self.volume + step))
        self.calls.append(("set_volume", self.volume))
        return self.volume

    def mute(self, on):
        self.calls.append(("mute", on))

    def open_place(self, target):
        self.calls.append(("open_place", target.path))

    def open_url(self, url):
        self.calls.append(("open_url", url))

    windows = {}   # target id -> open window titles

    def running_apps(self, catalog):
        return [(t, self.windows[t.id]) for t in catalog if t.id in self.windows]

    def close(self, target):
        self.calls.append(("close", target.id))

    def minimise(self, target):
        self.calls.append(("minimise", target.id))

    def minimise_all(self):
        self.calls.append(("minimise_all",))


SPOTIFY = Target("spotify", "Spotify")
CHROME = Target("chrome", "Google Chrome")
VSCODE = Target("vscode", "Visual Studio Code")


DOWNLOADS = Target("folder:downloads", "Downloads", "folder", r"C:\Users\me\Downloads")
DDRIVE = Target("drive:d", "D drive", "folder", "D:\\")
BLUETOOTH = Target("settings:bluetooth", "Bluetooth settings", "settings", "ms-settings:bluetooth")
YOUTUBE = Target("site:youtube", "YouTube", "website", "https://www.youtube.com")
LINKEDIN = Target("site:linkedin", "LinkedIn", "website", "https://www.linkedin.com/feed/")
PLACES = (DOWNLOADS, DDRIVE, BLUETOOTH, YOUTUBE, LINKEDIN)


def ctx(actions=None, catalog=(SPOTIFY, CHROME, VSCODE) + PLACES):
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


def test_clawed_and_cloud_open_claude():
    claude = Target("claude", "Claude")
    assert handle("open clawed", ctx(catalog=(claude,))).card.obj == "Claude"
    assert handle("open cloud", ctx(catalog=(claude,))).card.obj == "Claude"


def test_polite_command_phrases_are_understood_without_changing_dictation():
    assert handle("Can you open Spotify?", ctx()).card.obj == "Spotify"
    assert handle("Could you please launch Chrome for me?", ctx()).card.obj == "Google Chrome"
    assert handle("Please pause, thanks.", ctx()).card.verb == "Paused"
    assert handle("Can you remind the team about Friday?", ctx()) == Dictation("Can you remind the team about Friday?")


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


def test_a_finished_command_is_complete_so_the_turn_can_end_early():
    actions = FakeActions()
    assert is_complete_command("Open Spotify", ctx(actions))
    assert actions.calls == []  # checking never acts


def test_unfinished_or_unknown_commands_and_dictation_are_not_complete():
    assert not is_complete_command("open", ctx())
    assert not is_complete_command("open visual", ctx())
    assert not is_complete_command("Remind the team", ctx())


def test_pause_and_next_control_whatever_is_playing():
    actions = FakeActions()
    out = handle("Pause.", ctx(actions))
    assert (out.card.verb, out.card.obj, out.card.icon) == ("Paused", "Spotify", "spotify")
    assert handle("skip", ctx(actions)).card.verb == "Next track"
    assert actions.calls == [("media", "pause", None), ("media", "next", None)]


def test_naming_a_player_controls_that_one():
    actions = FakeActions()
    handle("pause chrome", ctx(actions))
    assert actions.calls == [("media", "pause", "chrome")]


def test_nothing_playing_says_so_calmly():
    actions = FakeActions()
    actions.player = None
    out = handle("resume", ctx(actions))
    assert isinstance(out, NoMatch)
    assert (out.card.verb, out.card.obj) == ("Nothing", "playing")


def test_volume_can_be_set_stepped_and_muted():
    actions = FakeActions()
    assert handle("Volume 30.", ctx(actions)).card.obj == "30%"
    assert handle("volume thirty five", ctx(actions)).card.obj == "35%"
    assert handle("volume up", ctx(actions)).card.obj == "45%"
    assert handle("mute", ctx(actions)).card.verb == "Muted"
    assert actions.calls == [("set_volume", 30), ("set_volume", 35), ("set_volume", 45), ("mute", True)]


def test_folders_drives_settings_and_websites_open_as_places():
    actions = FakeActions()
    assert handle("Open Downloads folder.", ctx(actions)).card.obj == "Downloads"
    assert handle("open d drive", ctx(actions)).card.obj == "D drive"
    assert handle("open bluetooth settings", ctx(actions)).card.obj == "Bluetooth settings"
    assert handle("open youtube", ctx(actions)).card.obj == "YouTube"
    assert handle("can you open linkedin", ctx(actions)).card.obj == "LinkedIn"
    assert actions.calls == [("open_place", r"C:\Users\me\Downloads"), ("open_place", "D:\\"),
                             ("open_place", "ms-settings:bluetooth"), ("open_place", "https://www.youtube.com"),
                             ("open_place", "https://www.linkedin.com/feed/")]


def test_search_spotify_youtube_and_the_web():
    actions = FakeActions()
    out = handle("Search Spotify for lo-fi beats", ctx(actions))
    assert (out.card.verb, out.card.obj, out.card.icon) == ("Searching Spotify", "lo-fi beats", "spotify")
    handle("search youtube for cat videos", ctx(actions))
    handle("Google how tall is Everest", ctx(actions))
    handle("search the web for weather", ctx(actions))
    assert actions.calls == [
        ("open_url", "spotify:search:lo-fi%20beats"),
        ("open_url", "https://www.youtube.com/results?search_query=cat+videos"),
        ("open_url", "https://www.google.com/search?q=how+tall+is+everest"),
        ("open_url", "https://www.google.com/search?q=weather")]


LOCALFLOW = Target("localflow", "LocalFlow")


def busy_desk():
    actions = FakeActions()
    actions.windows = {"spotify": ["Spotify Premium"], "chrome": ["Inbox - Gmail", "YouTube"],
                       "vscode": ["local-flow"], "localflow": ["LocalFlow"]}
    return actions


def test_close_one_app_closes_it_without_asking():
    actions = busy_desk()
    out = handle("Close Spotify.", ctx(actions))
    assert (out.card.verb, out.card.obj) == ("Closing", "Spotify")
    assert actions.calls == [("close", "spotify")]


def test_closing_an_app_that_isnt_open_says_so():
    out = handle("close spotify", ctx(FakeActions()))
    assert isinstance(out, NoMatch)
    assert (out.card.verb, out.card.obj) == ("Not open", "Spotify")


def test_minimise_one_app_or_everything():
    actions = busy_desk()
    assert handle("minimize chrome", ctx(actions)).card.verb == "Minimised"
    assert handle("minimise everything", ctx(actions)).card.obj == "Everything"
    assert actions.calls == [("minimise", "chrome"), ("minimise_all",)]


def test_closing_several_apps_asks_first_and_never_closes_localflow():
    actions = busy_desk()
    out = handle("close everything", ctx(actions, catalog=(SPOTIFY, CHROME, VSCODE, LOCALFLOW)))
    assert isinstance(out, NeedsConfirmation)
    assert out.question == "Close 3 apps?"
    assert [(t.name, titles) for t, titles in out.apps] == [
        ("Spotify", ["Spotify Premium"]), ("Google Chrome", ["Inbox - Gmail", "YouTube"]), ("Visual Studio Code", ["local-flow"])]
    assert actions.calls == []  # nothing closes before the answer


def test_saying_yes_closes_them_and_no_or_silence_keeps_them():
    actions = busy_desk()
    asked = handle("close all apps", ctx(actions))
    assert answer("Yeah, do it.") == "yes"
    assert answer("no thanks") == "no"
    assert answer("") == "no"
    assert answer("what's the weather") is None
    out = confirm(asked, True, ctx(actions))
    assert (out.card.verb, out.card.obj) == ("Closed", "3 apps")
    assert sorted(actions.calls) == [("close", "chrome"), ("close", "spotify"), ("close", "vscode")]
    kept = confirm(asked, False, ctx(busy_desk()))
    assert (kept.card.verb, kept.card.obj) == ("Kept open", "3 apps")


CLAUDE_STORE = Target("Claude_pzs8sxrjxfjjc!Claude", "Claude")
CLAUDE_OLD = Target("com.squirrel.AnthropicClaude.claude", "Claude")


def test_an_alias_opens_its_target_with_or_without_open():
    c = ctx()
    c.aliases = [Alias("music", "spotify", suggested=True)]
    assert handle("open music", c).card.obj == "Spotify"
    assert handle("Music.", c).card.obj == "Spotify"


def test_duplicate_apps_prefer_voice_use_then_windows_use_then_the_store_version():
    assert handle("open claude", ctx(catalog=(CLAUDE_OLD, CLAUDE_STORE))).card.icon == CLAUDE_STORE.id  # Store by default
    c = ctx(catalog=(CLAUDE_OLD, CLAUDE_STORE))
    c.windows_usage = {CLAUDE_OLD.id: 30}
    assert handle("open claude", c).card.icon == CLAUDE_OLD.id            # Windows saw that one used
    c.usage = {CLAUDE_STORE.id: 3}
    assert handle("open claude", c).card.icon == CLAUDE_STORE.id          # what you open by voice wins


def test_each_command_is_counted_so_suggestions_learn():
    c = ctx()
    used = []
    c.on_use = lambda target_id, heard: used.append((target_id, heard))
    handle("open spotify", c)
    handle("open spotify", c)
    assert c.usage == {"spotify": 2}
    assert used == [("spotify", "open spotify"), ("spotify", "open spotify")]


def test_command_log_rebuilds_usage_and_ignores_a_damaged_line(tmp_path):
    path = tmp_path / "commands.jsonl"
    append_command(path, "open spotify", "spotify", datetime(2026, 10, 31, 12, 0))
    append_command(path, "pause spotify", "spotify", datetime(2026, 10, 31, 12, 1))
    with open(path, "a", encoding="utf-8") as f:
        f.write("not json\n")
    assert read_command_usage(path) == {"spotify": 2}
    text = path.read_text(encoding="utf-8")
    assert '"command": "open spotify"' in text and '"ts": "2026-10-31T12:00:00"' in text


def test_suggested_aliases_only_for_installed_apps_and_not_dismissed():
    chatgpt = Target("OpenAI.Codex_2p2nqsd0c76g0!App", "ChatGPT")
    antigravity, ide = Target("Google.Antigravity", "Antigravity"), Target("Google.AntigravityIDE", "Antigravity IDE")
    catalog = [SPOTIFY, chatgpt, antigravity, ide]
    got = {(a.say, a.target_id) for a in suggested_aliases(catalog, dismissed={"music"})}
    assert got == {("codex", chatgpt.id), ("antigravity", antigravity.id)}
    assert all(a.suggested for a in suggested_aliases(catalog, dismissed=set()))


def test_top_apps_put_named_favourites_and_most_used_first():
    catalog = [VSCODE, SPOTIFY, CHROME]
    top = top_apps(catalog, usage={"vscode": 1}, windows_usage={"chrome": 178}, favourites=["Spotify"])
    assert [t.id for t in top] == ["vscode", "chrome", "spotify"]


def test_a_routine_runs_safe_steps_in_order():
    actions = FakeActions()
    c = ctx(actions)
    c.routines = [Routine("Work mode", (RoutineStep("open", "chrome"), RoutineStep("open", "spotify"),
                                        RoutineStep("minimise_all"), RoutineStep("media", action="play")))]
    out = handle("work mode", c)
    assert (out.card.verb, out.card.obj) == ("Ran", "Work mode")
    assert actions.calls == [("switch_to", "chrome"), ("launch", "chrome"),
                             ("switch_to", "spotify"), ("launch", "spotify"),
                             ("minimise_all",), ("media", "play", None)]


def test_wrap_up_keeps_the_chosen_app_and_asks_before_closing_the_rest():
    actions = busy_desk()
    explorer = Target("explorer", "File Explorer")
    actions.windows["explorer"] = ["Documents"]
    c = ctx(actions, catalog=(SPOTIFY, CHROME, VSCODE, LOCALFLOW, explorer))
    c.routines = [Routine("Wrap up", (RoutineStep("close_all_except", keep=("explorer",)),))]
    out = handle("Wrap up", c)
    assert isinstance(out, NeedsConfirmation)
    assert [t.id for t, _ in out.apps] == ["spotify", "chrome", "vscode"]


def test_a_confirmed_close_step_continues_the_routine():
    actions = busy_desk()
    c = ctx(actions)
    c.routines = [Routine("Reset", (RoutineStep("close_all_except"), RoutineStep("open", "spotify")))]
    asked = handle("reset", c)
    out = confirm(asked, True, c)
    assert (out.card.verb, out.card.obj) == ("Ran", "Reset")
    assert ("launch", "spotify") in actions.calls


def test_suggested_routines_need_their_apps_and_stay_dismissed():
    explorer = Target("explorer", "File Explorer")
    youtube = Target("youtube", "YouTube", "website", "https://youtube.com")
    claude = Target("claude", "Claude")
    got = suggested_routines([CHROME, claude, explorer, youtube], {"break time"})
    assert [r.name for r in got] == ["Work mode", "Wrap up"]
    assert all(r.suggested for r in got)


def test_speech_without_a_command_word_is_dictation():
    assert handle("Remind the team about Friday", ctx()) == Dictation("Remind the team about Friday")
