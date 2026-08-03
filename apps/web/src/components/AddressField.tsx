/**
 * An address field with suggestions from the geocoding proxy.
 *
 * Three things it has to get right:
 *
 * 1. **It degrades to a plain text field.** If LocationIQ has no key, or is
 *    down, the response comes back `configured: false` or simply empty — and
 *    typing an address by hand still works. An address field that stops
 *    accepting text because a third party is unreachable is worse than no
 *    autocomplete at all.
 * 2. **Keyboard first.** Arrow keys, Enter and Escape all work, and the
 *    listbox is wired up with the ARIA combobox roles so a screen reader
 *    announces the suggestions rather than silently swallowing them.
 * 3. **It does not fire on every keystroke.** Debounced, and the server caches
 *    on top of that — the free tier is 5,000 lookups a day.
 */

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { MapPin } from "lucide-react";
import { queryString, type Place, type PlaceSearchResult } from "@live-msc/shared";

import { api } from "../lib/api";

interface AddressFieldProps {
  id?: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** Fired when a suggestion is chosen, with the full place including coords. */
  onSelect: (place: Place) => void;
  placeholder?: string;
  note?: string;
  required?: boolean;
  /** Comma-separated ISO codes, e.g. "us" — narrows results usefully. */
  countries?: string;
  maxLength?: number;
}

const DEBOUNCE_MS = 280;
const MIN_QUERY = 3;

export function AddressField({
  id,
  label,
  value,
  onChange,
  onSelect,
  placeholder,
  note,
  required = false,
  countries,
  maxLength = 300,
}: AddressFieldProps) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  const listId = `${fieldId}-suggestions`;

  const [places, setPlaces] = useState<Place[]>([]);
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(-1);
  const [searching, setSearching] = useState(false);

  // Set once the server says LocationIQ has no key. The field then behaves as
  // a plain input and stops asking.
  const [unavailable, setUnavailable] = useState(false);

  // Suppresses the lookup that a selection's own onChange would otherwise
  // trigger — picking a suggestion should not immediately re-search for it.
  const skipNextLookup = useRef(false);
  const generation = useRef(0);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (unavailable) return;
    if (skipNextLookup.current) {
      skipNextLookup.current = false;
      return;
    }

    const term = value.trim();
    if (term.length < MIN_QUERY) {
      setPlaces([]);
      setOpen(false);
      // Cleared here too: deleting back below the minimum used to leave the
      // live region announcing "Searching addresses" indefinitely.
      setSearching(false);
      return;
    }

    const current = ++generation.current;
    setSearching(true);
    const timer = setTimeout(() => {
      void api
        .get<PlaceSearchResult>(
          `/api/v1/geocode/autocomplete${queryString({ q: term, countries })}`,
        )
        .then((result) => {
          // A slower earlier request must never overwrite a newer one.
          if (generation.current !== current) return;
          setSearching(false);
          if (!result.ok || !result.data) return;
          if (!result.data.configured) {
            setUnavailable(true);
            return;
          }
          setPlaces(result.data.places);
          setOpen(result.data.places.length > 0);
          setHighlighted(-1);
        });
    }, DEBOUNCE_MS);

    return () => {
      clearTimeout(timer);
      // Unconditionally: a superseded request's "Searching" status must not
      // outlive it. If a newer run is starting it sets the flag again on the
      // very next line of its own body, so there is no flicker.
      setSearching(false);
    };
  }, [value, countries, unavailable]);

  // Close on an outside click, the way a combobox is expected to behave.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  const choose = useCallback(
    (place: Place) => {
      skipNextLookup.current = true;
      onChange(place.name || place.label);
      onSelect(place);
      setOpen(false);
      setPlaces([]);
      setHighlighted(-1);
    },
    [onChange, onSelect],
  );

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || places.length === 0) return;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlighted((index) => (index + 1) % places.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlighted((index) => (index <= 0 ? places.length - 1 : index - 1));
    } else if (event.key === "Enter" && highlighted >= 0) {
      // Only intercept Enter when a suggestion is actually highlighted, so it
      // still submits the form otherwise.
      event.preventDefault();
      choose(places[highlighted]!);
    } else if (event.key === "Escape") {
      setOpen(false);
      setHighlighted(-1);
    }
  }

  return (
    <div className="field address-field" ref={containerRef}>
      <label htmlFor={fieldId}>{label}</label>
      <div className="address-input" role="combobox" aria-expanded={open} aria-owns={listId}
           aria-haspopup="listbox">
        <MapPin size={15} aria-hidden />
        <input
          id={fieldId}
          className="input"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
          onFocus={() => places.length > 0 && setOpen(true)}
          placeholder={placeholder}
          maxLength={maxLength}
          required={required}
          autoComplete="off"
          aria-autocomplete="list"
          aria-controls={listId}
          aria-activedescendant={
            highlighted >= 0 ? `${fieldId}-option-${highlighted}` : undefined
          }
        />
      </div>

      {open && places.length > 0 ? (
        <ul className="suggestions" id={listId} role="listbox" aria-label="Address suggestions">
          {places.map((place, index) => (
            <li
              key={`${place.label}-${index}`}
              id={`${fieldId}-option-${index}`}
              role="option"
              aria-selected={index === highlighted}
              className={index === highlighted ? "suggestion is-highlighted" : "suggestion"}
              // onMouseDown, not onClick: a click fires after the input's blur
              // has already closed the list.
              onMouseDown={(event) => {
                event.preventDefault();
                choose(place);
              }}
              onMouseEnter={() => setHighlighted(index)}
            >
              <span className="suggestion-name">{place.name || place.label}</span>
              <span className="suggestion-detail">{place.label}</span>
            </li>
          ))}
        </ul>
      ) : null}

      {/* Announced politely so a screen reader hears that results arrived. */}
      <span className="sr-only" role="status" aria-live="polite">
        {searching
          ? "Searching addresses"
          : open
            ? `${places.length} address suggestion${places.length === 1 ? "" : "s"}`
            : ""}
      </span>

      {note ? <p className="form-note">{note}</p> : null}
    </div>
  );
}
