/**
 * The Plan — what is on near you, on an actual map.
 *
 * The prototype drew its own ground: a CSS grid with pins projected onto it by
 * percentage. It was handsome and it was useless — the relative geography was
 * real but there were no streets, so a reader could not tell which of two pins
 * was the walkable one. This page now renders a real basemap (see
 * `components/PlanMap.tsx`, which also carries the privacy note about tile
 * requests) and the listing below it stays the text equivalent of what is
 * drawn.
 *
 * The viewport drives the query. Panning or zooming re-asks the API for that
 * frame, so the map works wherever the reader is rather than only within five
 * miles of a hard-coded centre.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { queryString, type EventListing } from "@live-msc/shared";

import { Empty, Notice, SectionHead, Spinner } from "../components/Primitives";
import { PlanMap, type Viewport } from "../components/PlanMap";
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
const DEFAULT_RADIUS_MILES = 5;

export function PlanPage() {
  const navigate = useNavigate();
  const [origin, setOrigin] = useState(FALLBACK);
  const [originIsReader, setOriginIsReader] = useState(false);
  const [locating, setLocating] = useState(false);
  const [locationNote, setLocationNote] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);

  // What the map is currently looking at. Separate from `origin`: the reader's
  // position anchors the distance labels, the viewport decides what is asked
  // for. Rounded, so a one-pixel drag is not a new cache key.
  const [viewport, setViewport] = useState<Viewport>({
    ...FALLBACK,
    radiusMiles: DEFAULT_RADIUS_MILES,
  });

  const { data, error, loading } = useResource<NearbyResponse>(
    () =>
      api.get<NearbyResponse>(
        `/api/v1/events/nearby${queryString({
          latitude: viewport.latitude,
          longitude: viewport.longitude,
          radius_miles: viewport.radiusMiles,
        })}`,
      ),
    [viewport.latitude, viewport.longitude, viewport.radiusMiles],
  );

  // The last rendered set. A pan mid-flight would otherwise blank the map and
  // the listing until the new response lands, which reads as a broken page.
  const lastEvents = useRef<EventListing[]>([]);
  if (data) lastEvents.current = data.events;
  const events = data?.events ?? lastEvents.current;

  const onViewportChange = useCallback((next: Viewport) => {
    setViewport((current) => {
      const moved =
        Math.abs(current.latitude - next.latitude) > 1e-4 ||
        Math.abs(current.longitude - next.longitude) > 1e-4 ||
        Math.abs(current.radiusMiles - next.radiusMiles) > 0.05;
      return moved ? next : current;
    });
  }, []);

  const useMyLocation = () => {
    if (!("geolocation" in navigator)) {
      setLocationNote("This browser cannot share a location.");
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const here = {
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        };
        setOrigin(here);
        setOriginIsReader(true);
        setViewport({ ...here, radiusMiles: DEFAULT_RADIUS_MILES });
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

  // Clear the highlight when the pointer leaves the listing entirely, so a pin
  // is not left lit after the reader has moved on.
  useEffect(() => {
    if (!activeId) return;
    const clear = () => setActiveId(null);
    window.addEventListener("blur", clear);
    return () => window.removeEventListener("blur", clear);
  }, [activeId]);

  const radiusLabel = data
    ? `${data.count} within ${Math.round(data.radius_miles)} miles`
    : "Shows near you";

  return (
    <div className="page">
      <div className="section-head" style={{ marginTop: 0 }}>
        <div>
          <h1 className="page-title">The Plan</h1>
          <p className="page-sub">{radiusLabel}</p>
        </div>
        <button type="button" className="btn btn-secondary" onClick={useMyLocation}>
          {locating ? "Locating…" : "Use my location"}
        </button>
      </div>

      {locationNote ? <Notice>{locationNote}</Notice> : null}
      {error ? <Notice tone="error">{error}</Notice> : null}

      <PlanMap
        events={events}
        origin={origin}
        originIsReader={originIsReader}
        activeId={activeId}
        onActivate={setActiveId}
        onOpen={(id) => navigate(`/shows/${id}`)}
        onViewportChange={onViewportChange}
      />

      <p className="form-note" style={{ marginTop: "var(--space-2)" }}>
        Drag or zoom the map to look somewhere else.
      </p>

      <SectionHead title="Nearest first" count="Next fourteen days" />

      {loading && !data ? <Spinner /> : null}

      {events.map((event) => (
        <button
          key={event.id}
          type="button"
          className="listing"
          onClick={() => navigate(`/shows/${event.id}`)}
          onMouseEnter={() => setActiveId(event.id)}
          onMouseLeave={() => setActiveId(null)}
          onFocus={() => setActiveId(event.id)}
          onBlur={() => setActiveId(null)}
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
        <Empty>Nothing in this part of the map for the next fortnight.</Empty>
      ) : null}
    </div>
  );
}
