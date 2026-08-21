/** The inbox: every bell that has rung for you. */

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { Notification, NotificationPage } from "@live-msc/shared";

import { Empty, Notice, Spinner } from "../components/Primitives";
import { useAuth } from "../context/AuthContext";
import { useResource } from "../hooks/useResource";
import { api } from "../lib/api";

const PAGE = 50;

function destination(notification: Notification): string | null {
  switch (notification.kind) {
    case "new_follower":
      return notification.actor ? `/u/${notification.actor.handle}` : null;
    case "gig_application":
    case "gig_accepted":
    case "gig_declined":
      return notification.gig_id ? `/gigs/${notification.gig_id}` : null;
    default:
      return notification.event_id ? `/shows/${notification.event_id}` : null;
  }
}

function when(iso: string): string {
  const then = new Date(iso);
  const days = (Date.now() - then.getTime()) / 86_400_000;
  if (days < 1) {
    return then.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  }
  return then.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function NotificationsPage() {
  const { user, initializing } = useAuth();
  const navigate = useNavigate();
  const [limit, setLimit] = useState(PAGE);

  const { data, error, loading, reload } = useResource<NotificationPage>(
    () => api.get<NotificationPage>(`/api/v1/me/notifications?limit=${limit}`),
    [user?.id ?? "", limit],
    { enabled: !initializing && Boolean(user) },
  );

  const open = async (notification: Notification) => {
    if (!notification.read) {
      await api.post("/api/v1/me/notifications/read", { ids: [notification.id] });
    }
    const to = destination(notification);
    if (to) navigate(to);
    else reload();
  };

  const markAll = async () => {
    await api.post("/api/v1/me/notifications/read", { all: true });
    reload();
  };

  if (initializing) return <div className="page page-narrow"><Spinner /></div>;

  if (!user) {
    return (
      <div className="page page-narrow">
        <h1 className="page-title">Inbox</h1>
        <Notice>Sign in to see who followed you, and who wrote back.</Notice>
        <Link className="btn btn-primary" to="/sign-in">Sign in</Link>
      </div>
    );
  }

  return (
    <div className="page page-narrow">
      <div className="section-head" style={{ marginTop: 0 }}>
        <h1 className="page-title" style={{ margin: 0 }}>Inbox</h1>
        {data && data.unread_count > 0 ? (
          <button type="button" className="btn btn-ghost btn-quiet" onClick={() => void markAll()}>
            Mark all read
          </button>
        ) : null}
      </div>
      <p className="page-sub">
        {data
          ? data.unread_count > 0
            ? `${data.unread_count} unread`
            : "All read"
          : "—"}
      </p>

      {error ? <Notice tone="error">{error}</Notice> : null}
      {loading && !data ? <Spinner /> : null}
      {data && data.total === 0 ? (
        <Empty>Quiet so far. It rings when someone follows you or writes back.</Empty>
      ) : null}

      {data?.notifications.map((notification) => (
        <button
          key={notification.id}
          type="button"
          className="notif-row"
          onClick={() => void open(notification)}
        >
          {notification.read ? <span aria-hidden /> : <span className="unread-ring" aria-label="Unread" />}
          <span className="notif-line">
            {notification.line}
            {notification.comment_excerpt ? (
              <span className="notif-excerpt">“{notification.comment_excerpt}”</span>
            ) : null}
          </span>
          <span className="notif-when">{when(notification.created_at)}</span>
        </button>
      ))}

      {data?.has_more ? (
        <button
          type="button"
          className="btn btn-ghost btn-block"
          onClick={() => setLimit((value) => value + PAGE)}
        >
          Older
        </button>
      ) : null}
    </div>
  );
}
