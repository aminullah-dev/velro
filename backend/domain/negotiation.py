"""Agreeing a fare, section 89.

VELRO does not price a journey. Nobody knows how many kilometres separate two
villages in Ghorband, or which part of the road is asphalt and which is dirt
that turns to mud in spring -- so the fare is what a passenger and a driver
agree between them, exactly as it is agreed at the station today.

The passenger names a price. Drivers who will take it offer that number back;
drivers who will not offer their own. The passenger picks one. Nothing here
computes a fare, and nothing overrides what two people settled on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from domain.enums import FareOfferStatus, RideRequestStatus
from shared import error_codes
from shared.errors import ConflictError, ValidationError
from shared.money import Money

# A price is a proposal, not a bid in an auction: an offer far above or below
# what was asked is almost always a typo -- a missing zero, or one too many --
# and refusing it costs a retype where accepting it costs a real argument at
# the roadside.
MAX_MULTIPLE_OF_ASKING = 5
MIN_FRACTION_OF_ASKING = 5      # i.e. not less than a fifth


@dataclass(slots=True)
class FareOffer:
    """One driver's price for one request."""

    id: str
    ride_request_id: str
    driver_id: str
    amount: Money
    status: FareOfferStatus = FareOfferStatus.OFFERED
    note: str | None = None
    created_at: datetime | None = None
    responded_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, FareOfferStatus):
            self.status = FareOfferStatus(self.status)
        if self.amount.amount_minor <= 0:
            raise ValidationError(
                error_codes.FARE_OFFER_AMOUNT_INVALID,
                offer_id=self.id,
                amount_minor=self.amount.amount_minor,
            )

    @property
    def is_open(self) -> bool:
        return self.status is FareOfferStatus.OFFERED

    def accept(self, *, at: datetime) -> None:
        self._require_open(FareOfferStatus.ACCEPTED)
        self.status = FareOfferStatus.ACCEPTED
        self.responded_at = at

    def decline(self, *, at: datetime) -> None:
        self._require_open(FareOfferStatus.DECLINED)
        self.status = FareOfferStatus.DECLINED
        self.responded_at = at

    def withdraw(self, *, at: datetime) -> None:
        self._require_open(FareOfferStatus.WITHDRAWN)
        self.status = FareOfferStatus.WITHDRAWN
        self.responded_at = at

    def _require_open(self, target: FareOfferStatus) -> None:
        if not self.is_open:
            raise ConflictError(
                error_codes.FARE_OFFER_NOT_OPEN,
                offer_id=self.id,
                current=str(self.status),
                requested=str(target),
            )


def assert_offer_allowed(
    *,
    asking: Money,
    offered: Money,
    request_status: RideRequestStatus,
    already_offered: bool,
    driver_is_passenger: bool,
) -> None:
    """Whether a driver may put this price on this request.

    One place, so the app and the API refuse for the same reason -- a driver
    told "too high" by one and "already offered" by the other has learnt
    nothing about what to do next.
    """
    if driver_is_passenger:
        # Bidding on your own request would let one person manufacture a
        # completed trip, and with it a commission record and a rating.
        raise ConflictError(error_codes.FARE_OFFER_SELF)
    if request_status is not RideRequestStatus.OPEN:
        raise ConflictError(
            error_codes.RIDE_REQUEST_NOT_OPEN, current=str(request_status)
        )
    if already_offered:
        # Changing your mind is withdrawing and offering again, so the
        # passenger sees one number per driver rather than a history.
        raise ConflictError(error_codes.FARE_OFFER_ALREADY_MADE)
    if offered.currency != asking.currency:
        raise ValidationError(
            error_codes.CURRENCY_MISMATCH,
            expected=asking.currency,
            received=offered.currency,
        )
    if offered.amount_minor <= 0:
        raise ValidationError(
            error_codes.FARE_OFFER_AMOUNT_INVALID, amount_minor=offered.amount_minor
        )
    if offered.amount_minor > asking.amount_minor * MAX_MULTIPLE_OF_ASKING:
        raise ValidationError(
            error_codes.FARE_OFFER_IMPLAUSIBLE,
            asking_minor=asking.amount_minor,
            offered_minor=offered.amount_minor,
            reason="too_high",
        )
    if offered.amount_minor * MIN_FRACTION_OF_ASKING < asking.amount_minor:
        raise ValidationError(
            error_codes.FARE_OFFER_IMPLAUSIBLE,
            asking_minor=asking.amount_minor,
            offered_minor=offered.amount_minor,
            reason="too_low",
        )
