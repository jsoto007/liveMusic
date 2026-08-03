/**
 * A band — the public profile, with the sound samples playable inline.
 *
 * Playback uses one shared `<audio>` element rather than one per row: several
 * elements would let two samples play over each other, and each would hold its
 * own connection to a signed URL.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { Pause, Play } from "lucide-react";
import type { Artist, EventListing } from "@live-msc/shared";

import { Empty, Notice, Plate, Rule, SectionHead, Spinner, Tag } from "../components/Primitives";
import { useAuth } from "../context/AuthContext";
import { useResource } from "../hooks/useResource";
import { api } from "../lib/api";

export function BandPage() {
  const { handle = "" } = useParams();
  const { user } = useAuth();

  const { data, error, loading, reload } = useResource<{ artist: Artist }>(
    () => api.get<{ artist: Artist }>(`/api/v1/artists/${encodeURIComponent(handle)}`),
    [handle],
  );
  const { data: eventsData } = useResource<{ events: EventListing[] }>(
    () => api.get<{ events: EventListing[] }>(`/api/v1/artists/${encodeURIComponent(handle)}/events`),
    [handle],
  );

  const artist = data?.artist ?? null;
  const { playingId, toggle } = useAudioPlayer();

  const toggleFollow = useCallback(async () => {
    if (!artist || !user) return;
    if (artist.is_following) {
      await api.delete(`/api/v1/artists/${artist.id}/follow`);
    } else {
      await api.post(`/api/v1/artists/${artist.id}/follow`);
    }
    reload();
  }, [artist, user, reload]);

  if (loading && !artist) return <div className="page page-narrow"><Spinner /></div>;
  if (error || !artist) {
    return (
      <div className="page page-narrow">
        <Notice tone="error">{error ?? "That band could not be found."}</Notice>
      </div>
    );
  }

  const samples = artist.samples ?? [];

  return (
    <article className="page page-narrow">
      <Plate src={artist.photo_url} alt={`${artist.name}`} placeholder="band photo" />

      <header style={{ paddingTop: "var(--space-4)" }}>
        <p className="kicker kicker-accent">
          Band{artist.neighborhood ? ` · ${artist.neighborhood}` : ""}
        </p>
        <h1 className="detail-title">{artist.name}</h1>
        {artist.one_liner ? <p className="detail-support">{artist.one_liner}</p> : null}
        {artist.available_for_hire ? (
          <p style={{ marginTop: "10px" }}>
            <span className="tag tag-accent">Available for hire</span>
          </p>
        ) : null}
      </header>

      <div className="actions">
        <button
          type="button"
          className={artist.is_following ? "btn btn-toggle btn-on" : "btn btn-toggle"}
          onClick={() => void toggleFollow()}
          aria-pressed={artist.is_following ?? false}
          disabled={!user}
          title={user ? undefined : "Sign in to follow"}
        >
          {artist.is_following ? "Following" : "Follow"}
        </button>
        {samples[0]?.stream_url ? (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => toggle(samples[0]!.id, samples[0]!.stream_url!)}
          >
            {playingId === samples[0].id ? "Pause" : "Listen"}
          </button>
        ) : null}
      </div>

      {artist.bio ? (
        <p className="prose" style={{ marginTop: "var(--space-4)" }}>
          {artist.bio}
        </p>
      ) : null}

      {eventsData?.events && eventsData.events.length > 0 ? (
        <>
          <SectionHead title="Upcoming" />
          {eventsData.events.map((event) => (
            <div
              key={event.id}
              style={{
                display: "grid",
                gridTemplateColumns: "84px 1fr auto",
                gap: "var(--space-3)",
                alignItems: "baseline",
                borderBottom: "1px solid var(--color-divider)",
                padding: "var(--space-3) 0",
              }}
            >
              <span className="listing-time">{event.date_long}</span>
              <span>
                <span style={{ display: "block", fontFamily: "var(--font-heading)", fontSize: "15.5px" }}>
                  {event.venue?.name}
                </span>
                {event.support_line ? (
                  <span className="listing-note italic">{event.support_line}</span>
                ) : null}
              </span>
              <span className="sample-duration">{event.price_label ?? "—"}</span>
            </div>
          ))}
        </>
      ) : null}

      {(artist.members?.length ?? 0) > 0 || artist.sounds_like ? (
        <>
          <Rule />
          <div className="two-column">
            {artist.members && artist.members.length > 0 ? (
              <div>
                <p className="kicker">Members</p>
                <p style={{ lineHeight: 1.7, fontSize: "12px", marginTop: "5px" }}>
                  {artist.members.map((member) => (
                    <span key={member.name} style={{ display: "block" }}>
                      {member.name}
                      {member.instrument ? ` — ${member.instrument}` : null}
                    </span>
                  ))}
                </p>
              </div>
            ) : null}
            {artist.sounds_like ? (
              <div>
                <p className="kicker">Sounds like</p>
                <p className="italic" style={{ lineHeight: 1.7, fontSize: "12px", marginTop: "5px" }}>
                  {artist.sounds_like}
                </p>
              </div>
            ) : null}
          </div>
        </>
      ) : null}

      {artist.style_tags.length > 0 ? (
        <>
          <Rule />
          <SectionHead title="Style" />
          <div className="chip-row" style={{ marginTop: "var(--space-3)" }}>
            {artist.style_tags.map((tag) => (
              <Tag key={tag}>{tag}</Tag>
            ))}
          </div>
        </>
      ) : null}

      <Rule />
      <SectionHead
        title="Sound samples"
        count={samples.length === 1 ? "1 sample" : `${samples.length} samples`}
      />
      {samples.length === 0 ? <Empty>No samples yet.</Empty> : null}
      {samples.map((sample) => {
        const isPlaying = playingId === sample.id;
        return (
          <div className="sample" key={sample.id}>
            <button
              type="button"
              className="btn btn-icon btn-ghost"
              onClick={() => sample.stream_url && toggle(sample.id, sample.stream_url)}
              disabled={!sample.stream_url}
              aria-label={`${isPlaying ? "Pause" : "Play"} ${sample.title}`}
            >
              {isPlaying ? <Pause size={14} aria-hidden /> : <Play size={14} aria-hidden />}
            </button>
            <span className="sample-title">
              {sample.title}
              {isPlaying ? (
                <span style={{ display: "flex", alignItems: "center", marginTop: "4px" }}>
                  <span className="eq" aria-hidden>
                    <i />
                    <i />
                    <i />
                  </span>
                  <span className="playing-label">Playing</span>
                </span>
              ) : null}
            </span>
            <span />
            <span className="sample-duration">{sample.duration_label ?? "—"}</span>
          </div>
        );
      })}
    </article>
  );
}

/** One `<audio>` element for the page; play/pause switches its source. */
function useAudioPlayer() {
  const elementRef = useRef<HTMLAudioElement | null>(null);
  const [playingId, setPlayingId] = useState<string | null>(null);

  useEffect(() => {
    const audio = new Audio();
    audio.preload = "none";
    audio.addEventListener("ended", () => setPlayingId(null));
    audio.addEventListener("error", () => setPlayingId(null));
    elementRef.current = audio;
    return () => {
      // Without this the sample keeps playing after navigating away.
      audio.pause();
      audio.src = "";
      elementRef.current = null;
    };
  }, []);

  const toggle = useCallback(
    (id: string, url: string) => {
      const audio = elementRef.current;
      if (!audio) return;
      if (playingId === id) {
        audio.pause();
        setPlayingId(null);
        return;
      }
      audio.src = url;
      void audio
        .play()
        .then(() => setPlayingId(id))
        .catch(() => setPlayingId(null));
    },
    [playingId],
  );

  return { playingId, toggle };
}
