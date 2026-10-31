"""Turning a raw transcript into the text that gets pasted."""
from textfx import Options, Transcript, postprocess

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


# -- numbers

def test_years_become_digits():
    assert postprocess("In twenty twenty six we grow.") == "In 2026 we grow."


def test_money_and_percentages():
    assert postprocess("I'm on the twenty dollar plan.") == "I'm on the $20 plan."
    assert postprocess("It costs five dollars, fifty percent off.") == "It costs $5, 50% off."


def test_times():
    assert postprocess("Meet at three thirty.") == "Meet at 3:30."


def test_ten_and_above_become_digits():
    assert postprocess("Twenty five people came.") == "25 people came."


def test_big_round_numbers_read_naturally():
    assert postprocess("We have five million users and twenty five thousand teams.") == \
        "We have 5 million users and 25,000 teams."


def test_small_numbers_stay_words_in_prose():
    for text in ("I have one question and two concerns.", "We need three apples."):
        assert postprocess(text) == text


def test_numbers_switched_off():
    assert postprocess("Twenty five people came.", Options(numbers=False)) == "Twenty five people came."


def test_numbers_inside_a_list_are_not_list_markers():
    assert postprocess("One, buy twenty apples. Two, call the bank.") == \
        "1. Buy 20 apples\n2. Call the bank"


# -- spoken lists

def test_spoken_numbers_without_punctuation_make_a_list():
    assert postprocess("One buy milk two call the bank three pay rent") == \
        "1. Buy milk\n2. Call the bank\n3. Pay rent"


def test_counting_without_punctuation_stays_a_sentence():
    for text in ("I have one question and two concerns.",
                 "One thing I learned is that two heads are better than one."):
        assert postprocess(text) == text


def test_then_after_a_pause_continues_an_open_list():
    said = Transcript(("One, buy milk. Two, call the bank.", "Then pay the rent."), (0.0, 0.8))
    assert postprocess(said) == "1. Buy milk\n2. Call the bank\n3. Pay the rent"


def test_then_without_a_pause_stays_in_the_point():
    said = Transcript(("One, buy milk. Two, call the bank and then pay the rent.",), (0.0,))
    assert postprocess(said) == "1. Buy milk\n2. Call the bank and then pay the rent"


def test_then_after_a_pause_with_no_list_stays_prose():
    said = Transcript(("I finished work.", "Then I went home."), (0.0, 0.8))
    assert postprocess(said) == "I finished work. Then I went home."


def test_pause_split_parts_join_into_one_sentence():
    said = Transcript(("I think we should.", "go to the park."), (0.0, 0.8))
    assert postprocess(said) == "I think we should go to the park."


# -- Starter words

def test_starter_words_group_switch_changes_the_output():
    from starter import StarterWords
    assert postprocess("I asked chat gpt.", PLAIN, [StarterWords()]) == "I asked ChatGPT."
    assert postprocess("I asked chat gpt.", PLAIN, [StarterWords({"tech": False})]) == "I asked chat gpt."


def test_your_dictionary_wins_over_starter_words(tmp_path):
    from dictionary import Dictionary
    from starter import StarterWords
    mine = Dictionary(tmp_path / "dictionary.json")
    mine.add("chat gpt", "Chat GPT")
    assert postprocess("I asked chat gpt.", PLAIN, [mine, StarterWords(yours=mine)]) == "I asked Chat GPT."


def test_spoken_shorthand_is_written_short():
    from starter import StarterWords
    assert postprocess("L G T M, ship it.", PLAIN, [StarterWords()]) == "LGTM, ship it."
