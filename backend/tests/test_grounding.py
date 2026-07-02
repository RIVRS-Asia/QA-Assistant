"""Box-parsing for the auto-annotation grounding step (pure, no network/key needed).

Run from backend/:  ./.venv/Scripts/python.exe -m pytest tests/test_grounding.py -v
"""
from pipeline.grounding import _parse_box


def test_parses_plain_array():
    assert _parse_box("[100, 200, 400, 600]") == [100, 200, 400, 600]


def test_parses_array_embedded_in_prose():
    assert _parse_box("The region is [10, 20, 300, 400] in the image.") == [10, 20, 300, 400]


def test_null_reply_is_none():
    assert _parse_box("null") is None
    assert _parse_box("") is None


def test_rejects_out_of_range_and_inverted_boxes():
    assert _parse_box("[0, 0, 2000, 100]") is None      # > 1000
    assert _parse_box("[400, 0, 100, 600]") is None      # ymin >= ymax
    assert _parse_box("[0, 600, 400, 200]") is None      # xmin >= xmax
