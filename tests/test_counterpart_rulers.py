"""The owner's shared measures: a case's reference words, tables and a word search over what a drill produced."""

import pytest

from experimental.cultivation.counterpart.rulers import SNIPPET, occurrences, tables, words


def test_reference_words_are_the_backticked_values_of_each_keyed_row(tmp_path):
    reference = tmp_path / "reference.md"
    reference.write_text(
        "Intro line.\n\n| key | values | note |\n|---|---|---|\n| banned | `free` `best` | words |\n"
        "| Not a key | `x` | skipped |\n| empty | none | skipped |\n\nAfter.\n"
    )
    assert words(reference) == {"banned": ("free", "best")}
    assert tables(reference.read_text()) == [
        [["key", "values", "note"], ["banned", "`free` `best`", "words"], ["Not a key", "`x`", "skipped"]]
        + [["empty", "none", "skipped"]]
    ]


def test_each_term_is_found_with_a_short_stretch_of_every_line_it_stands_on():
    text = "The best offer.\nNothing here.\n" + "x" * 100 + " best " + "y" * 100
    found = occurrences(text, ("free", "best"))
    assert list(found) == ["best"]
    first, second = found["best"]
    assert first == "The best offer." and "best" in second and len(second) == SNIPPET


def test_a_figure_is_read_the_way_it_is_said_aloud():
    from experimental.cultivation.counterpart.rulers import chinese_number

    def han(*codes):
        return "".join(chr(code) for code in codes)

    one, five, nine, ten, hundred, point, zero = (
        han(code) for code in (0x4E00, 0x4E94, 0x4E5D, 0x5341, 0x767E, 0x70B9, 0x96F6)
    )
    assert chinese_number("99") == nine + ten + nine and chinese_number("10") == ten
    assert chinese_number("19.9") == ten + nine + point + nine
    assert chinese_number("105") == one + hundred + zero + five
    assert chinese_number("10000") == one + han(0x4E07) and chinese_number("1,000") == one + han(0x5343)
    assert len(chinese_number("140351.67")) == 12
    with pytest.raises(ValueError):
        chinese_number("12a")
