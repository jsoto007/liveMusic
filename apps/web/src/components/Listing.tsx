/**
 * A row on the bill.
 *
 * Three columns — time, act, price — with the time and price set tabular so a
 * column of them lines up as figures. Every label comes from the server so the
 * web and mobile listings read identically.
 */

import { useNavigate } from "react-router-dom";
import type { DaySection, EventListing } from "@live-msc/shared";

import { fallBackToStock, stockPosterUrl } from "../lib/stock";
import { SectionHead } from "./Primitives";

export function ListingRow({
  event,
  showNote = true,
}: {
  event: EventListing;
  showNote?: boolean;
}) {
  const navigate = useNavigate();
  const venue = event.venue;

  // The row's text is split across nested spans for layout, which leaves the
  // computed accessible name unreliable. Spell it out so a screen reader hears
  // one coherent listing rather than a run of fragments.
  const spokenLabel = [
    event.headline,
    event.genre_label,
    venue ? `at ${venue.name}` : null,
    `${event.day_label} ${event.time_label ?? ""}`.trim(),
    event.price_label ?? "price not stated",
    event.age_label,
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <button
      type="button"
      className="listing"
      aria-label={spokenLabel}
      onClick={() => navigate(`/shows/${event.id}`)}
    >
      <span className="listing-time">{event.time_label ?? "—"}</span>
      <span className="listing-plate" aria-hidden="true">
        {/* No uploaded poster prints the genre's house stock, so a row never
            runs without a photograph. */}
        <img
          src={event.poster_url ?? stockPosterUrl(event.genre)}
          alt=""
          loading="lazy"
          onError={(imgEvent) => fallBackToStock(imgEvent, event.genre)}
        />
      </span>
      <span className="listing-body">
        <span className="listing-artist">{event.headline}</span>
        <span className="listing-meta">
          <span className="italic">{event.genre_label}</span>
          {venue ? ` · ${venue.name}` : null}
          {venue?.neighborhood ? `, ${venue.neighborhood}` : null}
        </span>
        {showNote && event.short_line ? (
          <span className="listing-note">{event.short_line}</span>
        ) : null}
      </span>
      <span className="listing-right">
        {/* A stated price prints; an unstated one leaves the column empty
            rather than claiming the show is free. */}
        <span className="listing-price">{event.price_label ?? "—"}</span>
        <span className="listing-ages">{event.age_label}</span>
      </span>
    </button>
  );
}

export function DaySections({ sections }: { sections: DaySection[] }) {
  return (
    <>
      {sections.map((section) => (
        <section key={section.key}>
          <SectionHead title={section.label} count={section.count_label} />
          {section.events.map((event) => (
            <ListingRow key={event.id} event={event} />
          ))}
        </section>
      ))}
    </>
  );
}
