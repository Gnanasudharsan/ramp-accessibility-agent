import pytest

from ramp.checks.contrast import (
    RGBA,
    contrast_ratio,
    is_large_text,
    parse_css_color,
    required_ratio,
)


def test_black_on_white_is_21() -> None:
    assert contrast_ratio(RGBA(0, 0, 0), RGBA(255, 255, 255)) == pytest.approx(21.0)


def test_same_colour_is_1() -> None:
    assert contrast_ratio(RGBA(120, 50, 200), RGBA(120, 50, 200)) == pytest.approx(1.0)


def test_known_threshold_grey() -> None:
    # #767676 on white is the classic "just passes AA" grey: 4.54:1.
    assert contrast_ratio(parse_css_color("rgb(118, 118, 118)"), RGBA(255, 255, 255)) == (
        pytest.approx(4.54, abs=0.01)
    )


def test_translucent_foreground_is_composited() -> None:
    half_black = parse_css_color("rgba(0, 0, 0, 0.5)")
    composited = half_black.over(RGBA(255, 255, 255))
    assert composited.r == pytest.approx(127.5)
    assert contrast_ratio(half_black, RGBA(255, 255, 255)) == pytest.approx(
        contrast_ratio(composited, RGBA(255, 255, 255))
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("rgb(1, 2, 3)", RGBA(1, 2, 3, 1.0)),
        ("rgba(1, 2, 3, 0.25)", RGBA(1, 2, 3, 0.25)),
        ("rgb(1 2 3 / 50%)", RGBA(1, 2, 3, 0.5)),
        ("transparent", RGBA(0, 0, 0, 0.0)),
    ],
)
def test_parse_css_color(value: str, expected: RGBA) -> None:
    assert parse_css_color(value) == expected


def test_parse_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        parse_css_color("color(display-p3 1 0 0)")


def test_large_text_thresholds() -> None:
    assert required_ratio(16, 400) == 4.5
    assert required_ratio(24, 400) == 3.0
    assert required_ratio(18.66, 700) == 3.0
    assert not is_large_text(18.66, 400)
