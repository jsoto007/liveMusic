# The correspondence desk and the photo desk

**Date:** 2026-08-17
**Branch:** `feat/real-map-and-pictures` (uncommitted)
**Scope:** full stack — follows `reports/social-and-gigs/2026-08-17-social-layer-and-gigs.md`

## 1. What shipped

**In-app messaging, scoped to the hiring flow.** One conversation per pair of
readers (ordered-pair unique constraint; a lost first-message race adopts the
winner's thread via a savepoint). Threads open from three anchors, each
resolved server-side:

- a band's page — "Message the band" reaches the band's *current* owner;
- a gig application — poster and applicant reach each other, and **nobody
  else can use an application id as an address book** (strangers get the
  same 404 a bad id would);
- a plain `@handle` from a profile.

The anchor that opened a thread becomes its subject line ("About Bloodroot
Choir", "About “House band wanted”") and survives the subject's deletion via
SET NULL. Blocks bar new mail in both directions (403 `BLOCKED`, matching
follows/comments); delivered history stays readable, like a mailbox. Read
state is a per-side stamp; the masthead (web) and Bill header (mobile) badge
the count of threads holding unseen mail. Rate limits: 30 opens/hour, 120
sends/hour. Endpoints: `POST /conversations`, `GET /me/conversations`,
`GET /me/conversations/unread-count`, `GET|POST
/conversations/<id>[/messages|/read]` — every one scoped to the two parties,
404 to all others.

UI on both clients renders threads as ruled correspondence (no filled chat
bubbles — stroke only, per the design system): web `/messages` +
`/messages/:id`, mobile `Messages` + `Thread` screens, "Message" buttons on
band pages, profiles, and both sides of a gig's applications.

**The photo desk (image moderation).** Every completed image upload — avatar,
band photo, event poster — files an `image_reviews` row in the same
transaction that attaches it. Editors work the queue at `/desk` (web;
admin-only, the API 404s everyone else):

- **Approve** — the editorial record notes it and the queue moves on.
- **Remove** — the object is detached from *whoever still wears it* (matched
  by object key, so a photo the owner already replaced doesn't clobber the
  replacement), deleted from R2, and the uploader is notified ("An editor
  removed one of your photos" — the editor stays unnamed; the desk speaks as
  the paper). The review row survives as the audit line.

Resolution is claimed with a conditional UPDATE (same shape as upload-ticket
completion), so two editors racing produce one verdict and one notification.

This is **post-moderation**: photos go live on upload and the desk takes them
down, complemented by the existing user-report flow. Automated *pre*-screening
for pornographic content would require an external classifier (AWS
Rekognition, Cloudflare's moderation API, or similar); `photo_desk.queue_image`
is the marked seam for it — score there, auto-resolve the obvious, leave the
queue for the borderline.

## 2. Schema

Revision `e4a8b3c96d15` (on `c9d2e51a7b43`): `conversations` (ordered pair
unique, per-side read stamps, `last_message_at`), `messages`,
`image_reviews`; `notification_kind` gains `image_removed`. Verified against
Postgres 16 via the parity test on a local throwaway instance; the test's
enum-drop list extended with `image_review_status`.

## 3. Review notes

Hardened during the pass, before commit:

1. **Mailbox last-line lookup** originally ordered every message of the
   page's threads; a long thread made the mailbox read its whole history.
   Now `append_message` stamps the message and `last_message_at` from one
   clock read, and the mailbox joins on the (conversation, timestamp) pair —
   one indexed query, no history scan.
2. **Photo-desk resolve** was check-then-write; now an atomic claim
   (`UPDATE … WHERE status='pending'`), refusing the second editor with
   `ALREADY_RESOLVED`.
3. Conversation-creation race handled with a savepoint (`begin_nested`), not
   a full-session rollback.

Verified invariants: thread privacy (party-scoped queries, 404 otherwise,
tested); application-anchor privacy (tested); block enforcement at open and
at send (tested); self-messaging refused; exactly-one anchor validation;
desk admin surface invisible to readers (401/404, tested); remove path
strips key + deletes object + notifies (tested); stale-key removal leaves a
replacement photo alone (tested); audio uploads never queue (tested).

Accepted behaviors: messaging any public handle is allowed (profiles are
public; the hiring anchors are conveniences, not the only door); message
bodies flatten control characters like every other text field; no
per-message notifications (the mailbox badge is the signal — the inbox stays
for social events).

## 4. Evidence

- Server: **355 passed, 1 skipped** (parity separately green on Postgres 16),
  ruff clean; 21 new tests covering the house standard + the adversarial set
  above.
- `pnpm typecheck` 4/4, `pnpm lint` 3/3, `pnpm test` fully green (web,
  mobile incl. new screens' static checks, shared, server).
- **Walked live in the browser**: Ben → Bloodroot Choir → "Message the band"
  → thread ("About Bloodroot Choir"); Ada's masthead "Messages (1)" → reply;
  Ada's avatar upload → editor's `/desk` photo queue → Remove → avatar
  stripped, uploader notified.
- **Walked live on the iOS simulator**: Ben's Bill header shows the Mail
  badge (1); the Messages screen lists the thread with the unread ring and
  Ada's reply preview; the Thread screen renders the same correspondence the
  web wrote. Mobile UI otherwise verified statically (typecheck/lint/vitest).

## 5. Follow-ups

- Automated NSFW classification at the `queue_image` seam (external service
  + credentials decision).
- Push/email notification for new messages (in-app badge only today).
- Editors currently moderate from the web desk only; a mobile desk was
  deliberately skipped.
