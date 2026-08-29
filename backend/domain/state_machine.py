"""A transition table with teeth.

Every lifecycle in VELRO is declared as an explicit table rather than scattered
``if`` statements, so that an illegal transition is a typed error at the one
place that performs it instead of a silent write discovered a week later.

The same tables are mirrored in the Kotlin ``:domain`` module and driven from
the shared specification in ``docs/domain/``; divergence surfaces as a failing
test rather than a field bug.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Generic, TypeVar

from shared.errors import ConflictError

S = TypeVar("S", bound=StrEnum)


class StateMachine(Generic[S]):
    def __init__(
        self,
        transitions: dict[S, frozenset[S]],
        *,
        conflict_code: str,
        entity: str,
    ) -> None:
        self._transitions = transitions
        self._conflict_code = conflict_code
        self._entity = entity

    @property
    def terminal_states(self) -> frozenset[S]:
        return frozenset(state for state, nexts in self._transitions.items() if not nexts)

    def is_terminal(self, state: S) -> bool:
        return not self._transitions[state]

    def can(self, current: S, target: S) -> bool:
        return target in self._transitions.get(current, frozenset())

    def allowed_from(self, current: S) -> frozenset[S]:
        return self._transitions.get(current, frozenset())

    def path(self, current: S, target: S) -> list[S] | None:
        """The shortest declared route from one state to another.

        Used when something that follows another entity's lifecycle has missed
        an intermediate step: a booking sitting at CONFIRMED whose trip has
        already reached ARRIVED_AT_PICKUP must pass through DRIVER_ASSIGNED
        rather than being stranded or teleported.

        Returns None when no legal route exists.
        """
        if current == target:
            return []
        seen = {current}
        frontier: list[tuple[S, list[S]]] = [(current, [])]
        while frontier:
            state, route = frontier.pop(0)
            for nxt in sorted(self._transitions.get(state, frozenset()), key=str):
                if nxt in seen:
                    continue
                extended = [*route, nxt]
                if nxt == target:
                    return extended
                seen.add(nxt)
                frontier.append((nxt, extended))
        return None

    def check(self, current: S, target: S, **context: object) -> None:
        """Raise unless the transition is declared. Callers mutate only after this returns."""
        if not self.can(current, target):
            raise ConflictError(
                self._conflict_code,
                entity=self._entity,
                current=str(current),
                requested=str(target),
                allowed=sorted(str(s) for s in self.allowed_from(current)),
                **context,
            )
