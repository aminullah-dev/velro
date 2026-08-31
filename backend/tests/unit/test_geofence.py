"""The fence itself, held up to the light.

The rule is one function with four exits, and each exit is a policy decision
somebody argued for: exempt numbers skip everything so the tester's handset
works from another continent; a non-positive radius is the operator's off
switch; missing coordinates are refused rather than waved through, because a
fence with a "GPS off" gate is a fence with a gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

import pytest

from shared import error_codes
from shared.errors import ValidationError
from ui.api.geofence import DEFAULT_RADIUS_M, SETTING_RADIUS_M, assert_inside

KABUL_ISH = (Decimal("35.125"), Decimal("68.77"))
HERAT_ISH = (Decimal("34.35"), Decimal("62.20"))


@dataclass
class FakeGeo:
    stations: list = field(default_factory=list)
    calls: list = field(default_factory=list)

    def nearby_stations(self, latitude, longitude, *, radius_m, limit):
        self.calls.append((latitude, longitude, radius_m, limit))
        return self.stations


@dataclass
class FakeAppSettings:
    radius: int = DEFAULT_RADIUS_M

    def get_int(self, key, default):
        assert key == SETTING_RADIUS_M
        return self.radius


def check(*, geo=None, radius=DEFAULT_RADIUS_M, exempt=(), phone="+93700000000",
          lat=KABUL_ISH[0], lon=KABUL_ISH[1]):
    assert_inside(
        geo=geo if geo is not None else FakeGeo(stations=[object()]),
        app_settings=FakeAppSettings(radius=radius),
        exempt_phones=exempt,
        phone=phone,
        latitude=lat,
        longitude=lon,
    )


class TestOneNumber:
    def test_the_module_default_and_the_seeded_default_are_the_same_number(self):
        # Two homes for one figure: the guard's fallback and the seeded
        # settings row the admin edits. If they drift, which fence is real
        # depends on whether seeding ran -- pin them together.
        from infrastructure.services.settings import DEFAULTS
        assert DEFAULTS[SETTING_RADIUS_M] == DEFAULT_RADIUS_M


class TestInside:
    def test_a_station_within_reach_admits_the_caller(self):
        check(geo=FakeGeo(stations=[object()]))

    def test_the_operators_radius_is_the_one_the_query_gets(self):
        geo = FakeGeo(stations=[object()])
        check(geo=geo, radius=5_000)
        assert geo.calls == [(KABUL_ISH[0], KABUL_ISH[1], 5_000, 1)]


class TestOutside:
    def test_no_station_in_reach_is_refused_with_the_coordinates(self):
        with pytest.raises(ValidationError) as caught:
            check(geo=FakeGeo(stations=[]), lat=HERAT_ISH[0], lon=HERAT_ISH[1])
        assert caught.value.code == error_codes.GEOFENCE_OUTSIDE
        # The refusal records where the caller claimed to be -- the operator's
        # only evidence when someone insists the fence is wrong.
        assert caught.value.context == {"latitude": "34.35", "longitude": "62.20"}

    @pytest.mark.parametrize("lat,lon", [(None, None), (KABUL_ISH[0], None), (None, KABUL_ISH[1])])
    def test_missing_coordinates_are_refused_not_waved_through(self, lat, lon):
        geo = FakeGeo(stations=[object()])
        with pytest.raises(ValidationError) as caught:
            check(geo=geo, lat=lat, lon=lon)
        assert caught.value.code == error_codes.GEOFENCE_OUTSIDE
        assert caught.value.context == {"reason": "location_required"}
        assert geo.calls == []


class TestExits:
    def test_an_exempt_phone_passes_from_anywhere_without_a_lookup(self):
        geo = FakeGeo(stations=[])
        check(geo=geo, exempt=("+93793817977",), phone="+93793817977",
              lat=None, lon=None)
        assert geo.calls == []

    def test_a_non_positive_radius_is_the_off_switch(self):
        geo = FakeGeo(stations=[])
        check(geo=geo, radius=0, lat=None, lon=None)
        check(geo=geo, radius=-1, lat=None, lon=None)
        assert geo.calls == []
