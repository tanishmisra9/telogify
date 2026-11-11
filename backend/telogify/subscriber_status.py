"""The one definition of Subscriber.status and its allowed transitions.

`verify_token_hash` is part of the same machine: a hash present means `pending` with a live
token, and confirming nulls it (single use). `bounced` and `complained` are terminal: nothing
reactivates them, so a hard-bounced or spam-complained address can never be mailed again.
"""

from enum import StrEnum


class SubscriberStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    UNSUBSCRIBED = "unsubscribed"
    BOUNCED = "bounced"
    COMPLAINED = "complained"


S = SubscriberStatus

# from -> states it may move to. Same-state moves are listed where a repeat is legitimate
# (pending re-issues its token, confirmed resubscribe is a no-op).
ALLOWED: dict[SubscriberStatus, frozenset[SubscriberStatus]] = {
    S.PENDING: frozenset({S.PENDING, S.CONFIRMED, S.UNSUBSCRIBED, S.BOUNCED, S.COMPLAINED}),
    S.CONFIRMED: frozenset({S.CONFIRMED, S.UNSUBSCRIBED, S.BOUNCED, S.COMPLAINED}),
    S.UNSUBSCRIBED: frozenset({S.PENDING, S.CONFIRMED, S.BOUNCED, S.COMPLAINED}),
    S.BOUNCED: frozenset(),
    S.COMPLAINED: frozenset(),
}

STATUS_VALUES = tuple(s.value for s in SubscriberStatus)


def can_transition(current: str, to: SubscriberStatus) -> bool:
    try:
        return to in ALLOWED[SubscriberStatus(current)]
    except ValueError:  # a status outside the enum has no allowed moves
        return False
