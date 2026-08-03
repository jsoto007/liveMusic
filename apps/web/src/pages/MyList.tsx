/** Your list — what you are going to, and what you kept for later. */

import { Link } from "react-router-dom";
import type { EventListing } from "@live-msc/shared";

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
    </div>
  );
}
