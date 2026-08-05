# 0001 — Media uploads go directly to R2, with a presigned POST

- **Status:** superseded — see "Update" below
- **Date:** 2026-08-03

## Context

Bands attach audio samples (up to 20 MB) to their profile and posters to their
listings. The obvious implementation — `POST /api/v1/samples` with a multipart
body, server streams it to storage — has three problems we would rather not
buy:

1. **The API becomes the bottleneck.** Every byte crosses the app server. A
   handful of concurrent 20 MB uploads occupies request workers for the whole
   transfer, and those workers are what serve the listings feed.
2. **Timeouts and memory.** Platform request limits (and gunicorn's) are tuned
   for API calls, not for slow mobile uploads. Buffering a file to satisfy them
   trades one failure mode for another.
3. **It puts us in the byte path for no benefit.** We do not transform the
   file. We only need to know it arrived and is what it claimed to be.

## Decision

The client uploads **straight to Cloudflare R2**. The server issues a narrowly
scoped credential and verifies the result:

1. `POST /api/v1/uploads` — the server authorizes the purpose against the
   caller, checks the MIME allowlist, the size cap and the per-artist quota,
   **mints an opaque object key** (the client never proposes one), records a
   `media_uploads` row as `PENDING`, and returns a presigned POST.
2. The client posts the file directly to R2 with those exact fields.
3. `POST /api/v1/uploads/{id}/complete` — the server `HEAD`s the object and
   verifies it exists, its size is within the cap, and its content-type matches
   what was signed. Only then is the durable row written.

Playback URLs are short-lived presigned GETs minted per request at
serialization time, never stored.

### Presigned POST, not PUT

This is the part worth writing down. A presigned **PUT** cannot bound the body
size: a client can declare 10 MB when asking for the signature and then push
10 GB, and the first we would hear of it is the storage bill. A presigned
**POST** carries a policy with a `content-length-range` condition, so R2 itself
rejects an oversized body at the edge. The policy also pins the exact key and
content type, so a signature issued for one object cannot be replayed to write
another.

## Consequences

**Good.** The API never handles file bytes; upload traffic does not consume
request workers. Uploads survive slow connections without touching our
timeouts. Size enforcement happens at the edge, at Cloudflare's expense.

**The cost.** The flow is three round-trips rather than one, and the client has
to implement it — which is why it lives once in
`packages/shared/src/uploads.ts` rather than twice.

An upload can now be started and never finished, leaving an object nothing
references. `sweep_abandoned_uploads` (`flask media sweep`) reclaims those;
without it they accumulate silently and are billed monthly.

Trust cannot be placed in the client's claims about what it uploaded. The
`HEAD` verification at completion is not optional belt-and-braces — it is the
only point at which the server learns what actually landed.

## Alternatives considered

- **Server-proxied upload.** Simplest to write and to reason about; rejected for
  the three reasons above. Worth revisiting only if we start transforming files
  (transcoding, waveform extraction) — and even then the transform belongs in a
  worker reading from R2, not in the request path.
- **Presigned PUT.** Fewer moving parts on the client, but no size enforcement.
  Rejected — but see "Update" below; this is what shipped in the end.
- **Public bucket, unsigned reads.** Cheaper and cacheable, and supported via
  `R2_PUBLIC_BASE_URL`. Not the default: private-by-default with short-lived
  signed reads is the safer starting position, and the switch is one env var
  when the CDN economics justify it.

## Update (2026-08-05): R2 does not support presigned POST

The "Presigned POST, not PUT" decision above assumed R2 implements S3's
POST-policy API. It does not — a presigned POST against a live bucket answers
`501 NotImplemented` regardless of credentials, which this ADR had no way to
know without trying it. PUT was never actually a choice between two working
options; it is the only direct-upload path R2 supports.

The consequence is exactly what "Presigned PUT" above predicted: no
`content-length-range` condition, so R2 cannot bounce an oversized body at the
edge. The `HEAD` check at completion — already described above as "not
optional belt-and-braces" — is now the *only* size gate rather than a second
one, and an oversized object is deleted there rather than kept. Everything
else in this record (opaque keys, ownership re-derivation, the sweep for
abandoned uploads, private-by-default reads) is unchanged.

See `apps/server/app/services/r2_storage.py::generate_presigned_put` and
CLAUDE.md §4 for the current implementation.
