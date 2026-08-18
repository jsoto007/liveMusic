/** A reader's public page: the face, the shelf, the verdicts, the bands. */

import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ShieldOff } from "lucide-react";
import type { EventList, Profile, Review } from "@live-msc/shared";

import { MessageButton } from "../components/MessageButton";
import { Empty, Notice, Rule, SectionHead, Spinner } from "../components/Primitives";
import {
  Avatar,
  FollowButton,
  ReportButton,
  Stars,
} from "../components/Social";
import { useAuth } from "../context/AuthContext";
import { useResource } from "../hooks/useResource";
import { api } from "../lib/api";

export function ProfilePage() {
  const { handle = "" } = useParams();
  const { user, initializing } = useAuth();
  const [blockBusy, setBlockBusy] = useState(false);

  const { data, error, loading, reload } = useResource<{ profile: Profile }>(
    () => api.get<{ profile: Profile }>(`/api/v1/users/${handle}`),
    [handle, user?.id ?? ""],
    { enabled: !initializing },
  );
  const lists = useResource<{ lists: EventList[] }>(
    () => api.get<{ lists: EventList[] }>(`/api/v1/users/${handle}/lists`),
    [handle, user?.id ?? ""],
    { enabled: !initializing },
  );
  const reviews = useResource<{ reviews: Review[]; total: number }>(
    () => api.get<{ reviews: Review[]; total: number }>(
      `/api/v1/users/${handle}/reviews?limit=10`,
    ),
    [handle, user?.id ?? ""],
    { enabled: !initializing },
  );

  const profile = data?.profile ?? null;

  const toggleBlock = async () => {
    if (!profile) return;
    setBlockBusy(true);
    if (profile.is_blocked) await api.delete(`/api/v1/users/${handle}/block`);
    else await api.post(`/api/v1/users/${handle}/block`);
    setBlockBusy(false);
    reload();
  };

  if ((loading || initializing) && !profile) {
    return <div className="page page-narrow"><Spinner /></div>;
  }
  if (error || !profile) {
    return (
      <div className="page page-narrow">
        <Notice tone="error">{error ?? "That person could not be found."}</Notice>
        <Link className="btn btn-ghost" to="/">Back to the bill</Link>
      </div>
    );
  }

  const memberSince = new Date(profile.member_since).toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });

  return (
    <div className="page page-narrow">
      <header className="profile-head">
        <Avatar user={profile} size="lg" />
        <div style={{ minWidth: 0, flex: 1 }}>
          <h1 className="page-title" style={{ marginBottom: 0 }}>
            {profile.display_name}
          </h1>
          <p className="kicker">
            @{profile.handle}
            {profile.home_city ? ` · ${profile.home_city}` : ""}
            {` · reading since ${memberSince}`}
          </p>
          {profile.bio ? <p className="prose" style={{ marginTop: "var(--space-2)" }}>{profile.bio}</p> : null}
          <div className="profile-counts" style={{ marginTop: "var(--space-2)" }}>
            <span><b>{profile.follower_count}</b> followers</span>
            <span><b>{profile.following_count}</b> following</span>
            <span><b>{profile.review_count}</b> reviews</span>
          </div>
        </div>
      </header>

      {!profile.is_self ? (
        <div className="actions" style={{ marginTop: 0 }}>
          <FollowButton
            handle={profile.handle}
            following={Boolean(profile.is_following)}
            onChange={reload}
          />
          <MessageButton
            anchor={{ to: profile.handle }}
            recipientName={profile.display_name}
          />
          {user ? (
            <button
              type="button"
              className="btn btn-ghost btn-quiet"
              disabled={blockBusy}
              onClick={() => void toggleBlock()}
            >
              <ShieldOff size={13} aria-hidden />{" "}
              {profile.is_blocked ? "Unblock" : "Block"}
            </button>
          ) : null}
          <ReportButton subject={{ reported_user_id: profile.id }} label="Report" />
        </div>
      ) : (
        <div className="actions" style={{ marginTop: 0 }}>
          <Link className="btn btn-ghost" to="/account">
            This is you — edit your profile
          </Link>
        </div>
      )}

      <Rule />

      {profile.artists.length > 0 ? (
        <>
          <SectionHead title="Their bands" />
          {profile.artists.map((artist) => (
            <Link key={artist.id} className="person-row" to={`/bands/${artist.slug}`} style={{ textDecoration: "none", color: "inherit" }}>
              <span>
                <span className="byline-name">{artist.name}</span>
                <span className="byline-sub">
                  {" "}
                  {artist.city ?? ""}
                  {artist.available_for_hire ? " · available for hire" : ""}
                </span>
              </span>
            </Link>
          ))}
        </>
      ) : null}

      <SectionHead title={profile.is_self ? "Your lists" : "Public lists"} />
      {lists.data && lists.data.lists.length === 0 ? (
        <Empty>Nothing on the shelf yet.</Empty>
      ) : null}
      {lists.data?.lists.map((list) => (
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
              {list.is_public ? "public" : "private"} · {list.count_label ?? ""}
            </span>
          </span>
        </Link>
      ))}

      <SectionHead title="Recent verdicts" />
      {reviews.data && reviews.data.total === 0 ? (
        <Empty>No reviews yet.</Empty>
      ) : null}
      {reviews.data?.reviews.map((review) => (
        <article key={review.id} className="comment">
          <div className="comment-head">
            {review.event ? (
              <Link className="byline-name" to={`/shows/${review.event.id}`} style={{ textDecoration: "none", color: "inherit" }}>
                {review.event.headline}
              </Link>
            ) : (
              <span className="byline-name">A show</span>
            )}
            <Stars rating={review.rating} />
          </div>
          {review.body ? <p className="comment-body">{review.body}</p> : null}
        </article>
      ))}
    </div>
  );
}
