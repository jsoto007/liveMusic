/**
 * Look it up — free-text search across acts, rooms and neighbourhoods,
 * narrowed by the genre buckets.
 */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Search as SearchIcon } from "lucide-react";
import {
  queryString,
  type EventListing,
  type Genre,
  type PeoplePage,
} from "@live-msc/shared";

import { GenreChips } from "../components/GenreChips";
import { ListingRow } from "../components/Listing";
import { Empty, Notice, Rule, SectionHead, Spinner } from "../components/Primitives";
import { PersonRow } from "../components/Social";
import { useAuth } from "../context/AuthContext";
import { useResource } from "../hooks/useResource";
import { api } from "../lib/api";

/** Wait for a pause in typing before querying, so a search is one request. */
function useDebounced<T>(value: T, delayMs = 300): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return settled;
}

export function SearchPage() {
  const { user } = useAuth();
  const [term, setTerm] = useState("");
  const [genres, setGenres] = useState<Genre[]>([]);
  const debouncedTerm = useDebounced(term);

  const { data, error, loading } = useResource<{ events: EventListing[]; count: number }>(
    () =>
      api.get<{ events: EventListing[]; count: number }>(
        `/api/v1/events${queryString({ q: debouncedTerm, genre: genres })}`,
      ),
    [debouncedTerm, genres.join(",")],
  );

  // People match on two or more characters; below that the endpoint refuses.
  const peopleTerm = debouncedTerm.trim().length >= 2 ? debouncedTerm.trim() : "";
  const people = useResource<PeoplePage>(
    () => api.get<PeoplePage>(`/api/v1/users/search${queryString({ q: peopleTerm })}`),
    [peopleTerm, user?.id ?? ""],
    { enabled: peopleTerm.length >= 2 },
  );

  const toggleGenre = (genre: Genre) =>
    setGenres((current) =>
      current.includes(genre) ? current.filter((g) => g !== genre) : [...current, genre],
    );

  const count = data?.count ?? 0;

  return (
    <div className="page page-narrow">
      <h1 className="page-title">Look it up</h1>

      <div className="search-field" style={{ marginTop: "var(--space-4)" }}>
        <SearchIcon size={16} aria-hidden />
        <input
          className="input"
          type="search"
          value={term}
          onChange={(event) => setTerm(event.target.value)}
          placeholder="Band, venue or genre"
          aria-label="Search listings"
          maxLength={80}
        />
      </div>

      <div style={{ marginTop: "var(--space-3)" }}>
        <GenreChips selected={genres} onToggle={toggleGenre} />
      </div>

      <SectionHead
        title="Results"
        count={loading ? "searching" : count === 1 ? "1 show" : `${count} shows`}
      />

      {error ? <Notice tone="error">{error}</Notice> : null}
      {loading && !data ? <Spinner label="Looking" /> : null}

      {data?.events.map((event) => (
        <ListingRow key={event.id} event={event} showNote={false} />
      ))}

      {!loading && data && count === 0 ? (
        <Empty>
          Nothing on the bill for that. Clear a filter, or{" "}
          <Link to="/post">post the show yourself</Link>.
        </Empty>
      ) : null}

      {peopleTerm ? (
        <>
          <SectionHead
            title="People"
            count={
              people.loading
                ? "searching"
                : `${people.data?.total ?? 0} ${
                    (people.data?.total ?? 0) === 1 ? "reader" : "readers"
                  }`
            }
          />
          {people.data?.people.map((person) => (
            <PersonRow
              key={person.id}
              person={person}
              onFollowChange={people.reload}
            />
          ))}
          {!people.loading && people.data && people.data.total === 0 ? (
            <Empty>No readers by that name.</Empty>
          ) : null}
        </>
      ) : null}

      <Rule />

      <p className="form-note">
        After something else? <Link to="/classifieds">Browse the classifieds</Link> —
        gigs wanted and bands for hire.
      </p>
    </div>
  );
}
