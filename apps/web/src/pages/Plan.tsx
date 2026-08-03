/**
 * The Plan — what is on near you, drawn rather than mapped.
 *
 * The pins are positioned by projecting the venue coordinates into the frame,
 * so their relative geography is real even though the ground is a drawn grid
 * rather than a tile server. Nothing is fetched from a third-party map host,
 * which keeps the reader's location out of anyone else's logs.
 */

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { queryString, type EventListing } from "@live-msc/shared";

import { Empty, Notice, SectionHead, Spinner } from "../components/Primitives";
import { useResource } from "../hooks/useResource";
import { api } from "../lib/api";

interface NearbyResponse {
  events: EventListing[];
  count: number;
  radius_miles: number;
}

// Providence — the city the prototype is set in. Used until the reader shares
// a location, which is asked for rather than taken.
const FALLBACK = { latitude: 41.824, longitude: -71.4128 };

interface Placed {
  event: EventListing;
  left: number;
  top: number;
}

/**
 * Project lat/lon into percentage offsets inside the frame.
 *
 * An equirectangular projection with the longitude span scaled by cos(lat) —
 * over a few miles that is visually indistinguishable from a proper projection
 * and needs no dependency. Padded to 8–92% so a pin at the extreme still sits
 * inside the frame rather than half outside it.
 */
function placePins(events: EventListing[]): Placed[] {
  const located = events.filter(
    (event) => event.venue?.latitude != null && event.venue?.longitude != null,
  );
  if (located.length === 0) return [];

  const lats = located.map((event) => event.venue!.latitude!);
  const lons = located.map((event) => event.venue!.longitude!);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLon = Math.min(...lons);
  const maxLon = Math.max(...lons);

  const latSpan = maxLat - minLat;
  const lonSpan = maxLon - minLon;

  const scale = (value: number, min: number, span: number) =>
    // A single venue (or a perfectly aligned row) gives a zero span; centre it
    // instead of dividing by zero.
    span < 1e-9 ? 50 : 8 + ((value - min) / span) * 84;

  return located.map((event) => ({
    event,
    left: scale(event.venue!.longitude!, minLon, lonSpan),
    // Latitude grows northward but CSS `top` grows downward.
    top: 100 - scale(event.venue!.latitude!, minLat, latSpan),
  }));
}

/**
 * Neighbourhood names, set where their venues actually cluster.
 *
 * Derived from the listings rather than hard-coded, so the map reads as a
 * drawn plan of wherever the reader is — not only of the city the prototype
 * happened to be set in. Each name sits at the centroid of its venues.
 */
function placeLabels(placed: Placed[]): { name: string; left: number; top: number }[] {
  const clusters = new Map<string, { left: number; top: number; count: number }>();

  for (const { event, left, top } of placed) {
    const name = event.venue?.neighborhood;
    if (!name) continue;
    const current = clusters.get(name) ?? { left: 0, top: 0, count: 0 };
    clusters.set(name, {
      left: current.left + left,
      top: current.top + top,
      count: current.count + 1,
    });
  }

  const OFFSET = 10;

  return [...clusters.entries()].map(([name, { left, top, count }]) => {
    const centre = top / count;
    // Normally the name sits above the pins it labels. Near the top edge that
    // would clamp onto them, so it drops below the cluster instead — a label
    // printed over its own pin is worse than one on the other side.
    const above = centre - OFFSET;
    return {
      name,
      left: left / count,
      top: above < 8 ? Math.min(94, centre + OFFSET) : above,
    };
  });
}

export function PlanPage() {
  const navigate = useNavigate();
  const [origin, setOrigin] = useState(FALLBACK);
  const [locating, setLocating] = useState(false);
  const [locationNote, setLocationNote] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);

  const { data, error, loading } = useResource<NearbyResponse>(
    () =>
      api.get<NearbyResponse>(
        `/api/v1/events/nearby${queryString({ ...origin, radius_miles: 5 })}`,
      ),
    [origin.latitude, origin.longitude],
  );

  const pins = useMemo(() => placePins(data?.events ?? []), [data]);
  const labels = useMemo(() => placeLabels(pins), [pins]);

  const useMyLocation = () => {
    if (!("geolocation" in navigator)) {
      setLocationNote("This browser cannot share a location.");
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setOrigin({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        });
        setLocationNote(null);
        setLocating(false);
      },
      () => {
        // A refusal is a legitimate answer, not an error to nag about.
        setLocationNote("Showing the city centre instead.");
        setLocating(false);
      },
      { timeout: 8000, maximumAge: 300_000 },
    );
  };

  return (
    <div className="page">
      <div className="section-head" style={{ marginTop: 0 }}>
        <div>
          <h1 className="page-title">The Plan</h1>
          <p className="page-sub">
            {data ? `${data.count} within ${data.radius_miles} miles` : "Shows near you"}
          </p>
        </div>
        <button type="button" className="btn btn-secondary" onClick={useMyLocation}>
          {locating ? "Locating…" : "Use my location"}
        </button>
      </div>

      {locationNote ? <Notice>{locationNote}</Notice> : null}
      {error ? <Notice tone="error">{error}</Notice> : null}

      <div className="mapframe" role="img" aria-label={`Map of ${pins.length} nearby shows`}>
        <div className="mapframe-grid" />
        {labels.map((label) => (
          <span
            key={label.name}
            className="maplabel"
            style={{ left: `${label.left}%`, top: `${label.top}%` }}
            aria-hidden
          >
            {label.name}
          </span>
        ))}
        {pins.map(({ event, left, top }) => (
          <button
            key={event.id}
            type="button"
            className="mappin"
            style={{ left: `${left}%`, top: `${top}%` }}
            aria-current={activeId === event.id}
            aria-label={`${event.pin_number}. ${event.headline} at ${event.venue?.name}`}
            onMouseEnter={() => setActiveId(event.id)}
            onFocus={() => setActiveId(event.id)}
            onClick={() => navigate(`/shows/${event.id}`)}
          >
            {event.pin_number}
          </button>
        ))}
        <div className="mapscale">
          <span />½ mi
        </div>
      </div>

      <SectionHead title="Nearest first" count="Next fourteen days" />

      {loading && !data ? <Spinner /> : null}

      {data?.events.map((event) => (
        <button
          key={event.id}
          type="button"
          className="listing"
          onClick={() => navigate(`/shows/${event.id}`)}
          onMouseEnter={() => setActiveId(event.id)}
        >
          <span className="listing-time" style={{ color: "var(--color-accent)" }}>
            {event.pin_number}
          </span>
          <span className="listing-body">
            <span className="listing-artist">{event.headline}</span>
            <span className="listing-meta">
              {event.venue?.name} · {event.day_label} {event.time_label}
            </span>
          </span>
          <span className="listing-right">
            <span className="listing-price">{event.distance_label}</span>
          </span>
        </button>
      ))}

      {!loading && data?.count === 0 ? (
        <Empty>Nothing within five miles this fortnight.</Empty>
      ) : null}
    </div>
  );
}
