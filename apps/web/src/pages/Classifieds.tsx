/**
 * The classifieds: gigs wanted, bands for hire, and your own side of both.
 * Three columns of the same page, switched with the segmented control.
 */

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Plus } from "lucide-react";
import type {
  Artist,
  Genre,
  Gig,
  GigApplication,
  GigPage,
} from "@live-msc/shared";
import { GENRES } from "@live-msc/shared";

import { Empty, Notice, SectionHead, Spinner, Tag } from "../components/Primitives";
import { useAuth } from "../context/AuthContext";
import { useResource } from "../hooks/useResource";
import { api } from "../lib/api";

type Column = "gigs" | "hire" | "yours";

export function GigRow({ gig }: { gig: Gig }) {
  const navigate = useNavigate();
  return (
    <button type="button" className="gig-row" onClick={() => navigate(`/gigs/${gig.id}`)}>
      <span className="gig-title">{gig.title}</span>
      <span className="gig-meta">
        {[
          gig.genre_label,
          gig.venue_name,
          gig.neighborhood ? `${gig.neighborhood}, ${gig.city}` : gig.city,
          gig.date_label,
          gig.pay_label ? `pays ${gig.pay_label}` : gig.pay_note,
        ]
          .filter(Boolean)
          .join(" · ")}
        {gig.status === "closed" ? " · closed" : ""}
        {typeof gig.application_count === "number"
          ? ` · ${gig.application_count} application${gig.application_count === 1 ? "" : "s"}`
          : ""}
      </span>
    </button>
  );
}

function GigsColumn() {
  const [city, setCity] = useState("");
  const [genre, setGenre] = useState<Genre | "">("");
  const [query, setQuery] = useState("");

  const params = new URLSearchParams();
  if (city.trim()) params.set("city", city.trim());
  if (genre) params.set("genre", genre);
  if (query.trim()) params.set("q", query.trim());

  const { data, error, loading } = useResource<GigPage>(
    () => api.get<GigPage>(`/api/v1/gigs?${params.toString()}`),
    [city, genre, query],
  );

  return (
    <>
      <div className="filter-row">
        <input
          className="input"
          placeholder="City"
          value={city}
          onChange={(event) => setCity(event.target.value)}
          aria-label="Filter by city"
        />
        <input
          className="input"
          placeholder="Search the board"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-label="Search gigs"
        />
      </div>
      <div className="chip-row" role="group" aria-label="Genre">
        <button
          type="button"
          className="chip"
          aria-pressed={genre === ""}
          onClick={() => setGenre("")}
        >
          All
        </button>
        {GENRES.map((option) => (
          <button
            key={option.value}
            type="button"
            className="chip"
            aria-pressed={genre === option.value}
            onClick={() => setGenre(genre === option.value ? "" : option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>

      {error ? <Notice tone="error">{error}</Notice> : null}
      {loading && !data ? <Spinner /> : null}
      {data && data.total === 0 ? (
        <Empty>Nothing on the board for that. Post the first one.</Empty>
      ) : null}
      {data?.gigs.map((gig) => (
        <GigRow key={gig.id} gig={gig} />
      ))}
    </>
  );
}

function HireColumn() {
  const [city, setCity] = useState("");
  const [query, setQuery] = useState("");

  const params = new URLSearchParams();
  if (city.trim()) params.set("city", city.trim());
  if (query.trim()) params.set("q", query.trim());

  const { data, error, loading } = useResource<{
    artists: Artist[];
    total: number;
  }>(
    () => api.get(`/api/v1/artists/for-hire?${params.toString()}`),
    [city, query],
  );

  return (
    <>
      <div className="filter-row">
        <input
          className="input"
          placeholder="City"
          value={city}
          onChange={(event) => setCity(event.target.value)}
          aria-label="Filter by city"
        />
        <input
          className="input"
          placeholder="Style, name, sounds like…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-label="Search bands for hire"
        />
      </div>

      {error ? <Notice tone="error">{error}</Notice> : null}
      {loading && !data ? <Spinner /> : null}
      {data && data.total === 0 ? (
        <Empty>
          No bands have raised the flag yet. Band accounts flip it on from
          their page under You.
        </Empty>
      ) : null}
      {data?.artists.map((artist) => (
        <Link
          key={artist.id}
          className="person-row"
          to={`/bands/${artist.slug}`}
          style={{ textDecoration: "none", color: "inherit" }}
        >
          <span style={{ minWidth: 0 }}>
            <span className="byline-name">
              {artist.name}
              {artist.verified ? " ✓" : ""}
            </span>
            <span className="byline-sub">
              {" "}
              {[artist.city, artist.one_liner].filter(Boolean).join(" · ")}
            </span>
          </span>
          <span>
            {artist.style_tags.slice(0, 2).map((tag) => (
              <Tag key={tag}>{tag}</Tag>
            ))}
          </span>
        </Link>
      ))}
    </>
  );
}

function YoursColumn() {
  const { user } = useAuth();
  const gigs = useResource<{ gigs: Gig[] }>(
    () => api.get("/api/v1/me/gigs"),
    [user?.id ?? ""],
    { enabled: Boolean(user) },
  );
  const applications = useResource<{ applications: GigApplication[] }>(
    () => api.get("/api/v1/me/applications"),
    [user?.id ?? ""],
    { enabled: Boolean(user) },
  );

  if (!user) {
    return (
      <Empty>
        <Link to="/sign-in">Sign in</Link> to post gigs and track your
        applications.
      </Empty>
    );
  }

  return (
    <>
      <SectionHead title="Gigs you posted" />
      {gigs.data && gigs.data.gigs.length === 0 ? (
        <Empty>None yet.</Empty>
      ) : null}
      {gigs.data?.gigs.map((gig) => (
        <GigRow key={gig.id} gig={gig} />
      ))}

      <SectionHead title="Your applications" />
      {applications.data && applications.data.applications.length === 0 ? (
        <Empty>No hands raised yet — the board is one tab over.</Empty>
      ) : null}
      {applications.data?.applications.map((application) => (
        <Link
          key={application.id}
          className="person-row"
          to={`/gigs/${application.gig_id}`}
          style={{ textDecoration: "none", color: "inherit" }}
        >
          <span style={{ minWidth: 0 }}>
            <span className="byline-name">{application.gig?.title ?? "A gig"}</span>
            <span className="byline-sub">
              {" "}
              as {application.artist?.name ?? "your band"}
            </span>
          </span>
          <Tag>{application.status}</Tag>
        </Link>
      ))}
    </>
  );
}

export function ClassifiedsPage() {
  const [column, setColumn] = useState<Column>("gigs");

  return (
    <div className="page page-narrow">
      <div className="section-head" style={{ marginTop: 0 }}>
        <h1 className="page-title" style={{ margin: 0 }}>Classifieds</h1>
        <Link className="btn btn-secondary" to="/gigs/new">
          <Plus size={15} aria-hidden /> Post a gig
        </Link>
      </div>
      <p className="page-sub">Gigs wanted, and bands for hire</p>

      <div className="seg">
        {(
          [
            ["gigs", "Gigs"],
            ["hire", "For hire"],
            ["yours", "Yours"],
          ] as const
        ).map(([key, label]) => (
          <label key={key} className="seg-opt">
            <input
              type="radio"
              name="classifieds-column"
              checked={column === key}
              onChange={() => setColumn(key)}
            />
            {label}
          </label>
        ))}
      </div>

      {column === "gigs" ? <GigsColumn /> : null}
      {column === "hire" ? <HireColumn /> : null}
      {column === "yours" ? <YoursColumn /> : null}
    </div>
  );
}
