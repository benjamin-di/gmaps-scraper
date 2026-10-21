"""Structured opening hours from real [203] blocks captured 2026-10-21.

The fixture keeps only the hours block of each place, all in Vienna: SPAR and
BILLA (Austrian National Day on Monday 26 Oct, confirmed closed vs. "might
affect"), a 24-hour petrol station, a bar closing after midnight and a
restaurant with lunch and dinner sittings, the dinner one closing at midnight.
"""

import json
from pathlib import Path

from gmaps.rpc.parser import ParsedPlace, _extract_hours_new, parse_opening_hours

FIXTURE = Path(__file__).parent / "fixtures" / "live" / "hours_2026-10-21.json"
SAMPLES = json.loads(FIXTURE.read_text(encoding="utf-8"))


def _days(name):
    return parse_opening_hours(SAMPLES[name]["hours_203"])


def _day(name, date):
    return next(d for d in _days(name) if d["date"] == date)


def test_seven_dated_days_starting_today():
    days = _days("SPAR Gourmet")
    assert [d["date"] for d in days] == [f"2026-10-{n}" for n in range(21, 28)]
    assert days[0]["weekday"] == "Wednesday" and days[0]["iso_weekday"] == 3
    assert days[5]["weekday"] == "Monday" and days[5]["iso_weekday"] == 1


def test_regular_day():
    day = _day("SPAR Gourmet", "2026-10-21")
    assert day["periods"] == [{"open": "07:30", "close": "20:00"}]
    assert day["closed"] is False and day["open_24_hours"] is False
    assert "special" not in day


def test_confirmed_holiday_closure():
    day = _day("SPAR Gourmet", "2026-10-26")
    assert day["closed"] is True and day["periods"] == []
    assert day["special"] == {
        "name": "Austrian National Day",
        "label": "Austrian National Day hours",
        "confirmed": True,
    }


def test_unconfirmed_holiday_keeps_regular_hours():
    day = _day("BILLA", "2026-10-26")
    assert day["closed"] is False
    assert day["periods"] == [{"open": "07:40", "close": "20:00"}]
    assert day["special"]["confirmed"] is False
    assert day["special"]["name"] == "Austrian National Day"


def test_weekly_closed_day():
    day = _day("SPAR Gourmet", "2026-10-25")
    assert day["closed"] is True and day["text"] == ["Closed"] and "special" not in day


def test_open_24_hours():
    day = _day("bp", "2026-10-21")
    assert day["open_24_hours"] is True
    assert day["periods"] == [{"open": "00:00", "close": "24:00"}]


def test_closes_at_midnight():
    day = _day("Steirereck", "2026-10-21")
    assert day["periods"][-1] == {"open": "18:30", "close": "24:00"}
    assert day["text"][-1] == "6:30\u202fPM–12\u202fAM"


def test_closes_after_midnight():
    day = _day("Loos American Bar", "2026-10-21")
    assert day["periods"] == [{"open": "12:00", "close": "04:00", "closes_next_day": True}]


def test_split_hours():
    day = _day("Steirereck", "2026-10-21")
    assert day["periods"] == [
        {"open": "11:30", "close": "14:30"},
        {"open": "18:30", "close": "24:00"},
    ]
    assert day["text"] == ["11:30\u202fAM–2:30\u202fPM", "6:30\u202fPM–12\u202fAM"]


def test_extract_sets_structured_hours_and_status_and_keeps_legacy_dict():
    # The fixture keeps only the per-day hours; the status line ([203][1][4][0]) is set here.
    block = list(SAMPLES["BILLA"]["hours_203"])
    block[1] = [None, None, None, None, ["Open · Closes 8\u202fPM"]]
    pd = [None] * 204
    pd[203] = block
    place = ParsedPlace()
    _extract_hours_new(pd, place)
    assert len(place.opening_hours) == 7
    assert place.hours_status == "Open · Closes 8\u202fPM"
    assert place.hours["Wednesday"] == ["7:40\u202fAM–8\u202fPM"]
    biz = place.to_dict()["business"]
    assert biz["opening_hours"] == place.opening_hours
    assert biz["hours_status"] == "Open · Closes 8\u202fPM"


def test_malformed_entries_are_skipped_not_guessed():
    block = [[["Monday", 1, None, [["9 AM–5 PM", [[9], [17]]]], 0, 1], "junk", ["Tuesday"]]]
    assert parse_opening_hours(block) == []
    assert parse_opening_hours(None) == []
