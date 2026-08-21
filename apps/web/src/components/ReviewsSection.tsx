/** The verdicts: stars and words, open once the show has started. */

import { useEffect, useState } from "react";
import type { Review, ReviewPage } from "@live-msc/shared";

import { useAuth } from "../context/AuthContext";
import { useResource } from "../hooks/useResource";
import { api } from "../lib/api";
import { Empty, Notice, SectionHead, Spinner } from "./Primitives";
import { Byline, ReportButton, StarInput, Stars } from "./Social";

export function ReviewsSection({
  eventId,
  alreadyStarted,
}: {
  eventId: string;
  alreadyStarted: boolean;
}) {
  const { user, initializing } = useAuth();
  const [rating, setRating] = useState(0);
  const [body, setBody] = useState("");
  const [editing, setEditing] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const { data, error, loading, reload } = useResource<ReviewPage>(
    () => api.get<ReviewPage>(`/api/v1/events/${eventId}/reviews`),
    [eventId, user?.id ?? ""],
    { enabled: !initializing },
  );

  const mine = data?.my_review ?? null;

  // Editing starts from what was said last time.
  useEffect(() => {
    if (mine && editing) {
      setRating(mine.rating);
      setBody(mine.body ?? "");
    }
  }, [mine, editing]);

  const save = async () => {
    if (rating < 1) {
      setFormError("Pick a star rating first.");
      return;
    }
    setSaving(true);
    setFormError(null);
    const payload = { rating, body: body.trim() || undefined };
    const result = mine
      ? await api.patch(`/api/v1/reviews/${mine.id}`, payload)
      : await api.post(`/api/v1/events/${eventId}/reviews`, payload);
    setSaving(false);
    if (!result.ok) {
      setFormError(result.error);
      return;
    }
    setEditing(false);
    setRating(0);
    setBody("");
    reload();
  };

  const removeMine = async () => {
    if (!mine) return;
    await api.delete(`/api/v1/reviews/${mine.id}`);
    setEditing(false);
    setRating(0);
    setBody("");
    reload();
  };

  const total = data?.review_count ?? 0;

  return (
    <section>
      <SectionHead
        title="Verdicts"
        count={data?.rating_label ?? undefined}
      />

      {!alreadyStarted ? (
        <Empty>Reviews open once the show has started.</Empty>
      ) : null}

      {alreadyStarted && user && !mine && !editing ? (
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => setEditing(true)}
          style={{ marginBottom: "var(--space-3)" }}
        >
          Write your review
        </button>
      ) : null}
      {alreadyStarted && !user ? (
        <Empty>Sign in to leave a verdict.</Empty>
      ) : null}

      {alreadyStarted && user && editing ? (
        <div style={{ marginBottom: "var(--space-3)" }}>
          <StarInput value={rating} onChange={setRating} />
          <textarea
            className="input"
            rows={3}
            maxLength={2000}
            placeholder="How was it? (optional)"
            value={body}
            onChange={(event) => setBody(event.target.value)}
            style={{ marginTop: "var(--space-2)" }}
          />
          <div className="actions" style={{ marginTop: "var(--space-2)" }}>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={saving}
              onClick={() => void save()}
            >
              {mine ? "Save changes" : "Publish review"}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => setEditing(false)}
            >
              Never mind
            </button>
            {mine ? (
              <button
                type="button"
                className="btn btn-ghost btn-quiet"
                onClick={() => void removeMine()}
              >
                Delete review
              </button>
            ) : null}
          </div>
          {formError ? <Notice tone="error">{formError}</Notice> : null}
        </div>
      ) : null}

      {mine && !editing ? (
        <div className="comment" style={{ borderTop: "1px solid var(--color-divider)" }}>
          <div className="comment-head">
            <span className="kicker">Your verdict</span>
            <button
              type="button"
              className="btn btn-ghost btn-quiet"
              onClick={() => setEditing(true)}
            >
              Edit
            </button>
          </div>
          <Stars rating={mine.rating} />
          {mine.body ? <p className="comment-body">{mine.body}</p> : null}
        </div>
      ) : null}

      {error ? <Notice tone="error">{error}</Notice> : null}
      {loading && !data ? <Spinner /> : null}
      {data && total === 0 && alreadyStarted ? (
        <Empty>No verdicts yet.</Empty>
      ) : null}

      {data?.reviews
        .filter((review) => review.id !== mine?.id)
        .map((review: Review) => (
          <article key={review.id} className="comment">
            <div className="comment-head">
              <Byline user={review.author} />
              <Stars rating={review.rating} />
            </div>
            {review.body ? <p className="comment-body">{review.body}</p> : null}
            <div className="comment-actions">
              {review.edited ? (
                <span className="notif-when">edited</span>
              ) : null}
              <ReportButton subject={{ review_id: review.id }} />
            </div>
          </article>
        ))}
    </section>
  );
}
