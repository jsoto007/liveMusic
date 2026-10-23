"""Closing an account.

App Store Review Guideline 5.1.1(v) requires that an app offering account
creation also offer account **deletion** — not deactivation — from inside the
app. This is the domain half of that: what "delete" means for a listings
paper, where some of what an account produced is a public record other people
have already acted on.

The rule we settled on:

* Everything **personal** goes with the account — credentials, tokens, the
  reader's list and interests, follows, blocks, comments, reviews, messages,
  notifications, gig applications, and every band page the account owned. All
  of that is reachable by ``ON DELETE CASCADE`` from ``users.id``, so deleting
  the row does it in one statement inside the transaction.
* A **listing** is not personal data — it is a published fact about a night at
  a venue, and other readers have it on their lists. Those rows survive
  (``events.artist_id`` and ``events.created_by_user_id`` are both
  ``ON DELETE SET NULL``), but anything still in the future is **cancelled**,
  because nobody is left to play it, and the reader's list should say so
  rather than keep advertising a show with no band behind it.
* An **uploaded poster** is the account's own file, so it is stripped from any
  surviving listing and queued for deletion from storage. A poster this app
  attached itself from an openly-licensed source carries ``poster_credit`` and
  is left alone — it was never the account's to take away.

Storage objects are collected *before* the delete (afterwards the rows are
gone) and purged *after* the commit. A failed R2 call must never roll back a
deletion the caller has already been told about; an orphaned object is a
storage cost, an undead account is a compliance failure.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from ..models import (
    Artist,
    AudioSample,
    Event,
    EventStatus,
    MediaUpload,
    User,
    utcnow,
)


def collect_storage_keys(session, user: User) -> list[str]:
    """Every R2 key that belongs to this account, in deletion order.

    Called before the row is deleted — once the cascade has run there is
    nothing left to walk.
    """
    keys: list[str] = []

    if user.avatar_key:
        keys.append(user.avatar_key)

    artist_ids = list(
        session.scalars(select(Artist.id).where(Artist.owner_user_id == user.id))
    )
    if artist_ids:
        keys.extend(
            key
            for key in session.scalars(
                select(Artist.photo_key).where(Artist.id.in_(artist_ids))
            )
            if key
        )
        keys.extend(
            session.scalars(
                select(AudioSample.object_key).where(
                    AudioSample.artist_id.in_(artist_ids)
                )
            )
        )

    # The account's own poster uploads. `poster_credit` marks a stock image
    # this app attached from a Commons source — not this account's file, and
    # possibly shared with other listings, so it is never deleted here.
    keys.extend(
        key
        for key in session.scalars(
            select(Event.poster_key).where(
                Event.created_by_user_id == user.id,
                Event.poster_key.is_not(None),
                Event.poster_credit.is_(None),
            )
        )
        if key
    )

    # Upload tickets that never completed. Their rows cascade away with the
    # account, which would otherwise put the object beyond the sweeper's reach
    # — it works from the PENDING rows.
    keys.extend(
        session.scalars(
            select(MediaUpload.object_key).where(MediaUpload.user_id == user.id)
        )
    )

    # One key can be reached two ways (a completed upload is both a
    # `media_uploads` row and a durable column). Deduplicate, keep order.
    return list(dict.fromkeys(key for key in keys if key))


def delete_account(session, user: User) -> list[str]:
    """Delete ``user`` and everything personal to it.

    Returns the storage keys the caller should purge once the transaction has
    committed. Does not commit — the route owns the transaction boundary.
    """
    keys = collect_storage_keys(session, user)
    now = utcnow()
    user_id: uuid.UUID = user.id

    # Surviving listings: cancel anything still ahead, and drop the account's
    # own poster from all of them.
    upcoming = session.scalars(
        select(Event).where(
            Event.created_by_user_id == user_id,
            Event.status == EventStatus.PUBLISHED,
            Event.starts_at >= now,
        )
    ).all()
    for event in upcoming:
        event.status = EventStatus.CANCELLED
        event.cancelled_at = now

    own_posters = session.scalars(
        select(Event).where(
            Event.created_by_user_id == user_id,
            Event.poster_key.is_not(None),
            Event.poster_credit.is_(None),
        )
    ).all()
    for event in own_posters:
        event.poster_key = None

    # Flush the listing edits before the cascade fires, so the UPDATE lands
    # while `created_by_user_id` still points at this account.
    session.flush()

    session.delete(user)
    return keys
