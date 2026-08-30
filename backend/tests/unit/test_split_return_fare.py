"""Two legs, two prices, one total.

A round trip out of Ghorband is one car and one driver, but the fare is
argued as two numbers -- so much to Kabul, so much back -- and the passenger
wants to see both. The platform stores both.

What it must not do is *check* both separately. Every rule about a price is a
rule about the total, because the total is what changes hands: the plausibility
guards, the currency, the commission, the receipt. Argued apart, checked
together.
"""

from __future__ import annotations

import pytest

from domain.enums import RideRequestStatus
from domain.negotiation import (
    MAX_MULTIPLE_OF_ASKING,
    assert_offer_allowed,
    total_fare,
)
from shared import error_codes
from shared.errors import ValidationError
from shared.money import Money

AFN = "AFN"


def afn(amount: int) -> Money:
    return Money(amount, AFN)


class TestTheTotal:
    def test_a_one_way_journey_is_its_own_total(self) -> None:
        assert total_fare(afn(30000), None) == afn(30000)

    def test_a_round_trip_adds_the_legs(self) -> None:
        assert total_fare(afn(30000), afn(25000)) == afn(55000)

    def test_the_currency_carries_across(self) -> None:
        assert total_fare(afn(100), afn(50)).currency == AFN

    def test_two_currencies_are_refused_rather_than_added(self) -> None:
        """Adding minor units across currencies produces a number that looks
        like money and is not."""
        with pytest.raises(ValidationError) as raised:
            total_fare(afn(30000), Money(25000, "USD"))
        assert raised.value.code == error_codes.CURRENCY_MISMATCH

    @pytest.mark.parametrize("amount", [0, -1, -30000])
    def test_a_return_leg_must_be_a_real_price(self, amount: int) -> None:
        """Null means no return. Zero would be a return agreed at nothing,
        which is a different claim about the world."""
        with pytest.raises(ValidationError) as raised:
            total_fare(afn(30000), afn(amount))
        assert raised.value.code == error_codes.FARE_OFFER_AMOUNT_INVALID


def allow(asking: Money, offered: Money) -> None:
    assert_offer_allowed(
        asking=asking,
        offered=offered,
        request_status=RideRequestStatus.OPEN,
        already_offered=False,
        driver_is_passenger=False,
    )


class TestPlausibilityAppliesToTheWholeJourney:
    """The reason the legs are added before they are judged.

    Asked 300 out and 250 back -- 550 in total. A guard that looked at the
    outbound alone would let a driver answer "300 out, 20000 back" and call it
    a fair reply to the outbound number.
    """

    ASKING = total_fare(afn(30000), afn(25000))    # 550 afghani

    def test_a_matching_pair_is_allowed(self) -> None:
        allow(self.ASKING, total_fare(afn(30000), afn(25000)))

    def test_a_reasonable_counter_is_allowed(self) -> None:
        allow(self.ASKING, total_fare(afn(35000), afn(30000)))

    def test_an_absurd_return_leg_is_caught_by_the_total(self) -> None:
        absurd = afn(25000 * MAX_MULTIPLE_OF_ASKING * 10)
        with pytest.raises(ValidationError) as raised:
            allow(self.ASKING, total_fare(afn(30000), absurd))
        assert raised.value.code == error_codes.FARE_OFFER_IMPLAUSIBLE

    def test_a_sensible_outbound_does_not_excuse_it(self) -> None:
        """The outbound on its own is exactly what was asked. Judged alone it
        would sail through; judged as part of the journey it does not."""
        absurd = afn(25000 * MAX_MULTIPLE_OF_ASKING * 10)
        offered = total_fare(afn(30000), absurd)
        assert offered.amount_minor > self.ASKING.amount_minor * MAX_MULTIPLE_OF_ASKING
        with pytest.raises(ValidationError):
            allow(self.ASKING, offered)

    def test_a_derisory_total_is_still_caught(self) -> None:
        with pytest.raises(ValidationError) as raised:
            allow(self.ASKING, total_fare(afn(1000), afn(1000)))
        assert raised.value.code == error_codes.FARE_OFFER_IMPLAUSIBLE
