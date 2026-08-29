"""The Python domain against the shared specification.

``docs/domain/lifecycles.json`` is the single source of truth for every
lifecycle in VELRO. The Kotlin ``:domain`` module is tested against the same
file, so a rule changed in one language and not the other fails a build instead
of becoming a discrepancy a passenger runs into.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from domain.booking import CANCELLABLE_STATUSES
from domain.enums import (
    BookingStatus,
    SeatStatus,
    SettlementStatus,
    TicketStatus,
    TripStatus,
)
from domain.fare import CommissionSplit
from domain.lifecycles import (
    BOOKABLE_TRIP_STATUSES,
    BOOKING_LIFECYCLE,
    SETTLEMENT_LIFECYCLE,
    TICKET_LIFECYCLE,
    TRIP_LIFECYCLE,
    TRIP_TO_BOOKING_STATUS,
)
from shared.money import Money

SPEC = json.loads(
    (Path(__file__).resolve().parents[3] / "docs" / "domain" / "lifecycles.json").read_text(
        encoding="utf-8"
    )
)


# The machines the parametrised test below covers. Kept beside it so the guard
# can compare the two.
COVERED = {"trip", "booking", "settlement", "ticket"}


def test_every_machine_in_the_specification_is_actually_tested() -> None:
    """The list above is hand-maintained, so it can fall behind the file.

    A machine added to lifecycles.json and not to that list is not a failing
    test -- it is no test at all, which is worse, because the suite goes green
    and nobody learns the Kotlin mirror was never checked either.
    """
    machines = {
        key for key, value in SPEC.items()
        if not key.startswith("$") and isinstance(value, dict) and "transitions" in value
    }
    assert machines == COVERED, (
        "lifecycles.json declares "
        + ", ".join(sorted(machines - COVERED) or ["nothing"])
        + " which no test covers; and this test names "
        + ", ".join(sorted(COVERED - machines) or ["nothing"])
        + " which the specification does not declare"
    )


@pytest.mark.parametrize(
    ("name", "machine", "enum"),
    [
        ("trip", TRIP_LIFECYCLE, TripStatus),
        ("booking", BOOKING_LIFECYCLE, BookingStatus),
        ("settlement", SETTLEMENT_LIFECYCLE, SettlementStatus),
        ("ticket", TICKET_LIFECYCLE, TicketStatus),
    ],
)
def test_transition_tables_match_the_specification(name: str, machine, enum) -> None:
    declared = SPEC[name]["transitions"]

    assert {str(s) for s in enum} == set(declared), (
        f"{name}: the states in code and in the specification differ"
    )
    for state, allowed in declared.items():
        actual = {str(s) for s in machine.allowed_from(enum(state))}
        assert actual == set(allowed), (
            f"{name}.{state}: code allows {sorted(actual)}, spec allows {sorted(allowed)}"
        )


def test_bookable_trip_statuses_match_the_specification() -> None:
    assert {str(s) for s in BOOKABLE_TRIP_STATUSES} == set(SPEC["trip"]["bookable_in"])


def test_cancellable_booking_statuses_match_the_specification() -> None:
    assert {str(s) for s in CANCELLABLE_STATUSES} == set(SPEC["booking"]["cancellable_in"])


def test_the_trip_to_booking_cascade_matches_the_specification() -> None:
    declared = {k: v for k, v in SPEC["trip_to_booking"].items() if not k.startswith("$")}
    actual = {str(k): str(v) for k, v in TRIP_TO_BOOKING_STATUS.items()}
    assert actual == declared


def test_seat_statuses_match_the_specification() -> None:
    assert {str(s) for s in SeatStatus} == set(SPEC["seat"]["statuses"])


@pytest.mark.parametrize("case", SPEC["commission"]["cases"])
def test_commission_cases_match_the_specification(case: dict[str, int]) -> None:
    """The same table is applied in Kotlin. Rounding that differs by one afghani
    between the app and the server is a support ticket a month later."""
    split = CommissionSplit.of(Money(case["gross_minor"]), case["rate_basis_points"])
    assert split.platform.amount_minor == case["platform_minor"]
    assert split.driver.amount_minor == case["driver_minor"]
    assert split.platform.amount_minor + split.driver.amount_minor == case["gross_minor"]


def test_error_codes_named_by_the_specification_are_registered() -> None:
    from shared.error_codes import is_registered

    for section in ("trip", "booking", "settlement"):
        assert is_registered(SPEC[section]["error_code"])
