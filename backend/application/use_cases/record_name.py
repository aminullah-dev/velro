"""Learning what a person is called.

One use case, four callers. The name is asked for in several places -- when a
passenger applies to drive, when a driver goes on shift, when an operator
approves him against a tazkira, and on the person's own account -- and every one
of them has to make the same two decisions: what counts as a name, and whether
this caller may replace one that is already there.

Keeping those decisions here rather than in four routers is what stops them
drifting apart, which for a field this widely read would mean the offer card and
the audit log disagreeing about who somebody is.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.enums import ActorRole
from domain.person_names import clean
from shared.clock import Clock


@dataclass(frozen=True)
class RecordNameCommand:
    user_id: str
    actor_id: str
    raw_name: str | None
    actor_role: ActorRole = ActorRole.PASSENGER
    allow_overwrite: bool = False
    """Whether this caller may replace a name that is already recorded.

    False for the opportunistic asks -- the apply form, the go-online sheet.
    Those appear in front of whoever is holding the handset, and a handset here
    is often shared between a household: a daughter borrowing her father's phone
    to book a ride must not be able to rename the man whose face is on every
    offer card in the valley.

    True for the two callers who are entitled to it: a person editing their own
    account, and an operator reading a driver's tazkira at approval. The second
    matters more than it looks -- it is the only way a name that came through as
    junk, or as somebody else's, can ever be corrected.
    """


class RecordName:
    """Records a name, or declines to, and says nothing either way.

    Never raises. Every caller reaches this on the way to doing something else
    -- registering, going online, being approved -- and none of them should fail
    because of the name field. A name that cannot be recorded is simply not
    recorded, and the product renders "no name given", which it does honestly.
    """

    def __init__(self, *, users, audit, clock: Clock) -> None:
        self._users = users
        self._audit = audit
        self._clock = clock

    def execute(self, cmd: RecordNameCommand) -> str | None:
        """Returns the name now on the record, which may be the one already there."""
        user = self._users.get(cmd.user_id)
        before = user.full_name

        if cmd.raw_name is None:
            # The caller did not mention the name -- an operator approving a
            # driver on the documents alone, a request body without the field.
            # Saying nothing is not the same as clearing it, and clean() maps
            # both to None, so the distinction has to be made before cleaning.
            # Without this, approving a driver erased the name he gave when he
            # applied.
            return before

        name = clean(cmd.raw_name)

        if name is None:
            # Nothing usable was typed. On a caller allowed to overwrite this is
            # a deliberate erasure -- somebody taking their name back off a
            # shared phone -- and on one that is not, it is a person tapping
            # past an optional field, which must leave what is there alone.
            if not cmd.allow_overwrite or before is None:
                return before
        elif before is not None and not cmd.allow_overwrite:
            return before

        if name == before:
            return before

        user.full_name = name
        user.updated_by = cmd.actor_id
        user.updated_at = self._clock.now()

        self._audit.write(
            "user.name_recorded",
            actor_id=cmd.actor_id,
            actor_role=cmd.actor_role,
            entity_type="user",
            entity_id=user.id,
            before={"full_name": before},
            after={"full_name": name},
        )
        return name
