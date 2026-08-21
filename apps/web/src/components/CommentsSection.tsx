/** The letters column under a listing: flat, newest first. */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Heart } from "lucide-react";
import type { Comment, CommentPage } from "@live-msc/shared";

import { useAuth } from "../context/AuthContext";
import { useResource } from "../hooks/useResource";
import { api } from "../lib/api";
import { Empty, Notice, SectionHead, Spinner } from "./Primitives";
import { Byline, MentionText, ReportButton } from "./Social";

const PAGE = 20;

export function CommentsSection({ eventId }: { eventId: string }) {
  const { user, initializing } = useAuth();
  const navigate = useNavigate();
  const [limit, setLimit] = useState(PAGE);
  const [draft, setDraft] = useState("");
  const [sendError, setSendError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const { data, error, loading, reload } = useResource<CommentPage>(
    () => api.get<CommentPage>(`/api/v1/events/${eventId}/comments?limit=${limit}`),
    [eventId, limit, user?.id ?? ""],
    { enabled: !initializing },
  );

  const submit = async () => {
    const body = draft.trim();
    if (!body) return;
    setSending(true);
    setSendError(null);
    const result = await api.post(`/api/v1/events/${eventId}/comments`, { body });
    setSending(false);
    if (!result.ok) {
      setSendError(
        result.code === "BLOCKED"
          ? "You can’t comment on this listing."
          : result.error,
      );
      return;
    }
    setDraft("");
    reload();
  };

  const toggleLike = async (comment: Comment) => {
    if (!user) {
      navigate("/sign-in");
      return;
    }
    if (comment.viewer_liked) {
      await api.delete(`/api/v1/comments/${comment.id}/like`);
    } else {
      await api.post(`/api/v1/comments/${comment.id}/like`);
    }
    reload();
  };

  const remove = async (comment: Comment) => {
    await api.delete(`/api/v1/comments/${comment.id}`);
    reload();
  };

  const total = data?.total ?? 0;

  return (
    <section>
      <SectionHead
        title="Letters"
        count={total ? `${total} comment${total === 1 ? "" : "s"}` : undefined}
      />

      {user ? (
        <div style={{ marginBottom: "var(--space-3)" }}>
          <textarea
            className="input"
            rows={2}
            maxLength={2000}
            placeholder="Add a comment — name a friend with @handle"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
          <div className="actions" style={{ marginTop: "var(--space-2)" }}>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={sending || !draft.trim()}
              onClick={() => void submit()}
            >
              Send it in
            </button>
          </div>
          {sendError ? <Notice tone="error">{sendError}</Notice> : null}
        </div>
      ) : (
        <Empty>Sign in to join the letters column.</Empty>
      )}

      {error ? <Notice tone="error">{error}</Notice> : null}
      {loading && !data ? <Spinner /> : null}
      {data && total === 0 ? <Empty>No comments yet — start the thread.</Empty> : null}

      {data?.comments.map((comment) => (
        <article key={comment.id} className="comment">
          <div className="comment-head">
            <Byline user={comment.author} />
            <span className="notif-when">
              {new Date(comment.created_at).toLocaleDateString(undefined, {
                day: "numeric",
                month: "short",
              })}
            </span>
          </div>
          <p className="comment-body">
            <MentionText text={comment.body} />
          </p>
          <div className="comment-actions">
            <button
              type="button"
              className="btn btn-ghost btn-quiet"
              aria-pressed={comment.viewer_liked}
              onClick={() => void toggleLike(comment)}
            >
              <Heart
                size={13}
                aria-hidden
                fill={comment.viewer_liked ? "currentColor" : "none"}
              />{" "}
              {comment.like_count > 0 ? comment.like_count : "Like"}
            </button>
            <ReportButton subject={{ comment_id: comment.id }} />
            {comment.can_delete ? (
              <button
                type="button"
                className="btn btn-ghost btn-quiet"
                onClick={() => void remove(comment)}
              >
                Delete
              </button>
            ) : null}
          </div>
        </article>
      ))}

      {data?.has_more ? (
        <button
          type="button"
          className="btn btn-ghost btn-block"
          onClick={() => setLimit((value) => value + PAGE)}
        >
          More letters
        </button>
      ) : null}
    </section>
  );
}
