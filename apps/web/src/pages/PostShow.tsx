/**
 * Post a show — three fields, and it prints tonight.
 *
 * "Add the details" is collapsed by design: the prototype's whole promise is
 * that a band can put a show on the bill in three fields. Everything else is
 * optional and stays out of the way until asked for.
 */

import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { CheckCircle } from "lucide-react";
import {
  ACCEPTED_IMAGE_TYPES,
  AGE_OPTIONS,
  GENRES,
  inferContentType,
  isOpenableTicketUrl,
  uploadDirect,
  type AgeRestriction,
  type EventListing,
  type Genre,
  type Place,
} from "@live-msc/shared";

import { AddressField } from "../components/AddressField";
import { Notice, Rule } from "../components/Primitives";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";

/**
 * Turn "tonight at 9pm" into an instant.
 *
 * The form takes a date and a time separately, and the browser hands us a
 * local-time string. Constructing the Date from the parts (rather than parsing
 * the string) makes the reader's own zone the reference, which is what they
 * meant when they typed it.
 */
function toIsoInstant(date: string, time: string): string | null {
  if (!date || !time) return null;
  const [year, month, day] = date.split("-").map(Number);
  const [hour, minute] = time.split(":").map(Number);
  if ([year, month, day, hour, minute].some((part) => part === undefined || Number.isNaN(part))) {
    return null;
  }
  return new Date(year!, month! - 1, day!, hour!, minute!).toISOString();
}

export function PostShowPage() {
  const navigate = useNavigate();
  const { user, artists } = useAuth();

  const [headline, setHeadline] = useState("");
  const [venueName, setVenueName] = useState("");
  const [city, setCity] = useState(user?.home_city ?? "");
  const [neighborhood, setNeighborhood] = useState("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("21:00");
  const [showMore, setShowMore] = useState(false);
  const [price, setPrice] = useState("");
  const [ages, setAges] = useState<AgeRestriction>("21_plus");
  const [genre, setGenre] = useState<Genre>("rock_punk");
  const [note, setNote] = useState("");
  const [ticketUrl, setTicketUrl] = useState("");
  const [poster, setPoster] = useState<File | null>(null);
  const [artistId, setArtistId] = useState(artists[0]?.id ?? "");
  // Set when a suggestion is chosen. Sending the coordinates we already have
  // saves the server a lookup and pins the room exactly where the reader
  // picked, rather than wherever a name search happens to land.
  const [venuePlace, setVenuePlace] = useState<Place | null>(null);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [posted, setPosted] = useState<EventListing | null>(null);
  // Kept apart from `error`: the listing itself succeeded, and colouring the
  // whole confirmation as a failure would read as "the show did not post".
  const [posterNote, setPosterNote] = useState<string | null>(null);

  if (!user) {
    return (
      <div className="page page-narrow">
        <h1 className="page-title">Post a show</h1>
        <Notice>You need an account to put a show on the bill.</Notice>
        <button type="button" className="btn btn-primary" onClick={() => navigate("/sign-in")}>
          Sign in
        </button>
      </div>
    );
  }

  if (posted) {
    return (
      <div className="page page-narrow" style={{ textAlign: "center" }}>
        <CheckCircle size={34} strokeWidth={1.2} color="var(--color-accent)" aria-hidden
          style={{ margin: "var(--space-8) auto 0" }} />
        <h1 className="page-title" style={{ marginTop: "var(--space-3)" }}>
          It&rsquo;s on the bill
        </h1>
        <p className="listing-meta">Set into the listings and pushed to everyone following you.</p>
        {/* The poster is the one part of this that can fail on its own. It is
            reported here, on the screen that also carries the link to the page
            where the band can put it right. */}
        {posterNote ? (
          <div style={{ marginTop: "var(--space-4)", textAlign: "left" }}>
            <Notice>{posterNote}</Notice>
          </div>
        ) : null}
        <div style={{ marginTop: "var(--space-6)" }}>
          <button
            type="button"
            className="btn btn-primary btn-block"
            onClick={() => navigate(`/shows/${posted.id}`)}
          >
            See it in the bill
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-block"
            onClick={() => {
              setPosted(null);
              setPosterNote(null);
              setPoster(null);
              setHeadline("");
              setNote("");
            }}
          >
            Post another
          </button>
        </div>
      </div>
    );
  }

  const priceCents = (() => {
    const trimmed = price.trim().replace(/^\$/, "");
    if (!trimmed) return undefined;
    if (/^free$/i.test(trimmed)) return 0;
    const value = Number(trimmed);
    return Number.isFinite(value) && value >= 0 ? Math.round(value * 100) : undefined;
  })();

  async function handleSubmit(formEvent: FormEvent) {
    formEvent.preventDefault();
    setError(null);

    const startsAt = toIsoInstant(date, time);
    if (!startsAt) {
      setError("Pick a date and a time for the show.");
      return;
    }

    // Checked here so a typo comes back beside the field, rather than as a
    // server error after half the listing has been made.
    const ticket = ticketUrl.trim();
    if (ticket && !isOpenableTicketUrl(ticket)) {
      setError(
        "The ticket link needs to be a full web address, starting http:// or https://.",
      );
      return;
    }

    setSubmitting(true);
    try {
      const created = await api.post<{ event: EventListing }>("/api/v1/events", {
        headline: headline.trim(),
        artist_id: artistId || undefined,
        starts_at: startsAt,
        venue: {
          name: venueName.trim(),
          city: city.trim(),
          neighborhood: neighborhood.trim() || undefined,
          address: venuePlace?.label,
          latitude: venuePlace?.latitude,
          longitude: venuePlace?.longitude,
          // The venue's zone is the reader's zone by default — a band posting
          // its own show is nearly always in the same city as the room.
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        },
        genre,
        price_cents: priceCents,
        age_restriction: ages,
        short_line: note.trim() || undefined,
        ticket_url: ticket || undefined,
        publish: true,
      });

      if (!created.ok || !created.data) {
        setError(created.ok ? "The show could not be posted." : created.error);
        return;
      }

      const event = created.data.event;

      // The poster is a separate, optional step: a failed image upload must
      // not lose the listing the band just wrote. What it must not do either
      // is fail quietly — a band that chose a file and is told nothing has no
      // reason to think the poster is missing until someone else notices.
      if (poster) {
        const contentType = inferContentType(poster.name, poster.type);
        if (!contentType) {
          // Previously this branch did nothing at all: an unrecognised
          // extension meant the file was dropped without a word.
          setPosterNote(
            "The show is posted. That file was not an image format we recognise — " +
              "add a JPEG, PNG, WebP or AVIF from the show's page.",
          );
        } else {
          try {
            await uploadDirect(api, {
              purpose: "event_poster",
              targetId: event.id,
              contentType,
              sizeBytes: poster.size,
            }, poster);
          } catch (uploadError) {
            // The server's own message is shown rather than a generic one:
            // "uploads are temporarily unavailable" and "that file is too
            // large" want different things from the reader.
            const reason =
              uploadError instanceof Error ? uploadError.message : "The upload failed.";
            setPosterNote(`The show is posted, but the poster did not upload. ${reason}`);
          }
        }
      }

      setPosted(event);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="page page-narrow" onSubmit={(e) => void handleSubmit(e)}>
      <h1 className="page-title">Post a show</h1>
      <p className="form-note">Three fields. It prints tonight.</p>

      {error ? <Notice tone="error">{error}</Notice> : null}

      <div className="stack" style={{ marginTop: "var(--space-6)" }}>
        {artists.length > 0 ? (
          <div className="field">
            <label htmlFor="artist">Posting as</label>
            <select
              id="artist"
              className="input"
              value={artistId}
              onChange={(e) => setArtistId(e.target.value)}
            >
              <option value="">Just me</option>
              {artists.map((artist) => (
                <option key={artist.id} value={artist.id}>
                  {artist.name}
                </option>
              ))}
            </select>
          </div>
        ) : null}

        <div className="field">
          <label htmlFor="headline">Who&rsquo;s playing</label>
          <input
            id="headline"
            className="input"
            value={headline}
            onChange={(e) => setHeadline(e.target.value)}
            placeholder="Bloodroot Choir"
            maxLength={160}
            required
          />
        </div>

        <AddressField
          id="venue"
          label="Where"
          value={venueName}
          onChange={(next) => {
            setVenueName(next);
            // Typing again invalidates the pin we had — better no coordinates
            // than coordinates for a room they have moved on from.
            setVenuePlace(null);
          }}
          onSelect={(place) => {
            setVenuePlace(place);
            if (place.city) setCity(place.city);
            if (place.neighborhood) setNeighborhood(place.neighborhood);
          }}
          placeholder="Dusk, or 301 Harris Ave"
          note="Start typing and pick the room — that puts it on the map."
          required
          maxLength={160}
        />

        <div className="field">
          <label htmlFor="city">City</label>
          <input
            id="city"
            className="input"
            value={city}
            onChange={(e) => setCity(e.target.value)}
            placeholder="Providence"
            maxLength={120}
            required
          />
        </div>

        {/* The poster used to live inside "Add the details", folded shut by
            default, so most bands never found it and shows went up bare. A
            picture is the first thing a reader looks at in a listing; it
            belongs in the form proper. */}
        <div className="field">
          <label htmlFor="poster">Poster</label>
          <input
            id="poster"
            className="input"
            type="file"
            // The one allowlist, from the shared package — the server checks
            // the same set and a divergent literal here would only produce a
            // file picker that offers formats the upload then refuses.
            accept={ACCEPTED_IMAGE_TYPES.join(",")}
            onChange={(e) => setPoster(e.target.files?.[0] ?? null)}
          />
          <p className="form-note">
            {poster
              ? `${poster.name} — uploaded straight to storage once the show is posted.`
              : "Optional. Uploaded straight to storage — it never passes through our servers."}
          </p>
        </div>

        <div className="two-column">
          <div className="field">
            <label htmlFor="date">Date</label>
            <input
              id="date"
              className="input"
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="time">First set</label>
            <input
              id="time"
              className="input"
              type="time"
              value={time}
              onChange={(e) => setTime(e.target.value)}
              required
            />
          </div>
        </div>
      </div>

      <Rule />

      <button
        type="button"
        className="btn btn-ghost"
        onClick={() => setShowMore((open) => !open)}
        aria-expanded={showMore}
        style={{ width: "100%", justifyContent: "space-between" }}
      >
        <span>Add the details</span>
        <span className="kicker">{showMore ? "Hide" : "Open"}</span>
      </button>

      {showMore ? (
        <div className="stack" style={{ paddingTop: "var(--space-4)" }}>

          <div className="two-column">
            <div className="field">
              <label htmlFor="price">Door price</label>
              <input
                id="price"
                className="input"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                placeholder="10, or Free"
                inputMode="decimal"
              />
            </div>
            <div className="field">
              <label htmlFor="ages">Ages</label>
              <select
                id="ages"
                className="input"
                value={ages}
                onChange={(e) => setAges(e.target.value as AgeRestriction)}
              >
                {AGE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="field">
            <label htmlFor="ticket-url">Ticket link</label>
            <input
              id="ticket-url"
              className="input"
              type="url"
              value={ticketUrl}
              onChange={(e) => setTicketUrl(e.target.value)}
              placeholder="https://dice.fm/event/…"
              maxLength={500}
              autoComplete="off"
              spellCheck={false}
            />
            <p className="form-note">
              Where tickets are actually sold — the venue&rsquo;s box office, or
              your ticketing page. Readers are sent straight there; nothing is
              sold here.
            </p>
          </div>

          <div className="field">
            <label htmlFor="genre">Genre</label>
            <select
              id="genre"
              className="input"
              value={genre}
              onChange={(e) => setGenre(e.target.value as Genre)}
            >
              {GENRES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label htmlFor="neighborhood">Neighbourhood</label>
            <input
              id="neighborhood"
              className="input"
              value={neighborhood}
              onChange={(e) => setNeighborhood(e.target.value)}
              placeholder="Olneyville"
              maxLength={120}
            />
          </div>

          <div className="field">
            <label htmlFor="note">A line for the paper</label>
            <textarea
              id="note"
              className="input"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="One sentence. Who you sound like, what the room will be."
              maxLength={300}
            />
          </div>
        </div>
      ) : null}

      <Rule />

      <p className="kicker">How it will read</p>
      <div className="rule-strong" style={{ marginTop: "4px" }} />
      <div className="listing" style={{ cursor: "default" }}>
        <span className="listing-time">{time || "—:—"}</span>
        <span className="listing-body">
          <span className="listing-artist">{headline.trim() || "Your band"}</span>
          <span className="listing-meta">
            <span className="italic">
              {GENRES.find((option) => option.value === genre)?.label}
            </span>
            {venueName.trim() ? ` · ${venueName.trim()}` : " · Venue"}
          </span>
        </span>
        <span className="listing-right">
          <span className="listing-price">
            {priceCents === undefined ? "—" : priceCents === 0 ? "Free" : `$${priceCents / 100}`}
          </span>
        </span>
      </div>

      <button
        type="submit"
        className="btn btn-primary btn-block"
        disabled={submitting}
        style={{ marginTop: "var(--space-4)" }}
      >
        {submitting ? "Sending…" : "Send it to press"}
      </button>
    </form>
  );
}
