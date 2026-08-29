"""Money.

House rule: integer minor units plus an ISO-4217 code. ``float`` is forbidden in
any code path that touches money -- a lint rule enforces it. Arithmetic between
different currencies raises; there is no implicit conversion, ever.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# Minor-unit exponent per ISO-4217. AFN has 2, like most.
MINOR_DIGITS: dict[str, int] = {"AFN": 2, "USD": 2, "EUR": 2, "PKR": 2}

DEFAULT_CURRENCY = "AFN"


class CurrencyMismatchError(Exception):
    """Raised when two different currencies meet in an arithmetic operation."""


@dataclass(frozen=True, slots=True)
class Money:
    amount_minor: int
    currency: str = DEFAULT_CURRENCY

    def __post_init__(self) -> None:
        if not isinstance(self.amount_minor, int) or isinstance(self.amount_minor, bool):
            raise TypeError("amount_minor must be an int; floats are banned in money paths")
        if self.currency not in MINOR_DIGITS:
            raise ValueError(f"unknown currency {self.currency!r}")

    # -- construction -----------------------------------------------------

    @classmethod
    def zero(cls, currency: str = DEFAULT_CURRENCY) -> Money:
        return cls(0, currency)

    @classmethod
    def of_major(cls, major: str | int | Decimal, currency: str = DEFAULT_CURRENCY) -> Money:
        """Parse a human-entered major amount ("500", "12.50") without ever touching float."""
        if isinstance(major, float):
            raise TypeError("float is banned in money paths; pass a str, int or Decimal")
        exponent = MINOR_DIGITS[currency]
        scaled = (Decimal(major) * (10**exponent)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        return cls(int(scaled), currency)

    # -- arithmetic -------------------------------------------------------

    def _same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(f"{self.currency} and {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(self.amount_minor + other.amount_minor, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(self.amount_minor - other.amount_minor, self.currency)

    def __mul__(self, factor: int) -> Money:
        if not isinstance(factor, int) or isinstance(factor, bool):
            raise TypeError("money may only be multiplied by an int")
        return Money(self.amount_minor * factor, self.currency)

    __rmul__ = __mul__

    def __neg__(self) -> Money:
        return Money(-self.amount_minor, self.currency)

    def __lt__(self, other: Money) -> bool:
        self._same_currency(other)
        return self.amount_minor < other.amount_minor

    def __le__(self, other: Money) -> bool:
        self._same_currency(other)
        return self.amount_minor <= other.amount_minor

    # -- splitting --------------------------------------------------------

    def percentage(self, basis_points: int) -> Money:
        """A share of this amount, in basis points (1000 bp = 10%).

        Rounded ROUND_HALF_UP, stated explicitly because a commission split that
        rounds differently in two places loses money one afghani at a time.
        """
        if not isinstance(basis_points, int) or isinstance(basis_points, bool):
            raise TypeError("basis_points must be an int")
        if not 0 <= basis_points <= 10_000:
            raise ValueError("basis_points must be between 0 and 10000")
        share = (Decimal(self.amount_minor) * basis_points / 10_000).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
        return Money(int(share), self.currency)

    def split_off(self, basis_points: int) -> tuple[Money, Money]:
        """Split into (share, remainder). The two always sum back to self exactly."""
        share = self.percentage(basis_points)
        return share, self - share

    # -- presentation -----------------------------------------------------

    @property
    def is_zero(self) -> bool:
        return self.amount_minor == 0

    @property
    def is_negative(self) -> bool:
        return self.amount_minor < 0

    def as_major(self) -> Decimal:
        """For formatters only. Never for arithmetic and never for storage."""
        return Decimal(self.amount_minor) / (10 ** MINOR_DIGITS[self.currency])

    def __repr__(self) -> str:
        return f"Money({self.amount_minor}, {self.currency!r})"
