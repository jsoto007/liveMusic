/**
 * A show — the full listing.
 *
 * The specifics go in a table (venue, doors, first set, price, ages) because
 * they are figures, and figures belong in a column. The blurb is justified
 * prose underneath.
 */

import { useCallback, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ChevronLeft, Ticket } from "lucide-react";
import type { EventListing } from "@live-msc/shared";

import { ImageUpload } from "../components/ImageUpload";
import { Notice, Plate, Rule, SaveButton, SectionHead, Spinner } from "../components/Primitives";
import { useAuth } from "../context/AuthContext";
import { useResource } from "../hooks/useResource";
import { api } from "../lib/api";
import { stockPosterUrl } from "../lib/stock";

export function ShowDetailPage() {
  const { eventId = "" } = useParams();
  const navigate = useNavigate();
  const { user, initializing } = useAuth();
  const [posterError, setPosterError] = useState<string | null>(null);

  // Keyed on the reader, and held until the session has settled. This payload
  // is not the same for everyone: `saved`, `going` and `can_manage` are all
  // answers to "who is asking". Fetched on mount it would be answered before
  // the silent refresh returned, so opening a show from a link or a reload —
  // as opposed to clicking through from the bill — showed the owner a listing
  // with no poster control and their own saved shows as unsaved.
  const { data, error, loading, reload } = useResource<{ event: EventListing }>(
    () => api.get<{ event: EventListing }>(`/api/v1/events/${eventId}`),
    [eventId, user?.id ?? ""],
    { enabled: !initializing },
  );

  const event = data?.event ?? null;

  const setInterest = useCallback(
    async (patch: { saved?: boolean; going?: boolean }) => {
      if (!user) {
        navigate("/sign-in");
        return;
      }
      await api.put(`/api/v1/events/${eventId}/interest`, patch);
      reload();
    },
    [user, navigate, eventId, reload],
  );

  if ((loading || initializing) && !event) {
    return <div className="page page-narrow"><Spinner /></div>;
  }
  if (error || !event) {
    return (
      <div className="page page-narrow">
        <Notice tone="error">{error ?? "That listing could not be found."}</Notice>
        <Link className="btn btn-ghost" to="/">
          Back to the bill
        </Link>
      </div>
    );
  }

  return (
    <article className="page page-narrow">
      <button type="button" className="btn btn-ghost" onClick={() => navigate(-1)}>
        <ChevronLeft size={16} aria-hidden /> Back
      </button>

      <div style={{ marginTop: "var(--space-4)" }}>
        <Plate
          src={event.poster_url}
          fallbackSrc={stockPosterUrl(event.genre)}
          alt={event.poster_url ? `Poster for ${event.headline}` : ""}
          placeholder="show poster"
        />
        {event.poster_credit ? (
          <p className="plate-credit">{event.poster_credit}</p>
        ) : null}
        {/* Only for whoever the server says owns this listing. The flag is
            `can_manage` on the detail payload; the upload route re-derives the
            same ownership from the token regardless, so a forged flag buys an
            attacker a button and a 404. */}
        {event.can_manage ? (
          <>
            <ImageUpload
              purpose="event_poster"
              targetId={event.id}
              hasImage={Boolean(event.poster_url)}
              addLabel="Add a poster"
              replaceLabel="Replace the poster"
              onUploaded={reload}
              onError={setPosterError}
            />
            {posterError ? (
              <div style={{ marginTop: "var(--space-2)" }}>
                <Notice tone="error">{posterError}</Notice>
              </div>
            ) : null}
          </>
        ) : null}
      </div>

      <header style={{ paddingTop: "var(--space-4)" }}>
        <p className="kicker kicker-accent">
          {event.day_label} · {event.date_long}
        </p>
        <h1 className="detail-title">{event.headline}</h1>
        {event.support_line ? <p className="detail-support">{event.support_line}</p> : null}
        {event.cancelled ? (
          <div style={{ marginTop: "var(--space-3)" }}>
            <Notice tone="error">This show has been cancelled.</Notice>
          </div>
        ) : null}
      </header>

      <Rule />

      <table className="table spec-table">
        <tbody>
          <tr>
            <th scope="row">Venue</th>
            <td>
              {event.venue?.name}
              {event.venue?.neighborhood ? `, ${event.venue.neighborhood}` : null}
            </td>
          </tr>
          {event.doors_label ? (
            <tr>
              <th scope="row">Doors</th>
              <td>{event.doors_label}</td>
            </tr>
          ) : null}
          <tr>
            <th scope="row">First set</th>
            <td>{event.time_label}</td>
          </tr>
          <tr>
            <th scope="row">Door price</th>
            {/* "Not stated" is a different fact from "free" and prints as one. */}
            <td>{event.price_label ?? "Not stated"}</td>
          </tr>
          <tr>
            <th scope="row">Ages</th>
            <td>{event.age_label}</td>
          </tr>
        </tbody>
      </table>

      {event.blurb ? (
        <p className="prose" style={{ marginTop: "var(--space-4)" }}>
          {event.blurb}
        </p>
      ) : null}

      {event.lineup && event.lineup.length > 0 ? (
        <>
          <Rule />
          <SectionHead title="On the bill" />
          {event.lineup.map((slot, index) => (
            <div
              key={`${slot.name}-${index}`}
              style={{
                display: "grid",
                gridTemplateColumns: "70px 1fr",
                gap: "var(--space-3)",
                alignItems: "baseline",
                borderBottom: "1px solid var(--color-divider)",
                padding: "var(--space-2) 0",
              }}
            >
              <span className="listing-time">{slot.time_label ?? "—"}</span>
              <span>
                <span style={{ display: "block", fontFamily: "var(--font-heading)", fontSize: "15px" }}>
                  {slot.name}
                </span>
                {slot.note ? (
                  <span className="listing-note italic" style={{ marginTop: "1px" }}>
                    {slot.note}
                  </span>
                ) : null}
              </span>
            </div>
          ))}
        </>
      ) : null}

      <div className="actions">
        <button
          type="button"
          className={event.going ? "btn btn-toggle btn-on" : "btn btn-toggle"}
          onClick={() => void setInterest({ going: !event.going })}
          aria-pressed={event.going}
        >
          {event.going ? "You're going" : "I'm going"}
        </button>
        {event.ticket_url ? (
          <a
            className="btn btn-secondary"
            href={event.ticket_url}
            target="_blank"
            // noopener/noreferrer: the ticket link is supplied by whoever
            // posted the show, so the new tab must not get a handle on ours.
            rel="noopener noreferrer"
          >
            <Ticket size={16} aria-hidden /> Tickets
          </a>
        ) : null}
        <SaveButton saved={event.saved} onToggle={() => void setInterest({ saved: !event.saved })} />
      </div>

      {event.artist ? (
        <Link className="btn btn-ghost btn-block" to={`/bands/${event.artist.slug}`}>
          More from {event.artist.name} →
        </Link>
      ) : null}
    </article>
  );
}
