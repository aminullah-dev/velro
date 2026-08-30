"""Reading a network off an Afghan mobile number.

Ghorband is MTN and Etisalat, so those two decide whether anybody can sign in
at all. The rest are here because a valley is not a country and VELRO is meant
to reach other provinces.
"""

from __future__ import annotations

import pytest

from domain.afghan_networks import Network, likely_network


class TestTheNetworksGhorbandActuallyUses:
    @pytest.mark.parametrize("number", ["+93762345678", "+93772345678"])
    def test_mtn(self, number: str) -> None:
        assert likely_network(number) is Network.MTN

    @pytest.mark.parametrize("number", ["+93732345678", "+93782345678"])
    def test_etisalat(self, number: str) -> None:
        assert likely_network(number) is Network.ETISALAT


class TestTheRest:
    @pytest.mark.parametrize(
        ("number", "network"),
        [
            ("+93702345678", Network.AWCC),
            ("+93712345678", Network.AWCC),
            ("+93722345678", Network.ROSHAN),
            ("+93792345678", Network.ROSHAN),
            ("+93742345678", Network.SALAAM),
            ("+93752345678", Network.SALAAM),
        ],
    )
    def test_each_allocation(self, number: str, network: Network) -> None:
        assert likely_network(number) is network

    def test_every_mobile_prefix_is_accounted_for(self) -> None:
        """70 through 79 with no gaps.

        A gap is a person who cannot sign in and whose failure is unexplained,
        because an unmapped prefix looks exactly like a foreign number.
        """
        unmapped = [
            f"7{digit}" for digit in range(10) if likely_network(f"+937{digit}2345678") is None
        ]
        assert not unmapped, f"no network for prefix: {unmapped}"


class TestWhatIsNotAnAfghanMobile:
    @pytest.mark.parametrize(
        "number",
        [
            "+13438677631",  # Canadian, used for testing
            "+93202345678",  # Kabul landline
            "+9376234567",  # eight digits
            "+937623456789",  # ten digits
            "+9376234567a",
            "",
            "+93",
        ],
    )
    def test_it_returns_nothing_rather_than_guessing(self, number: str) -> None:
        assert likely_network(number) is None

    def test_the_leading_plus_is_optional(self) -> None:
        assert likely_network("93762345678") is Network.MTN
