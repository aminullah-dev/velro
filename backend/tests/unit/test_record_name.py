"""Who may write a person's name, and over what.

One handset is one account here -- `users.phone` is unique and a family shares a
phone -- so this is not a formality. Whoever the account is called is the name on
every offer card the driver of that household sends, on the receipts, and in the
emergency SMS. The rule about overwriting is the only thing standing between a
daughter borrowing the phone to book a ride and her given name being broadcast
to the valley under her father's car.

No database: the repository and the audit writer are stand-ins, because the
decision under test is a rule and not a query.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from application.use_cases.record_name import RecordName, RecordNameCommand
from domain.enums import ActorRole


@dataclass
class FakeUser:
    id: str = "01900000-0000-7000-8000-00000000000a"
    full_name: str | None = None
    updated_by: str | None = None
    updated_at: datetime | None = None


class FakeUsers:
    def __init__(self, user: FakeUser) -> None:
        self.user = user

    def get(self, id: str) -> FakeUser:
        return self.user


@dataclass
class FakeAudit:
    entries: list[dict[str, Any]] = field(default_factory=list)

    def write(self, action: str, **fields: Any) -> None:
        self.entries.append({"action": action, **fields})


class FrozenClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 30, 6, 0, tzinfo=UTC)


def record(
    stored: str | None,
    typed: str | None,
    *,
    allow_overwrite: bool = False,
    actor_id: str = "01900000-0000-7000-8000-00000000000a",
) -> tuple[str | None, FakeUser, FakeAudit]:
    user = FakeUser(full_name=stored)
    audit = FakeAudit()
    use_case = RecordName(users=FakeUsers(user), audit=audit, clock=FrozenClock())
    result = use_case.execute(
        RecordNameCommand(
            user_id=user.id,
            actor_id=actor_id,
            raw_name=typed,
            allow_overwrite=allow_overwrite,
        )
    )
    return result, user, audit


class TestFillingABlank:
    def test_a_first_name_is_recorded(self) -> None:
        result, user, _ = record(None, "محمد نعیم")
        assert result == "محمد نعیم"
        assert user.full_name == "محمد نعیم"

    def test_it_is_cleaned_on_the_way_in(self) -> None:
        _, user, _ = record(None, "  محمد   نعیم  ")
        assert user.full_name == "محمد نعیم"

    def test_junk_leaves_the_blank_blank(self) -> None:
        """He typed one letter to get past the field. That is not his name, and
        storing it would break every fallback that keys on the name being
        absent -- starting with the driver's number in the emergency SMS."""
        result, user, audit = record(None, "G")
        assert result is None
        assert user.full_name is None
        assert audit.entries == []

    def test_recording_is_audited_with_both_sides(self) -> None:
        _, _, audit = record(None, "احمد")
        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry["action"] == "user.name_recorded"
        assert entry["before"] == {"full_name": None}
        assert entry["after"] == {"full_name": "احمد"}


class TestNotOverwriting:
    """The opportunistic asks: the apply form, the go-online sheet.

    These appear in front of whoever is holding the phone, which is not
    reliably the person the account belongs to.
    """

    def test_an_existing_name_is_left_alone(self) -> None:
        result, user, audit = record("غلام سخی", "زرغونه")
        assert result == "غلام سخی"
        assert user.full_name == "غلام سخی"
        assert audit.entries == [], "and nothing was written"

    def test_an_empty_field_cannot_erase_a_name(self) -> None:
        """Tapping past an optional field is not an instruction to forget who
        somebody is."""
        result, user, _ = record("غلام سخی", "")
        assert result == "غلام سخی"
        assert user.full_name == "غلام سخی"

    def test_it_still_fills_a_blank(self) -> None:
        result, _, _ = record(None, "غلام سخی")
        assert result == "غلام سخی"


class TestOverwriting:
    """The two callers entitled to it: the person themselves, and an operator
    holding the tazkira at approval."""

    def test_a_name_can_be_replaced(self) -> None:
        result, user, audit = record("غلام سخی", "غلام سخی نیازی", allow_overwrite=True)
        assert result == "غلام سخی نیازی"
        assert user.full_name == "غلام سخی نیازی"
        assert audit.entries[0]["before"] == {"full_name": "غلام سخی"}

    def test_junk_can_be_corrected_by_someone_who_may_overwrite(self) -> None:
        """The repair path for a name that came through as a single letter.

        clean() already refuses to store "G", but a name can be wrong without
        being junk -- somebody else's, or a nickname on a shared phone. The
        operator at approval is reading a tazkira, and this is the only place
        in the product where that reading can be applied.
        """
        result, _, _ = record("غلم", "غلام سخی", allow_overwrite=True)
        assert result == "غلام سخی"

    def test_a_name_can_be_taken_back(self) -> None:
        """Somebody removing their name from a handset they are handing on.

        Only an overwriting caller can do this, so the account screen and the
        operator can, and a drive-by prompt cannot.
        """
        result, user, audit = record("زرغونه", "", allow_overwrite=True)
        assert result is None
        assert user.full_name is None
        assert audit.entries[0]["after"] == {"full_name": None}

    def test_junk_also_erases_when_overwriting_is_allowed(self) -> None:
        result, user, _ = record("زرغونه", "..", allow_overwrite=True)
        assert result is None
        assert user.full_name is None


class TestNoWorkWhenNothingChanged:
    @pytest.mark.parametrize("allow_overwrite", [True, False])
    def test_resubmitting_the_same_name_writes_nothing(self, allow_overwrite: bool) -> None:
        """Every caller reaches this on the way to doing something else, so the
        same name arrives over and over. An audit log with one entry per shift
        start is an audit log nobody reads."""
        _, user, audit = record("احمد", "احمد", allow_overwrite=allow_overwrite)
        assert audit.entries == []
        assert user.updated_by is None, "and the row was not touched"

    def test_no_name_over_no_name_writes_nothing(self) -> None:
        _, _, audit = record(None, None, allow_overwrite=True)
        assert audit.entries == []


class TestSayingNothingIsNotErasing:
    """None and "" are different instructions, and clean() maps both to None.

    A real bug, caught by an end-to-end test: an operator approving a driver on
    the strength of his documents alone posts no name field, which arrives as
    None -- and that erased the name he had given when he applied. Approving
    somebody is not an instruction to forget who they are.
    """

    def test_an_absent_field_leaves_a_name_alone(self) -> None:
        result, user, audit = record("گل احمد", None, allow_overwrite=True)
        assert result == "گل احمد"
        assert user.full_name == "گل احمد"
        assert audit.entries == []

    def test_an_empty_field_still_erases(self) -> None:
        """The difference this rests on: somebody submitted the field, empty."""
        result, user, _ = record("گل احمد", "", allow_overwrite=True)
        assert result is None
        assert user.full_name is None


def test_the_actor_is_recorded_not_the_subject() -> None:
    """An operator naming a driver must appear as the operator.

    Otherwise the audit log says the driver named himself, and the one question
    it exists to answer -- which person did this -- is answered wrongly.
    """
    operator = "01900000-0000-7000-8000-0000000000ff"
    _, user, audit = record(None, "احمد", actor_id=operator)
    assert audit.entries[0]["actor_id"] == operator
    assert user.updated_by == operator
    assert audit.entries[0]["entity_id"] == user.id


def test_the_clock_is_injected_not_read() -> None:
    _, user, _ = record(None, "احمد")
    assert user.updated_at == datetime(2026, 8, 30, 6, 0, tzinfo=UTC)


def test_the_role_travels_to_the_audit_entry() -> None:
    user = FakeUser()
    audit = FakeAudit()
    RecordName(users=FakeUsers(user), audit=audit, clock=FrozenClock()).execute(
        RecordNameCommand(
            user_id=user.id,
            actor_id="01900000-0000-7000-8000-0000000000ff",
            raw_name="احمد",
            actor_role=ActorRole.ADMIN,
        )
    )
    assert audit.entries[0]["actor_role"] is ActorRole.ADMIN
