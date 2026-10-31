"""Turning a raw transcript into the text that gets pasted."""
from textfx import Options, postprocess

PLAIN = Options(numbers=False)


def test_fillers_are_dropped():
    assert postprocess("Um, so I think we should go.") == "So I think we should go."


def test_fillers_kept_when_switched_off():
    assert postprocess("Um, hello.", Options(fillers=False)) == "Um, hello."


def test_numbered_list_from_spoken_numbers_with_punctuation():
    assert postprocess("Here's my plan. One, buy milk. Two, call the bank.", PLAIN) == \
        "Here's my plan:\n1. Buy milk\n2. Call the bank"


def test_counting_in_a_sentence_stays_a_sentence():
    text = "I have one question and two concerns."
    assert postprocess(text, PLAIN) == text


def test_first_then_finally_makes_a_list():
    assert postprocess("First, open the app. Then sign in. Finally, check the logs.", PLAIN) == \
        "1. Open the app\n2. Sign in\n3. Check the logs"


def test_then_on_its_own_stays_prose():
    assert postprocess("Then I went home.", PLAIN) == "Then I went home."


def test_bullet_points():
    assert postprocess("Bullet point apples. Bullet point pears.", PLAIN) == "- Apples\n- Pears"


def test_lists_switched_off():
    text = "One, buy milk. Two, call the bank."
    assert postprocess(text, Options(lists=False, numbers=False)) == text


def test_new_line_and_new_paragraph():
    assert postprocess("Hello new line world new paragraph bye", PLAIN) == "Hello\nworld\n\nbye"


def test_replacements_apply_whole_words():
    opts = Options(numbers=False, replacements=(("gonna", "going to"),))
    assert postprocess("I'm gonna go.", opts) == "I'm going to go."


def test_swap_sources_apply_in_order():
    class Swap:
        def __init__(self, a, b):
            self.a, self.b = a, b

        def apply(self, text):
            return text.replace(self.a, self.b)

    assert postprocess("I use cloud code.", PLAIN, [Swap("cloud", "Claude"), Swap("Claude", "X")]) == \
        "I use X code."
