"""Token measure, bands, calibration and excerpts shared by every participant's model input."""

import pytest

from experimental.harness.participation.allowance import (
    Band,
    Calibration,
    context_window,
    estimate_tokens,
    excerpt,
    measure_name,
    reading_budget,
)


def test_a_band_admits_below_clear_refuses_from_refuse_and_is_near_between():
    band = Band.of(1000, (0.25, 0.5))
    assert band == Band(250, 500) and band.describe() == {"clear": 250, "refuse": 500}
    assert [band.verdict(tokens) for tokens in (0, 249, 250, 499, 500)] == ["clear", "clear", "near", "near", "over"]
    assert Band.of(3, (0.1, 0.2)) == Band(1, 1)
    with pytest.raises(ValueError, match="ordered"):
        Band.of(1000, (0.5, 0.25))
    with pytest.raises(ValueError, match="0 < clear <= refuse"):
        Band(0, 5)


def test_the_window_prefers_the_configured_value_then_the_rate_tables_then_the_default():
    assert context_window("any/model", configured=4096) == 4096
    assert context_window("nobody/knows-this") == context_window(None) == 200_000
    assert reading_budget("any/model", configured=1600) == 100
    assert reading_budget("nobody/knows-this", share=0.5) == 100_000
    with pytest.raises(ValueError, match="positive"):
        reading_budget(share=0)


def test_estimates_count_tokens_and_calibration_learns_the_providers_ratio():
    assert measure_name() in {"tiktoken o200k_base", "character heuristic"}
    short, long = estimate_tokens("one two three"), estimate_tokens("one two three " * 100)
    assert 1 <= short < long < 1000
    calibration = Calibration()
    assert calibration.ratio("m") == 1.0 and calibration.scaled("m", 100) == 100
    calibration.learn("m", 100, 150)
    calibration.learn("m", 100, 130)
    calibration.learn("m", 0, 50)
    calibration.learn("m", 100, None)
    assert calibration.ratio("m") == pytest.approx(1.4) and calibration.scaled("m", 100) == 140
    assert calibration.ratio("other") == 1.0


def test_an_excerpt_keeps_a_prefix_of_the_text_and_says_how_much_was_left_out():
    text = "The quick brown fox jumps over the lazy dog. " * 40
    shown = excerpt(text, 12)
    assert text.startswith(shown.split("\n[... ")[0]) and shown.endswith(" more characters not shown]")
    left = int(shown.rsplit("[... ", 1)[1].split(" ")[0])
    assert left == len(text) - len(shown.split("\n[... ")[0])
    assert excerpt("short", 12) == "short"
    with pytest.raises(ValueError, match="positive"):
        excerpt("text", 0)
