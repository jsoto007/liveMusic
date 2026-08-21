/** Post a classified: what you need, where, when, and what it pays. */

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { Genre, Gig } from "@live-msc/shared";
import { GENRES } from "@live-msc/shared";

import { Notice, Spinner } from "../components/Primitives";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";

export function PostGigPage() {
  const { user, initializing } = useAuth();
  const navigate = useNavigate();

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [city, setCity] = useState(user?.home_city ?? "");
  const [neighborhood, setNeighborhood] = useState("");
  const [venueName, setVenueName] = useState("");
  const [when, setWhen] = useState("");
  const [pay, setPay] = useState("");
  const [payNote, setPayNote] = useState("");
  const [genre, setGenre] = useState<Genre | "">("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (initializing) return <div className="page page-narrow"><Spinner /></div>;

  if (!user) {
    return (
      <div className="page page-narrow">
        <h1 className="page-title">Post a gig</h1>
        <Notice>Sign in to put a classified on the board.</Notice>
        <Link className="btn btn-primary" to="/sign-in">Sign in</Link>
      </div>
    );
  }

  const submit = async () => {
    setError(null);

    let payCents: number | undefined;
    if (pay.trim()) {
      const dollars = Number(pay.replace(/[$,\s]/g, ""));
      if (!Number.isFinite(dollars) || dollars < 0) {
        setError("Pay should be a dollar amount, or left blank.");
        return;
      }
      payCents = Math.round(dollars * 100);
    }

    let startsAt: string | undefined;
    if (when) {
      const parsed = new Date(when);
      if (Number.isNaN(parsed.getTime())) {
        setError("That date didn’t parse.");
        return;
      }
      startsAt = parsed.toISOString();
    }

    setBusy(true);
    const result = await api.post<{ gig: Gig }>("/api/v1/gigs", {
      title: title.trim(),
      description: description.trim(),
      city: city.trim(),
      neighborhood: neighborhood.trim() || undefined,
      venue_name: venueName.trim() || undefined,
      starts_at: startsAt,
      timezone: startsAt
        ? Intl.DateTimeFormat().resolvedOptions().timeZone
        : undefined,
      pay_cents: payCents,
      pay_note: payNote.trim() || undefined,
      genre: genre || undefined,
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    navigate(`/gigs/${result.data.gig.id}`);
  };

  return (
    <div className="page page-narrow">
      <h1 className="page-title">Post a gig</h1>
      <p className="page-sub">A classified for the musicians reading this paper</p>

      <div className="stack">
        <label className="field">
          What you need
          <input
            className="input"
            maxLength={160}
            placeholder="Jazz trio wanted for Friday residency"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>

        <label className="field">
          The details
          <textarea
            className="input"
            rows={5}
            maxLength={4000}
            placeholder="Sets, gear, the room, how to impress you…"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </label>

        <div className="filter-row">
          <label className="field" style={{ flex: 1 }}>
            City
            <input
              className="input"
              maxLength={120}
              value={city}
              onChange={(event) => setCity(event.target.value)}
            />
          </label>
          <label className="field" style={{ flex: 1 }}>
            Neighborhood
            <input
              className="input"
              maxLength={120}
              value={neighborhood}
              onChange={(event) => setNeighborhood(event.target.value)}
            />
          </label>
        </div>

        <label className="field">
          Venue (if there is one)
          <input
            className="input"
            maxLength={160}
            value={venueName}
            onChange={(event) => setVenueName(event.target.value)}
          />
        </label>

        <label className="field">
          When (leave blank for “ongoing”)
          <input
            className="input"
            type="datetime-local"
            value={when}
            onChange={(event) => setWhen(event.target.value)}
          />
        </label>

        <div className="filter-row">
          <label className="field" style={{ flex: 1 }}>
            Pay, in dollars
            <input
              className="input"
              inputMode="decimal"
              placeholder="300"
              value={pay}
              onChange={(event) => setPay(event.target.value)}
            />
          </label>
          <label className="field" style={{ flex: 2 }}>
            Pay note
            <input
              className="input"
              maxLength={140}
              placeholder="plus door split"
              value={payNote}
              onChange={(event) => setPayNote(event.target.value)}
            />
          </label>
        </div>

        <div className="chip-row" role="group" aria-label="Genre wanted">
          {GENRES.map((option) => (
            <button
              key={option.value}
              type="button"
              className="chip"
              aria-pressed={genre === option.value}
              onClick={() =>
                setGenre(genre === option.value ? "" : option.value)
              }
            >
              {option.label}
            </button>
          ))}
        </div>

        {error ? <Notice tone="error">{error}</Notice> : null}

        <div className="actions">
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy || !title.trim() || !description.trim() || !city.trim()}
            onClick={() => void submit()}
          >
            Put it on the board
          </button>
          <Link className="btn btn-ghost" to="/classifieds">Never mind</Link>
        </div>
      </div>
    </div>
  );
}
