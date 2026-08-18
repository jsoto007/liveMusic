/** The Following column — your personal edition of the paper. */

import { useState } from "react";
import { Link } from "react-router-dom";
import type { FeedPage } from "@live-msc/shared";

import { ListingRow } from "../components/Listing";
import { Empty, Notice, Spinner } from "../components/Primitives";
import { Stars } from "../components/Social";
import { useAuth } from "../context/AuthContext";
import { useResource } from "../hooks/useResource";
import { api } from "../lib/api";

const PAGE = 20;

export function FeedPageView() {
  const { user, initializing } = useAuth();
  const [limit, setLimit] = useState(PAGE);

  const { data, error, loading } = useResource<FeedPage>(
    () => api.get<FeedPage>(`/api/v1/me/feed?limit=${limit}`),
    [user?.id ?? "", limit],
    { enabled: !initializing && Boolean(user) },
  );

  if (initializing) return <div className="page page-narrow"><Spinner /></div>;

  if (!user) {
    return (
      <div className="page page-narrow">
        <h1 className="page-title">Following</h1>
        <Notice>
          Sign in to read your own column — shows from bands you follow, and
          what the readers you follow are saying.
        </Notice>
        <Link className="btn btn-primary" to="/sign-in">Sign in</Link>
      </div>
    );
  }

  return (
    <div className="page page-narrow">
      <h1 className="page-title">Following</h1>
      <p className="page-sub">
        What the bands and readers you follow have been up to
        {data ? ` · last ${data.window_days} days` : ""}
      </p>

      {error ? <Notice tone="error">{error}</Notice> : null}
      {loading && !data ? <Spinner /> : null}

      {data && data.items.length === 0 ? (
        <Empty>
          Nothing yet. Follow bands from their pages, and people from theirs —
          their shows, verdicts and public lists will land here.{" "}
          <Link to="/search">Find someone to follow.</Link>
        </Empty>
      ) : null}

      {data?.items.map((item, index) => (
        <article key={`${item.type}-${item.event.id}-${item.at}-${index}`} style={{ padding: "var(--space-3) 0", borderBottom: "1px solid var(--color-divider)" }}>
          <p className="kicker feed-line">
            {item.actor ? (
              <Link className="kicker-accent" to={`/u/${item.actor.handle}`} style={{ textDecoration: "none" }}>
                {item.line}
              </Link>
            ) : (
              item.line
            )}
            {item.type === "list_add" && item.list ? (
              <>
                {" — "}
                <Link to={`/lists/${item.list.id}`}>see the list</Link>
              </>
            ) : null}
          </p>
          {item.type === "review" && item.review ? (
            <div style={{ margin: "var(--space-1) 0" }}>
              <Stars rating={item.review.rating} />
              {item.review.body ? (
                <p className="comment-body">{item.review.body}</p>
              ) : null}
            </div>
          ) : null}
          <ListingRow event={item.event} showNote={false} />
        </article>
      ))}

      {data?.has_more ? (
        <button
          type="button"
          className="btn btn-ghost btn-block"
          onClick={() => setLimit((value) => value + PAGE)}
        >
          Further back
        </button>
      ) : null}
    </div>
  );
}
