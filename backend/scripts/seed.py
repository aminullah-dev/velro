"""Development seed.

Creates a database a developer can actually book a trip in: the four Ghorband
districts, sample villages and stations, the real destination set, generated
routes, fares, schedules, an approved driver with a vehicle, and today's trips.

IMPORTANT -- the village list here is a SAMPLE, not the master data. The
authoritative list of Ghorband villages has not yet been provided; when it is,
it is loaded through the importer (``scripts/import_villages.py``), which does
duplicate detection and keeps alternative names as their own records. Seeding
and importing are deliberately different paths: this one is disposable, that
one is not.

Idempotent: safe to run repeatedly.
"""

from __future__ import annotations

import sys
from datetime import date, time, timedelta
from decimal import Decimal

from sqlalchemy import select

from application.use_cases.generate_routes import GenerateRoutes, GenerateRoutesCommand
from domain.driver import normalise_plate
from domain.enums import (
    DestinationKind,
    DocumentStatus,
    DriverApprovalStatus,
    DriverAvailability,
    GeoStatus,
    RideKind,
    RouteStatus,
    RouteType,
    TripStatus,
    VehicleStatus,
)
from domain.identity import (
    ADMIN,
    ALL_ROLES,
    DISPATCHER,
    DRIVER,
    FINANCE_MANAGER,
    OPERATIONS_MANAGER,
    PASSENGER,
    STAFF_ROLES,
    SUPER_ADMIN,
    SUPPORT_AGENT,
)
from domain.text import comparison_key
from infrastructure.db.models.geography import (
    DestinationRow,
    DistrictRow,
    ProvinceRow,
    RegionRow,
    StationRow,
    VillageAliasRow,
    VillageRow,
)
from infrastructure.db.models.identity import PermissionRow, RolePermissionRow, RoleRow, UserRow
from infrastructure.db.models.ops import SettingRow
from infrastructure.db.models.routing import (
    FareRuleRow,
    RouteScheduleRow,
    RouteTemplateRow,
    VehicleTypeRow,
)
from infrastructure.db.models.supply import (
    DriverDocumentRow,
    DriverRow,
    VehicleDocumentRow,
    VehicleRow,
)
from infrastructure.db.models.trips import TripRow, TripSeatRow, TripStopRow
from infrastructure.db.repositories.geography import GeographyRepository
from infrastructure.db.repositories.identity import UserRepository
from infrastructure.db.repositories.routing import (
    RouteRepository,
    RouteStopRepository,
    RouteTemplateRepository,
)
from infrastructure.db.session import build_engine, build_session_factory
from infrastructure.services.audit import SqlAuditLog
from infrastructure.services.numbers import SqlNumberAllocator
from infrastructure.services.settings import DEFAULTS, wrap
from shared import config
from shared.clock import SystemClock
from shared.ids import new_id

CLOCK = SystemClock()

# -- master data ---------------------------------------------------------

PROVINCE = ("AF-PAR", "پروان")
REGION = ("GRB", "غوربند")

DISTRICTS = [
    ("GRB-SYG", "سیاه‌گرد", "Siahgird", Decimal("35.1200"), Decimal("68.7800")),
    ("GRB-SHW", "شینواری", "Shinwari", Decimal("35.0600"), Decimal("68.8900")),
    ("GRB-SPA", "سرخ‌پارسا", "Surkh Parsa", Decimal("34.9500"), Decimal("68.2500")),
    ("GRB-SHA", "شیخ‌علی", "Sheikh Ali", Decimal("34.9000"), Decimal("68.4500")),
]

# (district_code, name, [aliases], lat, lon)
# Sample only -- see the module docstring.
VILLAGES = [
    ("GRB-SYG", "خیشکی", [], Decimal("35.1250"), Decimal("68.7700")),
    ("GRB-SYG", "صدوار", ["سبزوار"], Decimal("35.1310"), Decimal("68.7550")),
    ("GRB-SYG", "دره‌قول‌خول", ["خسرویه"], Decimal("35.1400"), Decimal("68.7420")),
    ("GRB-SYG", "قلعه نو", [], Decimal("35.1180"), Decimal("68.7910")),
    ("GRB-SHW", "پل متک", [], Decimal("35.0650"), Decimal("68.8850")),
    ("GRB-SHW", "ده نو", [], Decimal("35.0710"), Decimal("68.8760")),
    ("GRB-SPA", "بازار سرخ‌پارسا", [], Decimal("34.9520"), Decimal("68.2470")),
    ("GRB-SPA", "کج", [], Decimal("34.9610"), Decimal("68.2310")),
    ("GRB-SHA", "بازار شیخ‌علی", [], Decimal("34.9020"), Decimal("68.4530")),
    ("GRB-SHA", "ترکمن", [], Decimal("34.9110"), Decimal("68.4400")),
]

# External destinations. Kabul is a group with two children (section 16).
EXTERNAL = [
    ("EXT-CHK", "چاریکار", None, 10, Decimal("35.0128"), Decimal("69.1711")),
    ("EXT-QRB", "قره‌باغ", None, 20, Decimal("34.8330"), Decimal("69.1170")),
    ("EXT-KBL", "کابل", None, 30, Decimal("34.5553"), Decimal("69.2075")),
    ("EXT-KBL-KHM", "خیرخانه مینه", "EXT-KBL", 31, Decimal("34.5700"), Decimal("69.1600")),
    ("EXT-KBL-JAD", "جاده", "EXT-KBL", 32, Decimal("34.5150"), Decimal("69.1750")),
]

# The way back.
#
# Every route in this file ran out of Ghorband, so the app could sell a seat
# from a village to Kabul and had no way to sell the seat home. That is not
# half the product missing -- it is more than half, because the journey people
# actually make is out and back, and the return is the leg they are stranded
# on: standing in Khairkhana at dusk with no booking.
#
# It needs no schema change and no new screen. A district carries a province,
# a station hangs off a village, and the four Ghorband district centres are
# already destinations -- so Kabul is simply another origin, and the booking
# flow that asks district → village → station → destination works unchanged.
# What was missing was the data.
#
# Both Kabul stations are called "ایستگاه غوربند" -- the Ghorband station.
#
# Named for where the cars go, not for where they stand, which is how these
# yards are actually known: a passenger in Kabul asks for the Ghorband station
# and everyone knows the one they mean. Naming them after their own
# neighbourhood -- "ایستگاه خیرخانه" -- is what an outsider would guess and is
# not what anybody calls them. The neighbourhood is already the district above
# it in the picker, so it is not lost by being left out of the name.
#
# (province_code, province_name, district_code, district_name, alt, lat, lon,
#  village_name, station_name)
RETURN_ORIGINS = [
    (
        "AF-KAB", "کابل", "KBL-KHM", "خیرخانه مینه", "Khair Khana",
        Decimal("34.5700"), Decimal("69.1600"),
        "خیرخانه مینه", "ایستگاه غوربند",
    ),
    (
        "AF-KAB", "کابل", "KBL-JAD", "جاده", "Jada",
        Decimal("34.5150"), Decimal("69.1750"),
        "جاده", "ایستگاه غوربند",
    ),
]

VEHICLE_TYPES = [
    ("SEDAN", "vehicle_type.sedan", 4, 10),
    ("SUV", "vehicle_type.suv", 6, 20),
    ("VAN", "vehicle_type.van", 10, 30),
    ("HIACE", "vehicle_type.hiace", 14, 40),
    ("BUS", "vehicle_type.bus", 30, 50),
    ("OTHER", "vehicle_type.other", 4, 60),
]

PERMISSIONS = [
    ("trip.view", "permission.trip_view"),
    ("trip.manage", "permission.trip_manage"),
    ("trip.assign_driver", "permission.trip_assign_driver"),
    ("booking.view", "permission.booking_view"),
    ("booking.manage", "permission.booking_manage"),
    ("driver.view", "permission.driver_view"),
    ("driver.approve", "permission.driver_approve"),
    ("driver.suspend", "permission.driver_suspend"),
    ("vehicle.manage", "permission.vehicle_manage"),
    ("location.manage", "permission.location_manage"),
    ("route.manage", "permission.route_manage"),
    ("pricing.manage", "permission.pricing_manage"),
    ("finance.view", "permission.finance_view"),
    ("settlement.manage", "permission.settlement_manage"),
    ("support.manage", "permission.support_manage"),
    ("settings.manage", "permission.settings_manage"),
    ("audit.view", "permission.audit_view"),
]

ROLE_PERMISSIONS: dict[str, list[str]] = {
    SUPER_ADMIN: [code for code, _ in PERMISSIONS],
    ADMIN: [code for code, _ in PERMISSIONS if code != "settings.manage"],
    OPERATIONS_MANAGER: [
        "trip.view", "trip.manage", "trip.assign_driver", "booking.view",
        "booking.manage", "driver.view", "driver.approve", "vehicle.manage",
        "location.manage", "route.manage",
    ],
    DISPATCHER: [
        "trip.view", "trip.manage", "trip.assign_driver", "booking.view", "driver.view",
    ],
    FINANCE_MANAGER: ["finance.view", "settlement.manage", "pricing.manage", "booking.view"],
    SUPPORT_AGENT: ["support.manage", "trip.view", "booking.view", "driver.view"],
    DRIVER: [],
    PASSENGER: [],
}


def _get_or_create(session, model, *, match: dict, defaults: dict):
    stmt = select(model)
    for column, value in match.items():
        stmt = stmt.where(getattr(model, column) == value)
    row = session.scalars(stmt).first()
    if row is not None:
        return row, False
    row = model(id=new_id(), **match, **defaults)
    session.add(row)
    session.flush()
    return row, True


def seed(session) -> None:
    now = CLOCK.now()
    created: dict[str, int] = {}

    def note(key: str, made: bool) -> None:
        if made:
            created[key] = created.get(key, 0) + 1

    # -- settings -------------------------------------------------------
    for key, value in DEFAULTS.items():
        _, made = _get_or_create(
            session, SettingRow,
            match={"key": key},
            defaults={
                "value": wrap(value),
                "value_type": type(value).__name__,
                "description_key": f"setting.{key.replace('.', '_')}",
            },
        )
        note("settings", made)

    # -- roles and permissions ------------------------------------------
    permissions: dict[str, PermissionRow] = {}
    for code, description_key in PERMISSIONS:
        row, made = _get_or_create(
            session, PermissionRow,
            match={"code": code}, defaults={"description_key": description_key},
        )
        permissions[code] = row
        note("permissions", made)

    roles: dict[str, RoleRow] = {}
    for code in ALL_ROLES:
        row, made = _get_or_create(
            session, RoleRow,
            match={"code": code},
            defaults={
                "name_key": f"role.{code.lower()}",
                "is_staff": code in STAFF_ROLES,
            },
        )
        roles[code] = row
        note("roles", made)

    for role_code, permission_codes in ROLE_PERMISSIONS.items():
        for permission_code in permission_codes:
            _, made = _get_or_create(
                session, RolePermissionRow,
                match={
                    "role_id": roles[role_code].id,
                    "permission_id": permissions[permission_code].id,
                },
                defaults={},
            )
            note("role_permissions", made)

    # -- vehicle types --------------------------------------------------
    for code, name_key, capacity, order in VEHICLE_TYPES:
        _, made = _get_or_create(
            session, VehicleTypeRow,
            match={"code": code},
            defaults={
                "name_key": name_key,
                "default_seat_capacity": capacity,
                "sort_order": order,
            },
        )
        note("vehicle_types", made)

    # -- geography ------------------------------------------------------
    province, made = _get_or_create(
        session, ProvinceRow,
        match={"code": PROVINCE[0]},
        defaults={"name": PROVINCE[1], "country_code": "AF", "status": GeoStatus.ACTIVE.value},
    )
    note("provinces", made)

    region, made = _get_or_create(
        session, RegionRow,
        match={"code": REGION[0]},
        defaults={"name": REGION[1], "province_id": province.id},
    )
    note("regions", made)

    districts: dict[str, DistrictRow] = {}
    for code, name, alternative, lat, lon in DISTRICTS:
        row, made = _get_or_create(
            session, DistrictRow,
            match={"code": code},
            defaults={
                "name": name, "alternative_name": alternative,
                "province_id": province.id, "region_id": region.id,
                "latitude": lat, "longitude": lon,
            },
        )
        districts[code] = row
        note("districts", made)

    villages: dict[str, VillageRow] = {}
    counters: dict[str, int] = {}
    for district_code, name, aliases, lat, lon in VILLAGES:
        counters[district_code] = counters.get(district_code, 0) + 1
        code = f"{district_code}-{counters[district_code]:03d}"
        row, made = _get_or_create(
            session, VillageRow,
            match={"code": code},
            defaults={
                "name": name, "name_key": comparison_key(name),
                "district_id": districts[district_code].id,
                "latitude": lat, "longitude": lon,
                "source_note": "development seed - not master data",
            },
        )
        villages[code] = row
        note("villages", made)

        # Alternative names stay their own records; they are never folded into
        # the village name (section 7).
        for alias in aliases:
            _, alias_made = _get_or_create(
                session, VillageAliasRow,
                match={"village_id": row.id, "name_key": comparison_key(alias)},
                defaults={"name": alias, "note": "seed"},
            )
            note("village_aliases", alias_made)

    stations: dict[str, StationRow] = {}
    for code, village in villages.items():
        station_code = f"{code}-S1"
        row, made = _get_or_create(
            session, StationRow,
            match={"code": station_code},
            defaults={
                "name": f"ایستگاه {village.name}",
                "name_key": comparison_key(f"ایستگاه {village.name}"),
                "village_id": village.id, "district_id": village.district_id,
                "latitude": village.latitude, "longitude": village.longitude,
                "is_primary": True,
            },
        )
        stations[station_code] = row
        note("stations", made)

    # Internal destinations: the four district centres. The coordinates the
    # DISTRICTS table already carried now travel with the destination too --
    # the driver's map needs a point to draw the journey's far end at, and
    # "the district" is a polygon nobody stored. The centre is close enough
    # for a line on a map; the road itself is what the eye follows.
    destinations: dict[str, DestinationRow] = {}
    for order, (code, name, _alt, lat, lon) in enumerate(DISTRICTS):
        row, made = _get_or_create(
            session, DestinationRow,
            match={"code": f"INT-{code}"},
            defaults={
                "name": name, "name_key": comparison_key(name),
                "kind": DestinationKind.INTERNAL.value,
                "district_id": districts[code].id,
                "sort_order": order,
                "latitude": lat, "longitude": lon,
            },
        )
        destinations[f"INT-{code}"] = row
        note("destinations", made)

    for code, name, parent_code, order, lat, lon in EXTERNAL:
        parent = destinations.get(parent_code) if parent_code else None
        row, made = _get_or_create(
            session, DestinationRow,
            match={"code": code},
            defaults={
                "name": name, "name_key": comparison_key(name),
                "kind": DestinationKind.EXTERNAL.value,
                "parent_id": parent.id if parent else None,
                "sort_order": order, "latitude": lat, "longitude": lon,
            },
        )
        destinations[code] = row
        note("destinations", made)

    # -- the way back ---------------------------------------------------
    #
    # Kabul as an origin, so a passenger standing in Khairkhana can buy a seat
    # home. Its own province and districts rather than a special case: the
    # geography is already province → district → village → station, and
    # nothing in it was ever Ghorband-specific except the rows.
    return_districts: dict[str, DistrictRow] = {}
    for (
        prov_code, prov_name, dist_code, dist_name, dist_alt, lat, lon,
        village_name, station_name,
    ) in RETURN_ORIGINS:
        prov, made = _get_or_create(
            session, ProvinceRow,
            match={"code": prov_code}, defaults={"name": prov_name},
        )
        note("provinces", made)

        district, made = _get_or_create(
            session, DistrictRow,
            match={"code": dist_code},
            defaults={
                "name": dist_name, "alternative_name": dist_alt,
                "province_id": prov.id, "region_id": None,
                "latitude": lat, "longitude": lon,
            },
        )
        return_districts[dist_code] = district
        note("districts", made)

        village, made = _get_or_create(
            session, VillageRow,
            match={"code": f"{dist_code}-001"},
            defaults={
                "name": village_name, "name_key": comparison_key(village_name),
                "district_id": district.id,
                "latitude": lat, "longitude": lon,
                "source_note": "development seed - not master data",
            },
        )
        note("villages", made)

        _, made = _get_or_create(
            session, StationRow,
            match={"code": f"{dist_code}-001-S1"},
            defaults={
                "name": station_name, "name_key": comparison_key(station_name),
                "village_id": village.id, "district_id": district.id,
                "latitude": lat, "longitude": lon, "is_primary": True,
            },
        )
        note("stations", made)

    session.flush()

    # -- route templates ------------------------------------------------
    # One template per (district, destination). Section 12: the routes for every
    # village in the district are generated from these, never written by hand.
    templates: list[RouteTemplateRow] = []
    plan = [
        ("CHK", "EXT-CHK", RouteType.INTERCITY, 45_000, 75, 50_000, []),
        ("QRB", "EXT-QRB", RouteType.INTERCITY, 70_000, 105, 70_000, ["EXT-CHK"]),
        ("KBL-KHM", "EXT-KBL-KHM", RouteType.CITY, 110_000, 165, 120_000, ["EXT-CHK"]),
        ("KBL-JAD", "EXT-KBL-JAD", RouteType.CITY, 118_000, 180, 130_000, ["EXT-CHK"]),
    ]
    # Kabul → Ghorband, the mirror of the plan above.
    #
    # The fare is the outbound fare, not a discount and not a premium: it is
    # the same road and the same hours, and a driver who charges more for the
    # empty-looking direction is the thing this product exists to replace.
    #
    # Charikar is a waypoint on the way out and a waypoint on the way back, so
    # somebody travelling only that far can be picked up in either direction.
    for dist_code, origin_district in return_districts.items():
        for grb_code, grb in districts.items():
            code = f"T-{dist_code}-{grb_code}"
            row, made = _get_or_create(
                session, RouteTemplateRow,
                match={"code": code},
                defaults={
                    "name": f"{origin_district.name} → {grb.name}",
                    "origin_scope": "DISTRICT",
                    "origin_ref_id": origin_district.id,
                    "destination_id": destinations[f"INT-{grb_code}"].id,
                    "route_type": RouteType.CITY.value,
                    "vehicle_type_code": "SEDAN",
                    "default_seat_capacity": 4,
                    "intermediate_destination_ids": [destinations["EXT-CHK"].id],
                    "distance_m": 110_000,
                    "duration_minutes": 165,
                    "base_fare_minor": 120_000,
                    "base_fare_currency": "AFN",
                    "status": RouteStatus.ACTIVE.value,
                },
            )
            templates.append(row)
            note("route_templates", made)

    for district_code, district in districts.items():
        for suffix, destination_code, route_type, distance, minutes, fare, waypoints in plan:
            code = f"T-{district_code}-{suffix}"
            row, made = _get_or_create(
                session, RouteTemplateRow,
                match={"code": code},
                defaults={
                    "name": f"{district.name} → {destinations[destination_code].name}",
                    "origin_scope": "DISTRICT",
                    "origin_ref_id": district.id,
                    "destination_id": destinations[destination_code].id,
                    "route_type": route_type.value,
                    "vehicle_type_code": "SEDAN",
                    "default_seat_capacity": 4,
                    "intermediate_destination_ids": [
                        destinations[w].id for w in waypoints
                    ],
                    "distance_m": distance,
                    "duration_minutes": minutes,
                    "base_fare_minor": fare,
                    "base_fare_currency": "AFN",
                    "status": RouteStatus.ACTIVE.value,
                },
            )
            templates.append(row)
            note("route_templates", made)

        # District-to-district, so a passenger can travel within Ghorband.
        for other_code, other in districts.items():
            if other_code == district_code:
                continue
            code = f"T-{district_code}-{other_code}"
            row, made = _get_or_create(
                session, RouteTemplateRow,
                match={"code": code},
                defaults={
                    "name": f"{district.name} → {other.name}",
                    "origin_scope": "DISTRICT",
                    "origin_ref_id": district.id,
                    "destination_id": destinations[f"INT-{other_code}"].id,
                    "route_type": RouteType.DISTRICT_TO_DISTRICT.value,
                    "vehicle_type_code": "SEDAN",
                    "default_seat_capacity": 4,
                    "intermediate_destination_ids": [],
                    "distance_m": 25_000,
                    "duration_minutes": 45,
                    "base_fare_minor": 20_000,
                    "base_fare_currency": "AFN",
                    "status": RouteStatus.ACTIVE.value,
                },
            )
            templates.append(row)
            note("route_templates", made)

    session.flush()

    # -- generate the concrete routes -----------------------------------
    generator = GenerateRoutes(
        templates=RouteTemplateRepository(session),
        routes=RouteRepository(session),
        route_stops=RouteStopRepository(session),
        geography=GeographyRepository(session),
        audit=SqlAuditLog(session, CLOCK),
        clock=CLOCK,
        new_id=new_id,
    )
    generated = generator.execute(GenerateRoutesCommand())
    session.flush()

    # -- fares and schedules --------------------------------------------
    route_repo = RouteRepository(session)
    templates_by_id = {t.id: t for t in templates}
    fares = schedules = 0

    for route in session.scalars(select(route_repo.model).where(
        route_repo.model.deleted_at.is_(None)
    )).all():
        template = templates_by_id.get(route.template_id)
        if template is None:
            continue
        stops = route_repo.stops_of(route.id)
        if len(stops) < 2:
            continue
        first, last = stops[0].sequence, stops[-1].sequence

        for ride_kind, multiplier in ((RideKind.SHARED, 1), (RideKind.PRIVATE, 3)):
            _, made = _get_or_create(
                session, FareRuleRow,
                match={
                    "route_id": route.id,
                    "ride_kind": ride_kind.value,
                    "from_sequence": first,
                    "to_sequence": last,
                },
                defaults={
                    "vehicle_type_code": None,
                    "amount_minor": (template.base_fare_minor or 50_000) * multiplier,
                    "amount_currency": "AFN",
                    "valid_from": date(now.year, 1, 1),
                    "notes": "seed",
                },
            )
            fares += int(made)

        for hour in (7, 9, 13, 16):
            _, made = _get_or_create(
                session, RouteScheduleRow,
                match={
                    "route_id": route.id,
                    "departure_time": time(hour, 0),
                    "vehicle_type_code": "SEDAN",
                    "active_from": date(now.year, 1, 1),
                },
                defaults={
                    # Saturday through Thursday: Friday is the weekend here.
                    "days_of_week": "YYYYYYN",
                    "seat_capacity": 4,
                    "ride_kind": RideKind.SHARED.value,
                },
            )
            schedules += int(made)

    session.flush()

    # -- people ----------------------------------------------------------
    users = UserRepository(session)

    def person(phone: str, name: str, role: str) -> UserRow:
        row = users.find_by_phone(phone)
        if row is None:
            row = users.create(id=new_id(), phone=phone, locale="fa-AF", full_name=name)
            session.flush()
        users.grant_role(row.id, role)
        return row

    admin_user = person("+93700000001", "مدیر ولرو", SUPER_ADMIN)
    person("+93700000002", "دسپچر", DISPATCHER)
    passenger_user = person("+93700000010", "احمد", PASSENGER)
    driver_user = person("+93700000020", "محمد", DRIVER)
    driver_user_2 = person("+93700000021", "نجیب", DRIVER)
    session.flush()

    drivers_made = 0
    for user, plate, capacity in (
        (driver_user, "PRW-1234", 4),
        (driver_user_2, "PRW-5678", 6),
    ):
        driver, made = _get_or_create(
            session, DriverRow,
            match={"user_id": user.id},
            defaults={
                "approval_status": DriverApprovalStatus.APPROVED.value,
                "availability": DriverAvailability.OFFLINE.value,
                "approved_at": now,
                "approved_by": admin_user.id,
                "home_district_id": districts["GRB-SYG"].id,
            },
        )
        drivers_made += int(made)

        for document_type in DEFAULTS["driver.required_documents"]:
            _get_or_create(
                session, DriverDocumentRow,
                match={"driver_id": driver.id, "document_type_code": document_type},
                defaults={
                    "file_key": f"seed/{driver.id}/{document_type.lower()}.jpg",
                    "status": DocumentStatus.VERIFIED.value,
                    "verified_by": admin_user.id,
                    "verified_at": now,
                },
            )
        vehicle, _ = _get_or_create(
            session, VehicleRow,
            match={"plate_number": plate},
            defaults={
                "driver_id": driver.id,
                # Through the domain rule, so the seed and the application agree
                # on what makes two plates the same vehicle.
                "plate_key": normalise_plate(plate),
                "vehicle_type_code": "SEDAN" if capacity == 4 else "SUV",
                "seat_capacity": capacity,
                "brand": "Toyota",
                "model": "Corolla" if capacity == 4 else "Land Cruiser",
                "year": 2012,
                "colour": "سفید",
                "status": VehicleStatus.ACTIVE.value,
            },
        )
        session.flush()

        # The car's own papers. An ACTIVE vehicle with no جواز سیر is a state
        # the application will not produce and will not let work, so a seed
        # that created one would hand every developer a fleet that cannot go
        # online.
        for document_type in DEFAULTS["vehicle.required_documents"]:
            _get_or_create(
                session, VehicleDocumentRow,
                match={"vehicle_id": vehicle.id, "document_type_code": document_type},
                defaults={
                    "file_key": f"seed/{vehicle.id}/{document_type.lower()}.jpg",
                    "status": DocumentStatus.VERIFIED.value,
                    "verified_by": admin_user.id,
                    "verified_at": now,
                },
            )
    session.flush()

    # -- today's trips ---------------------------------------------------
    numbers = SqlNumberAllocator(session)
    trips_made = 0
    khishki_station = stations["GRB-SYG-001-S1"]
    charikar = destinations["EXT-CHK"]

    origin_routes = list(
        session.scalars(
            select(route_repo.model).where(
                route_repo.model.origin_station_id == khishki_station.id,
                route_repo.model.destination_id == charikar.id,
                route_repo.model.deleted_at.is_(None),
            )
        ).all()
    )
    for route in origin_routes:
        stops = route_repo.stops_of(route.id)
        for offset_hours in (2, 5, 8):
            departure = (now + timedelta(hours=offset_hours)).replace(
                minute=0, second=0, microsecond=0
            )
            existing = session.scalars(
                select(TripRow).where(
                    TripRow.route_id == route.id,
                    TripRow.scheduled_departure_at == departure,
                    TripRow.deleted_at.is_(None),
                )
            ).first()
            if existing is not None:
                continue

            trip = TripRow(
                id=new_id(),
                number=numbers.allocate("trip", year=now.year),
                route_id=route.id,
                ride_kind=RideKind.SHARED.value,
                seat_capacity=4,
                scheduled_departure_at=departure,
                status=TripStatus.SCHEDULED.value,
                origin_station_id=route.origin_station_id,
                destination_id=route.destination_id,
            )
            session.add(trip)
            session.flush()

            for stop in stops:
                session.add(
                    TripStopRow(
                        id=new_id(), trip_id=trip.id, sequence=stop.sequence,
                        station_id=stop.station_id, destination_id=stop.destination_id,
                        planned_at=departure + timedelta(minutes=30 * stop.sequence),
                    )
                )
            # Seats are rows, so capacity cannot be exceeded by construction.
            for seat_number in range(1, trip.seat_capacity + 1):
                session.add(
                    TripSeatRow(id=new_id(), trip_id=trip.id, seat_number=seat_number)
                )
            trips_made += 1

    session.commit()

    print("seeded:")
    for key in sorted(created):
        print(f"  {key:20} {created[key]}")
    print(f"  {'routes generated':20} {generated.routes_created} "
          f"(updated {generated.routes_updated}, stations {generated.stations_covered})")
    print(f"  {'fare rules':20} {fares}")
    print(f"  {'schedules':20} {schedules}")
    print(f"  {'drivers':20} {drivers_made}")
    print(f"  {'trips':20} {trips_made}")
    print()
    print("sign in with (OTP is echoed in development):")
    print(f"  passenger  {passenger_user.phone}")
    print(f"  driver     {driver_user.phone}")
    print(f"  admin      {admin_user.phone}")


def main() -> int:
    cfg = config.load()
    engine = build_engine(cfg.database_url)
    factory = build_session_factory(engine)
    with factory() as session:
        seed(session)
    return 0


if __name__ == "__main__":
    sys.exit(main())
