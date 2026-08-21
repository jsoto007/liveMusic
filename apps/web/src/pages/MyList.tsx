/** Your list — what you are going to, what you kept, and your named shelves. */

import { useState } from "react";
import { Link } from "react-router-dom";
import type { EventList, EventListing } from "@live-msc/shared";

import { ListingRow } from "../components/Listing";
import { Empty, Notice, SectionHead, Spinner } from "../components/Primitives";
import { useAuth } from "../context/AuthContext";
import { useResource } from "../hooks/useResource";
import { api } from "../lib/api";

interface ListResponse {
  going: EventListing[];
  saved: EventListing[];
  summary: string;
}

function NamedLists() {
  const { user } = useAuth();
  const [name, setName] = useState("");
  const [isPublic, setIsPublic] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const { data, error, loading, reload } = useResource<{ lists: EventList[] }>(
    () => api.get<{ lists: EventList[] }>("/api/v1/me/lists"),
    [user?.id ?? ""],
  );

  const create = async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    setBusy(true);
    setFormError(null);
    const result = await api.post("/api/v1/me/lists", {
      name: trimmed,
      is_public: isPublic,
    });
    setBusy(false);
    if (!result.ok) {
      setFormError(result.error);
      return;
    }
    setName("");
    setIsPublic(false);
    reload();
  };

  return (
    <>
      <SectionHead title="Your lists" />
      {error ? <Notice tone="error">{error}</Notice> : null}
      {loading && !data ? <Spinner /> : null}
      {data && data.lists.length === 0 ? (
        <Empty>
          Shelves for anything — “Jazz to catch”, “October”. Public ones show
          on your profile.
        </Empty>
      ) : null}
      {data?.lists.map((list) => (
        <Link
          key={list.id}
          className="person-row"
          to={`/lists/${list.id}`}
          style={{ textDecoration: "none", color: "inherit" }}
        >
          <span>
            <span className="byline-name">{list.name}</span>
            <span className="byline-sub">
              {" "}
              {list.is_public ? "public" : "private"} · {list.count_label ?? "0 shows"}
            </span>
          </span>
        </Link>
      ))}

      <div className="actions" style={{ alignItems: "center" }}>
        <input
          className="input"
          placeholder="Start a list"
          maxLength={80}
          value={name}
          onChange={(event) => setName(event.target.value)}
          style={{ flex: 1 }}
        />
        <label className="radio" style={{ whiteSpace: "nowrap" }}>
          <input
            type="checkbox"
            checked={isPublic}
            onChange={(event) => setIsPublic(event.target.checked)}
          />
          Public
        </label>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={busy || !name.trim()}
          onClick={() => void create()}
        >
          Create
        </button>
      </div>
      {formError ? <Notice tone="error">{formError}</Notice> : null}
    </>
  );
}

export function MyListPage() {
  const { user, initializing } = useAuth();
  const { data, error, loading } = useResource<ListResponse>(
    () => api.get<ListResponse>("/api/v1/me/list"),
    [user?.id ?? ""],
  );

  if (initializing) return <div className="page page-narrow"><Spinner /></div>;

  if (!user) {
    return (
      <div className="page page-narrow">
        <h1 className="page-title">Your list</h1>
        <Notice>Sign in to keep shows and mark what you&rsquo;re going to.</Notice>
        <Link className="btn btn-primary" to="/sign-in">
          Sign in
        </Link>
      </div>
    );
  }

  return (
    <div className="page page-narrow">
      <h1 className="page-title">Your list</h1>
      <p className="page-sub">{data?.summary ?? "—"}</p>

      {error ? <Notice tone="error">{error}</Notice> : null}
      {loading && !data ? <Spinner /> : null}

      <SectionHead title="Going" />
      {data?.going.length === 0 ? (
        <Empty>Nothing marked yet.</Empty>
      ) : (
        data?.going.map((event) => (
          <ListingRow key={event.id} event={event} showNote={false} />
        ))
      )}

      <SectionHead title="Kept for later" />
      {data?.saved.length === 0 ? (
        <Empty>Nothing kept yet.</Empty>
      ) : (
        data?.saved.map((event) => (
          <ListingRow key={event.id} event={event} showNote={false} />
        ))
      )}

      <NamedLists />
    </div>
  );
}
