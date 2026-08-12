/**
 * The Bill — tonight's listings, set as a page.
 *
 * The first published show is given over to the featured plate; everything
 * else falls into the day sections the server grouped.
 */

import { useCallback, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  DAY_FILTERS,
  queryString,
  type BillPage as BillPayload,
  type DayBucket,
  type EventListing,
} from "@live-msc/shared";

import { DaySections } from "../components/Listing";
import { Empty, Notice, Plate, Rule, SaveButton, Spinner } from "../components/Primitives";
import { useAuth } from "../context/AuthContext";
import { useResource } from "../hooks/useResource";
import { api } from "../lib/api";
import { stockPosterUrl } from "../lib/stock";

export function BillPage() {
  const [day, setDay] = useState<"all" | DayBucket>("all");
  const navigate = useNavigate();
  const { user } = useAuth();

  const { data, error, loading, reload } = useResource<BillPayload>(
    () => api.get<BillPayload>(`/api/v1/events${queryString({ day })}`),
    [day],
  );

  const featured = data?.events[0] ?? null;

  // The featured show already has the plate; leaving it in the list too would
  // print the same listing twice on one page.
  const sections = useMemo(() => {
    if (!data) return [];
    if (!featured) return data.sections;
    return data.sections
      .map((section) => ({
        ...section,
        events: section.events.filter((event) => event.id !== featured.id),
      }))
      .filter((section) => section.events.length > 0);
  }, [data, featured]);

  const toggleSave = useCallback(
    async (event: EventListing) => {
      if (!user) {
        navigate("/sign-in");
        return;
      }
      await api.put(`/api/v1/events/${event.id}/interest`, { saved: !event.saved });
      reload();
    },
    [user, navigate, reload],
  );

  return (
    <div className="page">
      <div className="filter-row" role="group" aria-label="Filter by day">
        {DAY_FILTERS.map((option) => (
          <button
            key={option.value}
            type="button"
            className="chip"
            aria-pressed={day === option.value}
            onClick={() => setDay(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
      <Rule strong />

      {error ? <Notice tone="error">{error}</Notice> : null}
      {loading && !data ? <Spinner /> : null}

      {featured ? (
        <section style={{ paddingTop: "var(--space-4)" }}>
          <p className="kicker kicker-accent" style={{ marginBottom: "10px" }}>
            Tonight&rsquo;s pick
          </p>
          <Plate
            src={featured.poster_url}
            fallbackSrc={stockPosterUrl(featured.genre)}
            alt={featured.poster_url ? `Poster for ${featured.headline}` : ""}
            placeholder={`poster / press shot — ${featured.headline}`}
          />
          {featured.poster_credit ? (
            <p className="plate-credit">{featured.poster_credit}</p>
          ) : null}
          <div className="featured-head">
            <div>
              <h2 className="featured-title">{featured.headline}</h2>
              <p className="listing-meta italic" style={{ marginTop: "3px" }}>
                {featured.genre_label}
                {featured.venue ? ` · ${featured.venue.name}` : null}
                {featured.venue?.neighborhood ? `, ${featured.venue.neighborhood}` : null}
              </p>
            </div>
            <div className="featured-time">{featured.time_label}</div>
          </div>
          {featured.short_line ? (
            <p className="prose" style={{ marginTop: "10px" }}>
              {featured.short_line}
            </p>
          ) : null}
          <div className="actions">
            <Link
              className="btn btn-primary"
              to={`/shows/${featured.id}`}
              style={{ flex: 1, minWidth: "150px" }}
            >
              Read the listing
            </Link>
            <SaveButton saved={featured.saved} onToggle={() => void toggleSave(featured)} />
          </div>
          <Rule />
        </section>
      ) : null}

      {!loading && data && data.count === 0 ? (
        <Empty>
          Nothing on the bill for that. Clear a filter, or{" "}
          <Link to="/post">post the show yourself</Link>.
        </Empty>
      ) : (
        <DaySections sections={sections} />
      )}

      <p className="colophon">Set and printed nightly. Corrections to the editor.</p>
    </div>
  );
}
