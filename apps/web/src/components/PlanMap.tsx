/**
 * The Plan's map.
 *
 * A real slippy map — Leaflet over a raster basemap — replacing the drawn grid
 * the prototype used. The grid read as decoration: a reader could see that six
 * shows existed but not which street any of them was on, which is the one
 * question a map is for.
 *
 * Two consequences of using a tile host, stated plainly because the earlier
 * comment claimed the opposite:
 *
 *   * The tile host sees the viewport. It does NOT see the reader's precise
 *     position — geolocation stays in the browser and only ever reaches our
 *     own API — but the requested tiles do disclose roughly where the map is
 *     looking. That is the price of a legible map and it is worth naming.
 *   * Tiles are images from another origin, so the CSP `img-src` has to admit
 *     the host. `MAP_TILE_ORIGINS` in `apps/server/app/security.py` is the
 *     server-side half of this and must be kept in step with `TILE_URL`.
 *
 * The basemap is CARTO Positron: a pale, low-chroma cartography that sits
 * under the Classical ground without fighting it, and needs no API key. Swap
 * `TILE_URL`/`TILE_ATTRIBUTION` (and the server constant) to change provider.
 *
 * Leaflet is driven imperatively rather than through react-leaflet. The map is
 * a mutable object with its own lifecycle; wrapping it in a component tree
 * that re-renders on every hover buys nothing and costs a dependency.
 */

import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { EventListing } from "@live-msc/shared";

import { stockPosterUrl } from "../lib/stock";

export const TILE_URL = "https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png";
export const TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, ' +
  '&copy; <a href="https://carto.com/attributions">CARTO</a>';

/** Leaflet's own cap for this basemap. Past it the host serves nothing. */
const MAX_ZOOM = 19;
const DEFAULT_ZOOM = 13;

/** The server rejects anything outside this, so never ask for it. */
const MAX_RADIUS_MILES = 50;
const MIN_RADIUS_MILES = 0.25;

const METRES_PER_MILE = 1609.344;

/** Below this, a container reading isn't a real layout yet — see `attemptFrame`. */
const MIN_USABLE_PX = 40;

export interface Viewport {
  latitude: number;
  longitude: number;
  radiusMiles: number;
}

interface PlanMapProps {
  events: EventListing[];
  /** Where the reader is (or the fallback centre until they say). */
  origin: { latitude: number; longitude: number };
  /** True once the reader has actually shared a position. */
  originIsReader: boolean;
  activeId: string | null;
  onActivate: (id: string | null) => void;
  onOpen: (id: string) => void;
  /** Fired after the reader pans or zooms, debounced. */
  onViewportChange: (viewport: Viewport) => void;
}

/** The radius that covers the visible frame, clamped to what the API accepts. */
function radiusFor(map: L.Map): number {
  const bounds = map.getBounds();
  const metres = map.distance(bounds.getCenter(), bounds.getNorthEast());
  const miles = metres / METRES_PER_MILE;
  return Math.min(MAX_RADIUS_MILES, Math.max(MIN_RADIUS_MILES, Number(miles.toFixed(2))));
}

function pinIcon(event: EventListing, active: boolean): L.DivIcon {
  // `.mappin` is the same class the drawn plan used, so the numbered disc is
  // unchanged — only the ground beneath it is real now.
  const label = String(event.pin_number ?? "");
  return L.divIcon({
    className: "mappin-wrap",
    html: `<span class="mappin" aria-hidden="true"${active ? ' data-active="true"' : ""}>${label}</span>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
  });
}

const POPUP_OPEN_ATTR = "data-mappopup-open";

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/**
 * The popup is what a click resolves to now — a card the reader can dismiss
 * to keep looking at the map, or press through to the real page. It is raw
 * HTML because Leaflet owns this DOM, not React; every field that came from
 * a band's own submission is escaped before it lands in the string.
 */
function popupHtml(event: EventListing): string {
  const meta = [event.day_label, event.time_label].filter(Boolean).join(" · ");
  const priceLine = [event.price_label, event.distance_label].filter(Boolean).join(" · ");
  // A missing poster falls back to the genre's house stock, same as the rows.
  const posterUrl = event.poster_url ?? stockPosterUrl(event.genre);
  const image = `<div class="mappopup-plate plate"><img src="${escapeHtml(posterUrl)}" alt="" /></div>`;
  const credit = event.poster_credit
    ? `<p class="mappopup-credit">${escapeHtml(event.poster_credit)}</p>`
    : "";
  return `
    <div class="mappopup-card">
      ${image}
      ${credit}
      <div class="mappopup-body">
        <p class="mappopup-headline">${escapeHtml(event.headline)}</p>
        ${event.venue ? `<p class="mappopup-meta">${escapeHtml(event.venue.name)}</p>` : ""}
        ${meta ? `<p class="mappopup-meta">${escapeHtml(meta)}</p>` : ""}
        ${priceLine ? `<p class="mappopup-meta">${escapeHtml(priceLine)}</p>` : ""}
        <button type="button" class="btn btn-secondary mappopup-open" ${POPUP_OPEN_ATTR}="${escapeHtml(event.id)}">
          View full details
        </button>
      </div>
    </div>
  `;
}

export function PlanMap({
  events,
  origin,
  originIsReader,
  activeId,
  onActivate,
  onOpen,
  onViewportChange,
}: PlanMapProps) {
  const holder = useRef<HTMLDivElement | null>(null);
  const map = useRef<L.Map | null>(null);
  const markers = useRef(new Map<string, L.Marker>());
  const originMarker = useRef<L.CircleMarker | null>(null);

  // A move the code made must not be reported back as a move the reader made,
  // or recentring on their location would trigger a refetch that recentres
  // again. A window rather than a one-shot flag, because a single `setView`
  // or `fitBounds` emits both `moveend` and `zoomend`: a boolean consumed by
  // the first left the second to fire a redundant query on every page load.
  const suppressUntil = useRef(0);
  const suppress = () => {
    suppressUntil.current = Date.now() + 600;
  };
  const settleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hasFramed = useRef(false);
  // Bounds waiting to be framed once the container's size has stopped
  // changing. A `useEffect` running is no proof the browser has finished a
  // layout pass — a flex column can still be widening across several
  // frames — and fitting against a size that is merely *non-zero*, rather
  // than *settled*, is how a fit against a 40px-wide sliver quietly commits
  // to a zoom that only fills the left corner of the eventual 900px map.
  // `attemptFrame`, set by the mount effect below, polls until two
  // consecutive readings agree before it actually fits.
  const pendingFrame = useRef<L.LatLngBounds | null>(null);
  const attemptFrame = useRef<(() => void) | null>(null);

  // Latest callbacks, read from inside Leaflet handlers that are bound once.
  const handlers = useRef({ onViewportChange, onActivate, onOpen });
  handlers.current = { onViewportChange, onActivate, onOpen };

  // ── Create the map, once ───────────────────────────────────────────────
  useEffect(() => {
    if (map.current || !holder.current) return;
    // Captured now rather than read as `markers.current` inside the cleanup:
    // by teardown the ref could point at a different registry, and clearing
    // the wrong one would leave every marker of the old map attached.
    const registry = markers.current;

    const instance = L.map(holder.current, {
      center: [origin.latitude, origin.longitude],
      zoom: DEFAULT_ZOOM,
      // A page-embedded map that eats the wheel traps the reader mid-scroll.
      // Pinch, drag, double-click and the +/- buttons all still zoom.
      scrollWheelZoom: false,
      zoomControl: true,
      attributionControl: true,
    });

    L.tileLayer(TILE_URL, {
      attribution: TILE_ATTRIBUTION,
      maxZoom: MAX_ZOOM,
      detectRetina: true,
    }).addTo(instance);

    // Bottom LEFT: the attribution control owns the bottom right, and two
    // boxes on the same corner overlap at narrow widths.
    L.control.scale({ imperial: true, metric: false, position: "bottomleft" }).addTo(instance);

    // Delegated, once, on the map's own container — never on a popup's
    // button directly. A marker whose data refreshes calls
    // `setPopupContent`, which replaces the popup's inner HTML wholesale
    // (Leaflet rebuilds it via `innerHTML =`); a listener attached to that
    // button in a `popupopen` handler is destroyed along with it, silently,
    // the next time the listing refreshes while the popup happens to be
    // open. Delegating to the container, which outlives every popup it
    // hosts, means the button's identity never has to be tracked at all.
    instance.getContainer().addEventListener("click", (domEvent) => {
      const target = (domEvent.target as HTMLElement | null)?.closest<HTMLElement>(
        `[${POPUP_OPEN_ATTR}]`,
      );
      const id = target?.getAttribute(POPUP_OPEN_ATTR);
      if (id) handlers.current.onOpen(id);
    });

    instance.on("moveend zoomend", () => {
      if (Date.now() < suppressUntil.current) return;
      if (settleTimer.current) clearTimeout(settleTimer.current);
      // Debounced: a drag fires `moveend` once, but a pinch-zoom on a phone
      // fires several, and each one would be a query.
      settleTimer.current = setTimeout(() => {
        const centre = instance.getCenter();
        handlers.current.onViewportChange({
          latitude: centre.lat,
          longitude: centre.lng,
          radiusMiles: radiusFor(instance),
        });
      }, 400);
    });

    map.current = instance;

    let pollHandle: number | null = null;
    let cancelled = false;

    // Poll rather than trust a single resize signal: the container can grow
    // across several frames — a flex column whose width is not resolved yet,
    // a webfont swap, the app shell's own first paint, even the surrounding
    // page still settling after navigation — and a fit against a size that
    // merely exists, rather than one that has stopped changing, is how a
    // 40px-wide reading quietly commits the whole framing to a corner of the
    // eventual map. Two equal, real readings back to back is "stopped".
    const pollForStableSize = (previous: L.Point | null, streak: number) => {
      if (cancelled || !pendingFrame.current) return;
      instance.invalidateSize();
      const size = instance.getSize();
      const usable = size.x >= MIN_USABLE_PX && size.y >= MIN_USABLE_PX;
      const stable = usable && previous != null && size.equals(previous);

      if (stable) {
        suppress();
        instance.fitBounds(pendingFrame.current, { maxZoom: DEFAULT_ZOOM + 2 });
        pendingFrame.current = null;
        return;
      }

      // A cap rather than an unbounded poll: past ~5s the container is not
      // going to settle on its own and holding the initial centre is better
      // than polling forever.
      if (streak > 300) return;
      pollHandle = requestAnimationFrame(() => pollForStableSize(usable ? size : null, streak + 1));
    };

    attemptFrame.current = () => {
      if (pollHandle != null) cancelAnimationFrame(pollHandle);
      pollForStableSize(null, 0);
    };

    // Leaflet measures the container on creation. Inside a layout that is
    // still settling it can read zero and render one grey tile forever. A
    // resize observer keeps Leaflet's cached size honest for as long as the
    // map lives, not just once on mount, and kicks the poll above awake
    // whenever the container's size actually moves.
    const observer = new ResizeObserver(() => {
      instance.invalidateSize();
      attemptFrame.current?.();
    });
    observer.observe(holder.current);

    // Belt and suspenders: a resize observer fires on a change to the
    // container's own box, but the page around it can still be settling in
    // ways that never register as one — a web font swapping in and
    // reflowing a sibling, the app shell finishing its own first paint. Keep
    // Leaflet's tile coverage in step with the container for the first few
    // seconds regardless, so a reader never lands on a map with pins framed
    // correctly but half the tiles still grey.
    let syncTicks = 0;
    const syncInterval = setInterval(() => {
      instance.invalidateSize();
      if (++syncTicks >= 10) clearInterval(syncInterval);
    }, 300);

    return () => {
      cancelled = true;
      if (pollHandle != null) cancelAnimationFrame(pollHandle);
      clearInterval(syncInterval);
      observer.disconnect();
      if (settleTimer.current) clearTimeout(settleTimer.current);
      instance.remove();
      map.current = null;
      registry.clear();
      originMarker.current = null;
      pendingFrame.current = null;
      attemptFrame.current = null;
    };
    // Deliberately once: `origin` here is only the initial centre. Later
    // changes are handled by the effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Recentre when the reader shares a location ─────────────────────────
  useEffect(() => {
    const instance = map.current;
    if (!instance || !originIsReader) return;

    suppress();
    instance.setView([origin.latitude, origin.longitude], DEFAULT_ZOOM);

    if (originMarker.current) {
      originMarker.current.setLatLng([origin.latitude, origin.longitude]);
    } else {
      originMarker.current = L.circleMarker([origin.latitude, origin.longitude], {
        radius: 5,
        className: "maphere",
        interactive: false,
      }).addTo(instance);
    }
  }, [origin.latitude, origin.longitude, originIsReader]);

  // ── Reconcile markers with the listings ────────────────────────────────
  useEffect(() => {
    const instance = map.current;
    if (!instance) return;

    const located = events.filter(
      (event) => event.venue?.latitude != null && event.venue?.longitude != null,
    );
    const wanted = new Set(located.map((event) => event.id));

    for (const [id, marker] of markers.current) {
      if (!wanted.has(id)) {
        marker.remove();
        markers.current.delete(id);
      }
    }

    for (const event of located) {
      const position: L.LatLngExpression = [event.venue!.latitude!, event.venue!.longitude!];
      const title = `${event.pin_number}. ${event.headline} at ${event.venue!.name}`;
      const existing = markers.current.get(event.id);

      if (existing) {
        existing.setLatLng(position);
        existing.setIcon(pinIcon(event, activeId === event.id));
        existing.setPopupContent(popupHtml(event));
        continue;
      }

      const marker = L.marker(position, {
        icon: pinIcon(event, activeId === event.id),
        // Tab-reachable, and announced as what it is rather than as a bare
        // number floating on a map.
        keyboard: true,
        title,
        alt: title,
        riseOnHover: true,
      })
        .addTo(instance)
        .bindTooltip(title, { direction: "top", offset: [0, -14] })
        .bindPopup(popupHtml(event), { className: "mappopup", maxWidth: 240, minWidth: 220 })
        .on("mouseover focus", () => handlers.current.onActivate(event.id))
        .on("mouseout blur", () => handlers.current.onActivate(null))
        // A click opens the popup (Leaflet's default for a bound popup); it
        // also lights up the matching row in the listing below, same as a
        // hover does. The popup's own close button — or a click elsewhere on
        // the map, which Leaflet closes it on by default — hands the map
        // back without leaving the page.
        .on("click", () => handlers.current.onActivate(event.id))
        .on("keypress", (domEvent) => {
          const key = (domEvent as L.LeafletKeyboardEvent).originalEvent.key;
          if (key === "Enter" || key === " ") marker.openPopup();
        });

      markers.current.set(event.id, marker);
    }

    // Frame the first set that arrives, then leave the view to the reader —
    // refitting on every response would yank the map out from under a pan.
    if (!hasFramed.current && located.length > 0) {
      hasFramed.current = true;
      pendingFrame.current = L.latLngBounds(
        located.map(
          (event) => [event.venue!.latitude!, event.venue!.longitude!] as L.LatLngTuple,
        ),
      ).pad(0.2);
      attemptFrame.current?.();
    }
  }, [events, activeId]);

  // ── Mirror the hovered listing onto its pin ────────────────────────────
  useEffect(() => {
    for (const [id, marker] of markers.current) {
      const element = marker.getElement()?.querySelector(".mappin");
      if (!element) continue;
      if (id === activeId) element.setAttribute("data-active", "true");
      else element.removeAttribute("data-active");
    }
  }, [activeId]);

  return (
    <div
      ref={holder}
      className="mapframe"
      // The map is interactive, so it is not an image; the listing below it is
      // the text equivalent and is what a screen reader should read.
      role="application"
      aria-label={`Map of ${events.length} nearby shows. The same shows are listed below.`}
    />
  );
}
