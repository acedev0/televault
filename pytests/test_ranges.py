import pytest

from televault.ranges import RangeNotSatisfiable, parse_range_header


def test_no_range_returns_entire_file():
    selected = parse_range_header(None, 1000)
    assert (selected.start, selected.end, selected.length, selected.partial) == (0, 999, 1000, False)


def test_bounded_range():
    selected = parse_range_header("bytes=100-299", 1000)
    assert (selected.start, selected.end, selected.length) == (100, 299, 200)
    assert selected.content_range == "bytes 100-299/1000"


def test_open_ended_range():
    selected = parse_range_header("bytes=900-", 1000)
    assert (selected.start, selected.end, selected.length) == (900, 999, 100)


def test_suffix_range():
    selected = parse_range_header("bytes=-250", 1000)
    assert (selected.start, selected.end, selected.length) == (750, 999, 250)


def test_suffix_larger_than_file_is_clamped():
    selected = parse_range_header("bytes=-5000", 1000)
    assert (selected.start, selected.end) == (0, 999)


def test_end_larger_than_file_is_clamped():
    selected = parse_range_header("bytes=500-5000", 1000)
    assert (selected.start, selected.end) == (500, 999)


@pytest.mark.parametrize(
    "header,size",
    [
        ("items=0-10", 100),
        ("bytes=10-5", 100),
        ("bytes=100-101", 100),
        ("bytes=0-1,4-5", 100),
        ("bytes=-0", 100),
        ("bytes=a-b", 100),
        (None, 0),
    ],
)
def test_invalid_ranges(header, size):
    with pytest.raises(RangeNotSatisfiable):
        parse_range_header(header, size)

