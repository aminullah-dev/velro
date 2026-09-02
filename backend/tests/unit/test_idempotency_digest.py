"""What counts as "the same request" for an idempotency key.

The body was the whole identity once. An accept has no body and names its
offer in the path, so two accepts of two different offers under one key
looked identical -- and the second was answered with the first's ride.
"""

from __future__ import annotations

from ui.api.idempotency import request_digest


class _Body:
    def __init__(self, **fields: object) -> None:
        self._fields = fields

    def model_dump(self) -> dict[str, object]:
        return dict(self._fields)


def test_a_path_parameter_is_part_of_the_request() -> None:
    assert request_digest({"offer_id": "one"}) != request_digest({"offer_id": "two"})


def test_the_body_is_still_part_of_the_request() -> None:
    a = request_digest({"body": _Body(seat_count=1)})
    b = request_digest({"body": _Body(seat_count=2)})
    assert a != b


def test_how_the_request_is_served_is_not_part_of_it() -> None:
    """The key header, the store, the actor: none of them describe the ask."""
    served_one_way = request_digest(
        {"offer_id": "x", "idempotency_key": "k1", "idem": object(), "actor": object()}
    )
    served_another = request_digest({"offer_id": "x", "idempotency_key": "k2"})
    assert served_one_way == served_another


def test_a_query_value_left_at_its_default_still_counts() -> None:
    assert request_digest({"station_id": None}) != request_digest({"station_id": "s"})


def test_the_digest_is_stable() -> None:
    assert request_digest({"offer_id": "x", "body": _Body(a=1, b=2)}) == request_digest(
        {"body": _Body(b=2, a=1), "offer_id": "x"}
    )
