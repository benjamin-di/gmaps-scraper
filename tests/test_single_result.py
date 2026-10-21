"""A query that names one place exactly returns that place in data[0][1][0]."""

import json
from pathlib import Path

from gmaps.rpc.parser import parse_search_response

LIVE = Path(__file__).parent / "fixtures" / "live"


def _load(name):
    return json.loads((LIVE / name).read_text(encoding="utf-8"))


def test_single_exact_match_is_parsed():
    # Real response captured 2026-10-21 for "Café Sperl Gumpendorfer Straße" in Vienna,
    # pruned to the fields the parser reads.
    places = parse_search_response(_load("search_single_result_2026-10-21.json"))
    assert len(places) == 1
    place = places[0]
    assert place.name == "Café Sperl"
    assert place.place_id == "ChIJ2XE5E4UHbUcRnNXnuwsVah8"
    assert place.latitude is not None and place.longitude is not None


def test_metadata_entry_without_name_is_still_skipped():
    metadata = [None] * 15
    metadata[14] = [None] * 20  # place-data-shaped, but no name at [11]
    business = [None] * 15
    business[14] = [None] * 20
    business[14][11] = "Cafe"
    business[14][18] = "1 Main St"
    places = parse_search_response([[None, [metadata, business]]])
    assert [p.name for p in places] == ["Cafe"]
