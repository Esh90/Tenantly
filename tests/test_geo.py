"""Boundaries, point-in-polygon, address normalization and the resolved addresses (offline:
they read the committed artifacts, so no network is needed)."""

import json

import pytest

from engine import config
from engine.geo import geocode
from engine.geo.jurisdictions import CITIES, COUNTIES
from engine.geo.pip import Locator

ART = config.ARTIFACTS


@pytest.fixture(scope="module")
def resolved():
    return json.loads((ART / "addresses.resolved.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def loc():
    return Locator()


def test_boundaries_cover_the_scope():
    report = json.loads((ART / "eval" / "geo_boundaries.json").read_text(encoding="utf-8"))
    assert len(report["cities"]) == 10 and len(report["counties"]) == len(COUNTIES) == 9
    assert {c["geoid"] for c in report["cities"]} == {c.place_geoid for c in CITIES}
    assert all(c["tiger_name"] for c in report["cities"])
    cousub = [c for c in report["cities"] if c["layer"] == "COUSUB"]
    assert len(cousub) == 5 and all(c.get("place_iou", 1) > 0.9 for c in cousub)
    gj = json.loads((ART / "geo" / "jurisdictions.geojson").read_text(encoding="utf-8"))
    levels = [f["properties"]["level"] for f in gj["features"]]
    assert (levels.count("state"), levels.count("county"), levels.count("city")) == (3, 9, 10)


@pytest.mark.parametrize(
    ("lat", "lon", "city"),
    [
        (37.7749, -122.4194, "CA-0667000"),  # San Francisco
        (34.0522, -118.2437, "CA-0644000"),  # Los Angeles
        (32.7157, -117.1611, "CA-0666000"),  # San Diego
        (37.8715, -122.2730, "CA-0606000"),  # Berkeley
        (40.7178, -74.0431, "NJ-3436000"),  # Jersey City
        (40.7439, -74.0324, "NJ-3432250"),  # Hoboken
        (40.7357, -74.1724, "NJ-3451000"),  # Newark
        (42.3601, -71.0589, "MA-2507000"),  # Boston
        (42.3736, -71.1097, "MA-2511000"),  # Cambridge
    ],
)
def test_point_in_polygon_known_places(loc, lat, lon, city):
    assert loc.locate(lat, lon).city_id == city


def test_point_outside_every_city(loc):
    assert loc.locate(41.0, -100.0).city_id is None  # Nebraska
    assert loc.locate(37.5, -122.8).city_id is None  # Pacific Ocean off San Francisco


def test_counties_resolve(loc):
    assert loc.locate(37.7749, -122.4194).county_id == "CA-06075"
    assert loc.locate(40.7178, -74.0431).county_id == "NJ-34017"


def test_jersey_city_and_hoboken_are_distinct(loc):
    assert loc.locate(40.7178, -74.0431).city_id != loc.locate(40.7439, -74.0324).city_id


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1031-1035 CLINTON ST", "1031 CLINTON ST"),
        ("322-322.5 Western Ave", "322 WESTERN AVE"),
        ("14.5-16 Vandine St", "14 VANDINE ST"),
        ("18-34 Kingbird Rd", "18 KINGBIRD RD"),
        ("397 05TH AV", "397 5TH AVE"),
        ("90 KENSINGTON AVE.", "90 KENSINGTON AVE"),
        ("876-878 S 14TH ST", "876 S 14TH ST"),
    ],
)
def test_street_normalization(raw, expected):
    assert geocode.normalize_street(raw) == expected


def test_suffix_variants_and_city_hints():
    assert geocode.street_variants("10 Main Street") == ["10 MAIN STREET", "10 MAIN ST"]
    assert "Boston" in geocode.city_hint("Dorchester", "MA")
    assert "San Diego" in geocode.city_hint("San Ysidro", "CA")
    assert geocode.city_hint("Newark", "NJ") == ["Newark"]


def test_batch_csv_parsing():
    text = (
        '"A1","1 MAIN ST, X, CA, 90001","Match","Exact","1 MAIN ST, X, CA, 90001",'
        '"-118.25,34.05","123","L","06","037","123400","1000"\n'
        '"A2","2 NOPE ST, X, CA, ","No_Match"\n'
    )
    out = geocode.parse_batch_csv(text)
    assert out["A2"] is None
    a1 = out["A1"]
    assert (a1.lat, a1.lon, a1.county_fips, a1.tier) == (34.05, -118.25, "06037", "census_batch")


def test_every_address_is_present_and_nearly_all_resolve(resolved):
    assert sorted(resolved) == [f"A{i:04d}" for i in range(1, 501)]
    unmatched = [a for a, r in resolved.items() if r["geocoder"] == "none"]
    assert unmatched == ["A0295"]  # 'Harvard ST LOT 2A-13': a lot with no house number
    r = resolved["A0295"]
    assert r["city_id"] is None and r["resolution_method"] == "state_only"
    assert r["stack_ids"] == ["MA"]


def test_legal_city_counts_match_the_atlas(resolved):
    counts = {}
    for r in resolved.values():
        counts[r["legal_city"]] = counts.get(r["legal_city"], 0) + 1
    assert counts == {
        "Los Angeles": 80, "San Francisco": 80, "San Diego": 50, "Berkeley": 40,
        "Jersey City": 50, "Hoboken": 40, "Newark": 50, "Boston": 59, "Cambridge": 50,
        None: 1,
    }  # fmt: skip


def test_state_totals_follow_the_data_not_the_geocoder(resolved):
    by_state = {}
    for r in resolved.values():
        by_state[r["state"]] = by_state.get(r["state"], 0) + 1
    assert by_state == {"CA": 250, "NJ": 140, "MA": 110}
    for r in resolved.values():
        if r["city_id"]:
            assert r["city_id"].startswith(r["state"] + "-")


def test_mailing_city_is_not_legal_city(resolved):
    mism = {a: r for a, r in resolved.items() if r["mailing_mismatch"]}
    assert len(mism) == 37
    dorch = resolved["A0118"]  # 18-34 Kingbird Rd, mailed as Dorchester
    assert dorch["postal_city"] == "Dorchester" and dorch["legal_city"] == "Boston"
    assert dorch["mailing_note"]["en"] == "Mailed as Dorchester. Legally inside Boston."
    assert dorch["mailing_note"]["es"].startswith("Enviado como Dorchester")
    ysidro = [r for r in resolved.values() if r["postal_city"] == "San Ysidro"]
    assert len(ysidro) == 1 and ysidro[0]["legal_city"] == "San Diego"
    assert {r["postal_city"] for r in mism.values() if r["state"] == "MA"} <= {
        "Allston", "Brighton", "Dorchester", "East Boston", "Hyde Park", "Jamaica Plain",
        "Mattapan", "Roxbury", "South Boston",
    }  # fmt: skip


def test_suspect_zips_are_dropped_before_geocoding(resolved):
    suspect = [r for r in resolved.values() if r["zip_suspect"]]
    assert len(suspect) == 83
    assert all(r["zip_used"] is None and r["zip"] for r in suspect)
    a3 = resolved["A0003"]  # 876-878 S 14TH ST, Newark, ZIP 11219 (Brooklyn)
    assert a3["zip_suspect"] and a3["legal_city"] == "Newark"


def test_census_cross_check_has_no_disagreements(resolved):
    assert [a for a, r in resolved.items() if r["census_agrees"] is False] == []
    assert sum(r["census_agrees"] is True for r in resolved.values()) > 400


def test_demo_addresses_resolve_to_expected_cities(resolved):
    assert resolved["A0016"]["legal_city"] == "San Francisco"
    assert resolved["A0001"]["legal_city"] == "Los Angeles"
    assert resolved["A0002"]["legal_city"] == "Hoboken"
    assert resolved["A0009"]["legal_city"] == "Cambridge"
    assert resolved["A0019"]["legal_city"] == "San Diego"


def test_geo_report_is_consistent(resolved):
    rep = json.loads((ART / "eval" / "geo_report.json").read_text(encoding="utf-8"))
    assert rep["matched_batch"] + rep["matched_oneline"] + rep["matched_nominatim"] == 499
    assert rep["unmatched"] == 1 and rep["mailing_mismatches"] == 37
    assert rep["census_disagreements"] == 0
