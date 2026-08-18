/**
 * Your account — and, if you hold one, your band's page.
 *
 * The sound-sample uploader shows the direct-to-R2 flow plainly: pick a file,
 * it goes straight to storage, and only then does a row appear. The band photo
 * uses the shared `<ImageUpload>`, the same control the show poster uses — one
 * implementation, so the two cannot drift apart again.
 */

import { useCallback, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, X } from "lucide-react";
import {
  ACCEPTED_AUDIO_TYPES,
  inferContentType,
  uploadDirect,
  type Artist,
  type AudioSample,
  type EmailPreferences,
  type EventListing,
  type Place,
} from "@live-msc/shared";

import { AddressField } from "../components/AddressField";
import { ImageUpload } from "../components/ImageUpload";
import { Empty, Notice, Plate, Rule, SectionHead, Spinner } from "../components/Primitives";
import { Avatar } from "../components/Social";
import { useAuth } from "../context/AuthContext";
import { useResource } from "../hooks/useResource";
import { api } from "../lib/api";
import type { UserCard } from "@live-msc/shared";

export function AccountPage() {
  const { user, artists, initializing, signOut, refreshProfile } = useAuth();
  const [newBandName, setNewBandName] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (initializing) return <div className="page page-narrow"><Spinner /></div>;

  if (!user) {
    return (
      <div className="page page-narrow">
        <h1 className="page-title">Your account</h1>
        <Notice>Sign in to see your account.</Notice>
        <Link className="btn btn-primary" to="/sign-in">
          Sign in
        </Link>
      </div>
    );
  }

  async function createBand() {
    setError(null);
    const result = await api.post<{ artist: Artist }>("/api/v1/me/artists", {
      name: newBandName.trim(),
      city: user?.home_city ?? undefined,
    });
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setNewBandName("");
    await refreshProfile();
  }

  return (
    <div className="page page-narrow">
      <p className="kicker kicker-accent">Account</p>
      <div className="profile-head" style={{ paddingTop: 0 }}>
        <Avatar user={user} size="lg" />
        <div>
          <h1 className="detail-title" style={{ margin: 0 }}>{user.display_name}</h1>
          <p className="detail-support">
            @{user.handle} · {user.home_city ?? "No home city set"} · {user.email}
          </p>
          <Link className="btn btn-ghost btn-quiet" to={`/u/${user.handle}`}>
            View your public page →
          </Link>
        </div>
      </div>

      {error ? <Notice tone="error">{error}</Notice> : null}

      {!user.email_verified ? <VerifyBanner email={user.email ?? ""} /> : null}

      <PublicProfilePanel
        handle={user.handle}
        bio={user.bio}
        userId={user.id}
        hasAvatar={Boolean(user.avatar_url)}
        onSaved={refreshProfile}
      />
      <HomeCityField currentCity={user.home_city} onSaved={refreshProfile} />
      <EmailPreferencesPanel />
      <BlockedPeoplePanel />

      {artists.map((artist) => (
        <BandPanel key={artist.id} artist={artist} onChanged={refreshProfile} />
      ))}

      <Rule />
      <SectionHead title="Start a band account" />
      <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-3)" }}>
        <input
          className="input"
          value={newBandName}
          onChange={(e) => setNewBandName(e.target.value)}
          placeholder="Band name"
          maxLength={120}
          aria-label="Band name"
        />
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => void createBand()}
          disabled={!newBandName.trim()}
        >
          Create
        </button>
      </div>

      <Rule />
      <button type="button" className="btn btn-secondary btn-block" onClick={() => void signOut()}>
        Sign out
      </button>
    </div>
  );
}

function BandPanel({ artist, onChanged }: { artist: Artist; onChanged: () => Promise<void> }) {
  const [hireOn, setHireOn] = useState(artist.available_for_hire);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement | null>(null);

  const detail = useResource<{ artist: Artist }>(
    () => api.get<{ artist: Artist }>(`/api/v1/artists/${artist.id}`),
    [artist.id],
  );
  const listings = useResource<{ events: EventListing[] }>(
    () => api.get<{ events: EventListing[] }>(`/api/v1/me/artists/${artist.id}/events`),
    [artist.id],
  );

  const samples = detail.data?.artist.samples ?? [];

  const toggleHire = useCallback(
    async (next: boolean) => {
      setHireOn(next);
      const result = await api.patch(`/api/v1/artists/${artist.id}`, {
        available_for_hire: next,
      });
      if (!result.ok) {
        // Put the switch back where it was rather than showing a state the
        // server did not accept.
        setHireOn(!next);
        setError(result.error);
      }
    },
    [artist.id],
  );

  const addSample = useCallback(
    async (file: File) => {
      setError(null);
      const contentType = inferContentType(file.name, file.type);
      if (!contentType || !ACCEPTED_AUDIO_TYPES.includes(contentType as never)) {
        setError("That is not an audio format we accept.");
        return;
      }

      setUploading(true);
      try {
        await uploadDirect<{ sample: AudioSample }>(
          api,
          {
            purpose: "artist_audio",
            targetId: artist.id,
            contentType,
            sizeBytes: file.size,
          },
          file,
          { completion: { title: file.name.replace(/\.[^.]+$/, "").slice(0, 140) } },
        );
        detail.reload();
        await onChanged();
      } catch (uploadError) {
        setError(
          uploadError instanceof Error ? uploadError.message : "The upload failed.",
        );
      } finally {
        setUploading(false);
        if (fileInput.current) fileInput.current.value = "";
      }
    },
    [artist.id, detail, onChanged],
  );

  const removeSample = useCallback(
    async (sampleId: string) => {
      const result = await api.delete(`/api/v1/artists/${artist.id}/samples/${sampleId}`);
      if (!result.ok) {
        setError(result.error);
        return;
      }
      detail.reload();
    },
    [artist.id, detail],
  );

  return (
    <section style={{ marginTop: "var(--space-6)" }}>
      <Rule />
      <div className="section-head" style={{ marginTop: "var(--space-4)" }}>
        <div>
          <h2 className="proper-noun">{artist.name}</h2>
          <p className="page-sub">Band account</p>
        </div>
        <Link className="btn btn-ghost" to={`/bands/${artist.slug}`}>
          View page →
        </Link>
      </div>

      {error ? <Notice tone="error">{error}</Notice> : null}

      <div style={{ marginTop: "var(--space-3)" }}>
        <Plate
          src={detail.data?.artist.photo_url}
          alt={`${artist.name}`}
          placeholder="band photo — press shot, or the four of you outside the practice room"
        />
        <ImageUpload
          purpose="artist_photo"
          targetId={artist.id}
          hasImage={Boolean(detail.data?.artist.photo_url)}
          addLabel="Add a band photo"
          replaceLabel="Replace the photo"
          onUploaded={async () => {
            detail.reload();
            await onChanged();
          }}
          onError={setError}
        />
      </div>

      <div className="stat-grid" style={{ marginTop: "var(--space-4)" }}>
        <div className="stat">
          <div className="stat-n">{detail.data?.artist.follower_count ?? 0}</div>
          <div className="stat-label">Following</div>
        </div>
        <div className="stat">
          <div className="stat-n">{listings.data?.events.length ?? 0}</div>
          <div className="stat-label">Listings</div>
        </div>
        <div className="stat">
          <div className="stat-n">{samples.length}</div>
          <div className="stat-label">Samples</div>
        </div>
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "var(--space-3)",
          marginTop: "var(--space-4)",
        }}
      >
        <div>
          <p className="kicker">Hire profile</p>
          <p className="form-note">Shown on your public page</p>
        </div>
        <div className="seg">
          <label className="seg-opt">
            <input
              type="radio"
              name={`hire-${artist.id}`}
              checked={hireOn}
              onChange={() => void toggleHire(true)}
            />
            Available
          </label>
          <label className="seg-opt">
            <input
              type="radio"
              name={`hire-${artist.id}`}
              checked={!hireOn}
              onChange={() => void toggleHire(false)}
            />
            Hidden
          </label>
        </div>
      </div>

      <div className="section-head">
        <h2>Sound samples</h2>
        <button
          type="button"
          className="btn btn-ghost"
          onClick={() => fileInput.current?.click()}
          disabled={uploading}
        >
          <Plus size={14} aria-hidden /> {uploading ? "Uploading…" : "Add sample"}
        </button>
      </div>
      <div className="rule-strong" />
      <input
        ref={fileInput}
        type="file"
        accept={ACCEPTED_AUDIO_TYPES.join(",")}
        className="sr-only"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void addSample(file);
        }}
      />

      {samples.length === 0 ? <Empty>No samples yet.</Empty> : null}
      {samples.map((sample) => (
        <div className="sample" key={sample.id}>
          <span />
          <span className="sample-title">{sample.title}</span>
          <span className="sample-duration">{sample.duration_label ?? "—"}</span>
          <button
            type="button"
            className="btn btn-icon btn-ghost"
            onClick={() => void removeSample(sample.id)}
            aria-label={`Remove ${sample.title}`}
          >
            <X size={12} aria-hidden />
          </button>
        </div>
      ))}

      <SectionHead title="Your listings" />
      {listings.data?.events.length === 0 ? <Empty>Nothing posted yet.</Empty> : null}
      {listings.data?.events.map((event) => (
        <div
          key={event.id}
          style={{
            display: "grid",
            gridTemplateColumns: "1fr auto",
            gap: "var(--space-3)",
            alignItems: "baseline",
            borderBottom: "1px solid var(--color-divider)",
            padding: "var(--space-3) 0",
          }}
        >
          <span>
            <span style={{ display: "block", fontFamily: "var(--font-heading)", fontSize: "16px" }}>
              {event.venue?.name}
            </span>
            <span className="listing-note">
              {event.date_long} · {event.time_label}
            </span>
          </span>
          <span className={event.status === "published" ? "tag tag-accent" : "tag tag-neutral"}>
            {event.status === "published"
              ? "On the bill"
              : event.status === "cancelled"
                ? "Cancelled"
                : "Draft"}
          </span>
        </div>
      ))}
    </section>
  );
}

/** The public face: your @handle, your line of bio, your photograph. */
function PublicProfilePanel({
  handle,
  bio,
  userId,
  hasAvatar,
  onSaved,
}: {
  handle: string;
  bio: string | null;
  userId: string;
  hasAvatar: boolean;
  onSaved: () => Promise<void>;
}) {
  const [draftHandle, setDraftHandle] = useState(handle);
  const [draftBio, setDraftBio] = useState(bio ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  const dirty =
    draftHandle.trim().toLowerCase() !== handle ||
    draftBio.trim() !== (bio ?? "").trim();

  async function save() {
    setBusy(true);
    setError(null);
    setSaved(false);
    const payload: Record<string, unknown> = {};
    if (draftHandle.trim().toLowerCase() !== handle) {
      payload.handle = draftHandle.trim();
    }
    if (draftBio.trim() !== (bio ?? "").trim()) {
      payload.bio = draftBio.trim() || null;
    }
    const result = await api.patch("/api/v1/me", payload);
    setBusy(false);
    if (!result.ok) {
      setError(
        result.code === "HANDLE_TAKEN"
          ? "That handle is already in use — try another."
          : result.error,
      );
      return;
    }
    setSaved(true);
    await onSaved();
  }

  return (
    <>
      <SectionHead title="Public profile" />
      <div style={{ marginTop: "var(--space-3)" }}>
        <ImageUpload
          purpose="user_avatar"
          targetId={userId}
          hasImage={hasAvatar}
          addLabel="Add a photograph of yourself"
          replaceLabel="Replace your photograph"
          onUploaded={async () => {
            await onSaved();
          }}
          onError={setError}
        />

        <label className="field" style={{ marginTop: "var(--space-3)" }}>
          Handle
          <input
            className="input"
            maxLength={30}
            value={draftHandle}
            onChange={(event) => {
              setDraftHandle(event.target.value);
              setSaved(false);
            }}
            aria-describedby="handle-note"
          />
        </label>
        <p className="form-note" id="handle-note">
          3–30 characters, a–z, 0–9 and _. Your page lives at /u/{draftHandle.trim().toLowerCase() || "…"}
          {" "}— old links stop working when you change it.
        </p>

        <label className="field" style={{ marginTop: "var(--space-3)" }}>
          A line about you
          <textarea
            className="input"
            rows={2}
            maxLength={500}
            placeholder="Fan of small rooms and long encores."
            value={draftBio}
            onChange={(event) => {
              setDraftBio(event.target.value);
              setSaved(false);
            }}
          />
        </label>

        {error ? <Notice tone="error">{error}</Notice> : null}
        {dirty ? (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => void save()}
            disabled={busy}
            style={{ marginTop: "var(--space-2)" }}
          >
            {busy ? "Saving…" : "Save profile"}
          </button>
        ) : null}
        {saved && !dirty ? <p className="form-note">Saved.</p> : null}
      </div>
    </>
  );
}

/** The people you've shut out, and the way back. */
function BlockedPeoplePanel() {
  const { data, error, reload } = useResource<{ people: UserCard[] }>(
    () => api.get<{ people: UserCard[] }>("/api/v1/me/blocks"),
    [],
  );

  async function unblock(handle: string) {
    await api.delete(`/api/v1/users/${handle}/block`);
    reload();
  }

  if (data && data.people.length === 0) return null;

  return (
    <>
      <SectionHead title="Blocked readers" />
      {error ? <Notice tone="error">{error}</Notice> : null}
      {data?.people.map((person) => (
        <div key={person.id} className="person-row">
          <span>
            <span className="byline-name">{person.display_name}</span>
            <span className="byline-sub"> @{person.handle}</span>
          </span>
          <button
            type="button"
            className="btn btn-ghost btn-quiet"
            onClick={() => void unblock(person.handle)}
          >
            Unblock
          </button>
        </div>
      ))}
    </>
  );
}

/**
 * Shown until the address is confirmed.
 *
 * Not a blocker — an unverified reader can still use the paper. It is a
 * prompt, because an unconfirmed address means our notifications are going
 * nowhere and we have no way to tell them so.
 */
function VerifyBanner({ email }: { email: string }) {
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  async function resend() {
    setBusy(true);
    await api.post("/api/v1/auth/verify-email/resend", { email });
    setBusy(false);
    setSent(true);
  }

  return (
    <div className="notice" style={{ marginTop: "var(--space-4)" }}>
      {sent ? (
        <>A new confirmation link is on its way to {email}.</>
      ) : (
        <>
          Your email isn&rsquo;t confirmed yet, so notices won&rsquo;t reach you.{" "}
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => void resend()}
            disabled={busy}
            style={{ padding: "0 4px" }}
          >
            {busy ? "Sending…" : "Send another link"}
          </button>
        </>
      )}
    </div>
  );
}

/** Home city, with address suggestions — it drives the map's default centre. */
function HomeCityField({
  currentCity,
  onSaved,
}: {
  currentCity: string | null;
  onSaved: () => Promise<void>;
}) {
  const [city, setCity] = useState(currentCity ?? "");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  const dirty = city.trim() !== (currentCity ?? "").trim();

  async function save(next?: string) {
    const value = (next ?? city).trim();
    setBusy(true);
    const result = await api.patch("/api/v1/me", { home_city: value || null });
    setBusy(false);
    if (result.ok) {
      setSaved(true);
      await onSaved();
    }
  }

  return (
    <>
      <SectionHead title="Home city" />
      <div style={{ marginTop: "var(--space-3)" }}>
        <AddressField
          id="home-city"
          label="Where you are"
          value={city}
          onChange={(next) => {
            setCity(next);
            setSaved(false);
          }}
          onSelect={(place: Place) => {
            const resolved = place.city ?? place.name;
            setCity(resolved);
            void save(resolved);
          }}
          placeholder="Providence"
          note="Used to centre the map and to pick your default listings."
          maxLength={120}
        />
        {dirty ? (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => void save()}
            disabled={busy}
          >
            {busy ? "Saving…" : "Save"}
          </button>
        ) : null}
        {saved && !dirty ? <p className="form-note">Saved.</p> : null}
      </div>
    </>
  );
}

/** What we're allowed to email about. */
function EmailPreferencesPanel() {
  const { data, error, reload } = useResource<{ preferences: EmailPreferences }>(
    () => api.get<{ preferences: EmailPreferences }>("/api/v1/me/email-preferences"),
    [],
  );
  const [saving, setSaving] = useState(false);
  const preferences = data?.preferences;

  async function update(patch: Partial<EmailPreferences>) {
    setSaving(true);
    await api.patch("/api/v1/me/email-preferences", patch);
    setSaving(false);
    reload();
  }

  return (
    <>
      <SectionHead title="Notices" count={saving ? "saving" : undefined} />
      {error ? <Notice tone="error">{error}</Notice> : null}

      <ToggleRow
        label="New shows from bands you follow"
        note="One email when a band you follow posts a listing."
        checked={preferences?.notify_new_shows ?? false}
        onChange={(value) => void update({ notify_new_shows: value })}
      />
      <ToggleRow
        label="Reminders for shows you're going to"
        note="The day before, for anything you've marked."
        checked={preferences?.notify_show_reminders ?? false}
        onChange={(value) => void update({ notify_show_reminders: value })}
      />

      {preferences?.unsubscribed_all ? (
        <p className="form-note">
          You&rsquo;re unsubscribed from everything. Turning either notice back on
          will start them again. Account mail — password resets and the like —
          reaches you regardless.
        </p>
      ) : null}
    </>
  );
}

function ToggleRow({
  label,
  note,
  checked,
  onChange,
}: {
  label: string;
  note: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "var(--space-3)",
        padding: "var(--space-3) 0",
        borderBottom: "1px solid var(--color-divider)",
      }}
    >
      <div>
        <div style={{ fontSize: "14px" }}>{label}</div>
        <p className="form-note">{note}</p>
      </div>
      <div className="seg" style={{ flex: "none" }}>
        <label className="seg-opt">
          <input
            type="radio"
            name={label}
            checked={checked}
            onChange={() => onChange(true)}
          />
          On
        </label>
        <label className="seg-opt">
          <input
            type="radio"
            name={label}
            checked={!checked}
            onChange={() => onChange(false)}
          />
          Off
        </label>
      </div>
    </div>
  );
}
