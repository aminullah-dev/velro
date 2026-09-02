"""The service-area fence.

Station-to-station was the founding decision and the map was set aside -- but
the map's one irreplaceable job comes back in a different uniform here. The
threat is not navigation, it is mischief: an ask rings every online driver's
phone, and a person in some other province with a spare SIM can ring them all
night for sport. A driver who gets three fake asks stops trusting the sound,
and the sound is the product.

So a mutation that summons drivers must come from inside the world the product
serves. The fence is not a polygon that someone has to maintain: it is the
geography already in the database. Every station carries coordinates, and
"within reach of a known station" IS Kabul, Parwan and Ghorband -- and grows by
itself the day a new province's stations are seeded.

The check trusts the handset's coordinates, and a determined liar can send
false ones. That is accepted: the adversary here is casual, a real SIM per
account is already the expensive part, and the rate limits stand behind this.
The fence prices out boredom, not espionage.
"""

from __future__ import annotations

from decimal import Decimal

from shared import error_codes
from shared.errors import ValidationError

#: Operator-tunable through app_settings; this is the fallback. Villages sit
#: off the road their station is on, so the radius is generous -- wide enough
#: for a valley home, far too narrow for the next province.
SETTING_RADIUS_M = "geofence.radius_m"
DEFAULT_RADIUS_M = 20_000


def assert_inside(
    *,
    geo,
    app_settings,
    exempt_phones: tuple[str, ...],
    phone: str,
    latitude: Decimal | None,
    longitude: Decimal | None,
    is_mock: bool = False,
) -> None:
    """Refuse a summons from outside the service area.

    Exempt numbers skip everything, coordinates included: the tester's handset
    lives on another continent and still has to exercise the whole flow. A
    radius of zero or less turns the fence off for everyone -- the operator's
    switch, in app_settings where operational levers live.
    """
    if phone in exempt_phones:
        return

    radius = app_settings.get_int(SETTING_RADIUS_M, DEFAULT_RADIUS_M)
    if radius <= 0:
        return

    if is_mock:
        # Android itself brands a fix produced by a mock-location app, and an
        # unmodified client passes the brand along. This catches the person
        # who installed Fake GPS from an app store -- the realistic bulk of
        # coordinate liars -- and openly cannot catch a patched client or a
        # raw API call, which is why the SIM cost and the suspend switch stand
        # behind it. Same sentence to the caller as any other refusal: telling
        # a cheater precisely which check caught him is a tutorial.
        raise ValidationError(
            error_codes.GEOFENCE_OUTSIDE, reason="mock_location"
        )

    if latitude is None or longitude is None:
        # No fix at all: the one refusal that is spoken plainly. This is not
        # the cheater's exit -- a person sending nothing learns nothing from
        # being told so -- it is the passenger in Kabul who tapped "don't
        # allow" on one unexplained dialog, or whose phone has location off,
        # or who is under a tin roof and the fix timed out. Handing her the
        # same vague "outside the service area" sentence told her VELRO does
        # not serve her, with no way to fix it. Her own code carries the
        # fix: allow location and try again.
        raise ValidationError(error_codes.GEOFENCE_LOCATION_REQUIRED)

    if not geo.nearby_stations(latitude, longitude, radius_m=radius, limit=1):
        raise ValidationError(
            error_codes.GEOFENCE_OUTSIDE,
            latitude=str(latitude),
            longitude=str(longitude),
        )
