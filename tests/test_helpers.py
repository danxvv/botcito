"""Check how command text is parsed and how times are shown."""

import pytest

import youtube
from commands.helpers import (
    format_clock,
    format_duration,
    parse_seek_position,
    render_progress_bar,
    song_duration_label,
)


@pytest.mark.parametrize(
    "text, current, expected",
    [
        ("90", 0, 90),
        ("0", 50, 0),
        ("1:30", 0, 90),
        ("01:30", 99, 90),
        ("1:02:03", 0, 3723),
        ("  2:00  ", 0, 120),
        ("+30", 100, 130),
        ("-15", 100, 85),
        ("- 15", 100, 85),
        ("-500", 100, 0),  # Rewinding past the start stops at the start.
        ("+1:00", 10, 70),
        ("-1:00", 90, 30),
        ("1:75", 0, 135),  # Overflowing seconds are added, not rejected.
    ],
)
def test_parse_seek_position(text, current, expected):
    assert parse_seek_position(text, current) == expected


@pytest.mark.parametrize(
    "text",
    ["", " ", "abc", "1:2:3:4", "1:", ":30", "1.5", "--5", "+-5", "1:30s", "²", "٣", "1::30", "0x10"],
)
def test_parse_seek_position_rejects_anything_else(text):
    with pytest.raises(ValueError):
        parse_seek_position(text)


@pytest.mark.parametrize(
    "seconds, expected",
    [(0, "0:00"), (5, "0:05"), (65, "1:05"), (3599, "59:59"), (3600, "1:00:00"), (3723, "1:02:03"), (-4, "0:00")],
)
def test_format_clock(seconds, expected):
    assert format_clock(seconds) == expected


def test_zero_length_means_live_but_zero_position_does_not():
    assert format_duration(0) == "Live"
    assert format_duration(-1) == "Live"
    assert format_duration(185) == "3:05"
    assert format_clock(0) == "0:00"


def test_progress_bar_still_formats_live_streams():
    assert render_progress_bar(30, 0).endswith("Live")
    assert render_progress_bar(30, 60).endswith("0:30 / 1:00")


def test_unprepared_playlist_entries_show_no_length_instead_of_live():
    entry = youtube.playlist_entry_song({"video_id": "abcdefghijk"})
    assert song_duration_label(entry) == "…"
    known = youtube.playlist_entry_song({"video_id": "abcdefghijk", "duration": 95})
    assert song_duration_label(known) == "1:35"
    entry.resolved = True  # Prepared and still zero: that really is a live stream.
    assert song_duration_label(entry) == "Live"
