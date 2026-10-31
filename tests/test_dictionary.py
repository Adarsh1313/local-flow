"""The Dictionary: learning from Fixes, then swapping words in later Dictations."""
import json

from dictionary import Dictionary, Learned, Refused, Waiting, describe


def fresh(tmp_path):
    return Dictionary(tmp_path / "dictionary.json")


def test_fix_to_a_name_is_learned_at_once_even_between_everyday_words(tmp_path):
    d = fresh(tmp_path)
    assert isinstance(d.learn("cloud", "Claude", ["code"]), Learned)
    assert d.apply("I asked cloud about it.") == "I asked Claude about it."


def test_rare_mishearing_is_learned_at_once(tmp_path):
    d = fresh(tmp_path)
    assert isinstance(d.learn("Lukendra", "Lokendra", []), Learned)
    assert d.apply("Call Lukendra today.") == "Call Lokendra today."


def test_rewording_waits_for_a_second_identical_fix(tmp_path):
    d = fresh(tmp_path)
    assert isinstance(d.learn("patch", "batch", ["next"]), Waiting)
    assert d.apply("the next patch") == "the next patch"
    assert isinstance(d.learn("patch", "batch", ["next"]), Learned)
    assert d.apply("the next patch") == "the next batch"


def test_name_over_a_very_common_word_only_swaps_next_to_its_words(tmp_path):
    d = fresh(tmp_path)
    assert isinstance(d.learn("New", "Nuvo", ["health"]), Learned)
    assert d.apply("Nuvo health, a new idea") == "Nuvo health, a new idea"
    assert d.apply("New health is here") == "Nuvo health is here"


def test_a_fix_you_turned_off_is_refused_with_a_reason(tmp_path):
    d = fresh(tmp_path)
    d.learn("Bodhi", "Boardy", [])
    d.set_mode("Bodhi", "off")
    outcome = d.learn("Bodhi", "Boardy", [])
    assert isinstance(outcome, Refused) and outcome.reason
    assert d.apply("Bodhi said hi") == "Bodhi said hi"


def test_learning_survives_a_restart(tmp_path):
    fresh(tmp_path).learn("cloud", "Claude", [])
    assert fresh(tmp_path).apply("cloud code") == "Claude code"


def test_old_switched_off_fixes_are_rechecked(tmp_path):
    path = tmp_path / "dictionary.json"
    path.write_text(json.dumps([
        {"heard": "codecs", "wanted": "Claude", "source": "learned", "mode": "off", "context": [], "count": 1},
        {"heard": "man", "wanted": "manan", "source": "learned", "mode": "off", "context": [], "count": 1},
    ]), encoding="utf-8")
    d = Dictionary(path)
    assert d.apply("ask codecs") == "ask Claude"
    assert d.apply("the man") == "the man"
    assert [e["heard"] for e in d.not_applied()] == ["man"]


def test_card_text_says_what_happened(tmp_path):
    d = fresh(tmp_path)
    assert describe(d.learn("cloud", "Claude", [])) == ("Added to dictionary", "Claude")
    verb, obj = describe(d.learn("patch", "batch", []))
    assert verb == "Not added yet" and "batch" in obj
