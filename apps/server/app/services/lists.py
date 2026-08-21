"""Named event lists: the shelves.

Both caps here gate a limited resource, so both are decided under a row lock
(CLAUDE.md §3.1): list creation locks the owner's user row, item addition
locks the list row. ``with_for_update`` is a no-op on SQLite and a real
``SELECT ... FOR UPDATE`` on Postgres, which is where the race lives.
"""

import sqlalchemy as sa

from ..models import EventList, EventListItem, EventStatus, User

MAX_LISTS_PER_USER = 24
MAX_ITEMS_PER_LIST = 200


class ListRefused(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def get_owned_list(session, owner, list_id) -> EventList | None:
    """The list, if it is the caller's. Missing and foreign are both None —
    the route turns either into the same 404."""
    if list_id is None:
        return None
    event_list = session.get(EventList, list_id)
    if event_list is None or event_list.owner_user_id != owner.id:
        return None
    return event_list


def get_visible_list(session, viewer, list_id) -> EventList | None:
    """The list, if the viewer may see it: public, or their own."""
    event_list = session.get(EventList, list_id)
    if event_list is None:
        return None
    if event_list.is_public:
        return event_list
    if viewer is not None and event_list.owner_user_id == viewer.id:
        return event_list
    return None


def create_list(
    session, owner: User, *, name: str, description: str | None, is_public: bool
) -> EventList:
    """Create under the owner-row lock so the cap survives concurrency."""
    session.get(User, owner.id, with_for_update=True)
    held = int(
        session.query(sa.func.count(EventList.id))
        .filter(EventList.owner_user_id == owner.id)
        .scalar()
        or 0
    )
    if held >= MAX_LISTS_PER_USER:
        raise ListRefused(
            "LIMIT_REACHED",
            f"You can keep at most {MAX_LISTS_PER_USER} lists. Retire one to start another.",
        )
    if _name_taken(session, owner.id, name):
        raise ListRefused("NAME_TAKEN", "You already have a list with that name.")

    event_list = EventList(
        owner_user_id=owner.id,
        name=name,
        description=description,
        is_public=is_public,
    )
    session.add(event_list)
    session.flush()
    return event_list


def _name_taken(session, owner_id, name: str, *, excluding_id=None) -> bool:
    query = session.query(EventList.id).filter(
        EventList.owner_user_id == owner_id,
        sa.func.lower(EventList.name) == name.lower(),
    )
    if excluding_id is not None:
        query = query.filter(EventList.id != excluding_id)
    return query.first() is not None


def rename_guard(session, event_list: EventList, new_name: str) -> None:
    if _name_taken(
        session, event_list.owner_user_id, new_name, excluding_id=event_list.id
    ):
        raise ListRefused("NAME_TAKEN", "You already have a list with that name.")


def add_item(session, event_list: EventList, event, *, note: str | None) -> EventListItem:
    """Idempotent add, capped under the list-row lock.

    A draft never goes on a shelf — it is not public, and a private thing
    reachable through someone's public list would be a leak, not a feature.
    """
    if event.status is EventStatus.DRAFT:
        raise ListRefused("NOT_FOUND", "That show could not be found.", status=404)

    session.get(EventList, event_list.id, with_for_update=True)

    existing = session.get(
        EventListItem, {"list_id": event_list.id, "event_id": event.id}
    )
    if existing is not None:
        # Re-adding is a note update, not an error — the tap meant "keep this".
        if note is not None:
            existing.note = note
        return existing

    held = int(
        session.query(sa.func.count(EventListItem.event_id))
        .filter(EventListItem.list_id == event_list.id)
        .scalar()
        or 0
    )
    if held >= MAX_ITEMS_PER_LIST:
        raise ListRefused(
            "LIMIT_REACHED", f"A list holds at most {MAX_ITEMS_PER_LIST} shows."
        )

    item = EventListItem(list_id=event_list.id, event_id=event.id, note=note)
    session.add(item)
    return item


def item_counts(session, list_ids) -> dict:
    if not list_ids:
        return {}
    rows = (
        session.query(EventListItem.list_id, sa.func.count(EventListItem.event_id))
        .filter(EventListItem.list_id.in_(list_ids))
        .group_by(EventListItem.list_id)
        .all()
    )
    return {list_id: int(count) for list_id, count in rows}
