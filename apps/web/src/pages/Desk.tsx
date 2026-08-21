/**
 * The editors' desk: reported content, and every photo awaiting an eye.
 *
 * The server answers 404 to non-admins on every endpoint here; this page is
 * simply not linked for them. Nothing on the client is the gate.
 */

import { useState } from "react";
import type { AdminReport, ImageReview } from "@live-msc/shared";

import { Empty, Notice, Plate, SectionHead, Spinner, Tag } from "../components/Primitives";
import { Byline, Stars } from "../components/Social";
import { useAuth } from "../context/AuthContext";
import { useResource } from "../hooks/useResource";
import { api } from "../lib/api";

function PhotoQueue() {
  const { data, error, loading, reload } = useResource<{
    reviews: ImageReview[];
    total: number;
  }>(() => api.get("/api/v1/admin/image-reviews?limit=50"), []);

  const [actionError, setActionError] = useState<string | null>(null);

  const resolve = async (review: ImageReview, action: "approve" | "remove") => {
    setActionError(null);
    const result = await api.post(
      `/api/v1/admin/image-reviews/${review.id}/resolve`,
      { action },
    );
    if (!result.ok) setActionError(result.error);
    reload();
  };

  const purposeLabel: Record<string, string> = {
    user_avatar: "Profile photo",
    artist_photo: "Band photo",
    event_poster: "Show poster",
  };

  return (
    <>
      {error ? <Notice tone="error">{error}</Notice> : null}
      {actionError ? <Notice tone="error">{actionError}</Notice> : null}
      {loading && !data ? <Spinner /> : null}
      {data && data.total === 0 ? (
        <Empty>The photo queue is clear.</Empty>
      ) : null}

      {data?.reviews.map((review) => (
        <div key={review.id} className="comment">
          <div style={{ maxWidth: 320 }}>
            <Plate
              src={review.image_url}
              alt={`${purposeLabel[review.purpose] ?? "Photo"} awaiting review`}
              placeholder="image unavailable"
            />
          </div>
          <div className="comment-head" style={{ marginTop: "var(--space-2)" }}>
            <span>
              <Tag>{purposeLabel[review.purpose] ?? review.purpose}</Tag>{" "}
              {review.uploader ? <Byline user={review.uploader} /> : null}
            </span>
            <span className="comment-actions" style={{ marginTop: 0 }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => void resolve(review, "approve")}
              >
                Approve
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-quiet"
                onClick={() => void resolve(review, "remove")}
              >
                Remove
              </button>
            </span>
          </div>
        </div>
      ))}
    </>
  );
}

function ReportQueue() {
  const { data, error, loading, reload } = useResource<{
    reports: AdminReport[];
    total: number;
  }>(() => api.get("/api/v1/admin/reports?status=open&limit=50"), []);

  const [actionError, setActionError] = useState<string | null>(null);

  const resolve = async (report: AdminReport, action: "dismiss" | "remove_content") => {
    setActionError(null);
    const result = await api.post(`/api/v1/admin/reports/${report.id}/resolve`, {
      action,
    });
    if (!result.ok) setActionError(result.error);
    reload();
  };

  return (
    <>
      {error ? <Notice tone="error">{error}</Notice> : null}
      {actionError ? <Notice tone="error">{actionError}</Notice> : null}
      {loading && !data ? <Spinner /> : null}
      {data && data.total === 0 ? <Empty>No open reports.</Empty> : null}

      {data?.reports.map((report) => (
        <div key={report.id} className="comment">
          <div className="comment-head">
            <span>
              <Tag>{report.subject_type}</Tag> <Tag>{report.reason}</Tag>
              {report.reporter ? (
                <span className="byline-sub">
                  {" "}
                  reported by @{report.reporter.handle}
                </span>
              ) : null}
            </span>
            <span className="comment-actions" style={{ marginTop: 0 }}>
              {report.subject_type === "comment" || report.subject_type === "review" ? (
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => void resolve(report, "remove_content")}
                >
                  Remove it
                </button>
              ) : null}
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => void resolve(report, "dismiss")}
              >
                Dismiss
              </button>
            </span>
          </div>
          {report.detail ? (
            <p className="comment-body">“{report.detail}”</p>
          ) : null}
          {report.comment ? (
            <div style={{ marginTop: "var(--space-2)" }}>
              <Byline user={report.comment.author} />
              <p className="comment-body">{report.comment.body}</p>
            </div>
          ) : null}
          {report.review ? (
            <div style={{ marginTop: "var(--space-2)" }}>
              <Byline user={report.review.author} />
              <Stars rating={report.review.rating} />
              {report.review.body ? (
                <p className="comment-body">{report.review.body}</p>
              ) : null}
            </div>
          ) : null}
          {report.reported_user ? (
            <div style={{ marginTop: "var(--space-2)" }}>
              <Byline user={report.reported_user} />
            </div>
          ) : null}
        </div>
      ))}
    </>
  );
}

export function DeskPage() {
  const { user, initializing } = useAuth();
  const [column, setColumn] = useState<"photos" | "reports">("photos");

  if (initializing) return <div className="page page-narrow"><Spinner /></div>;
  if (!user || user.role !== "admin") {
    // Nothing to advertise; the API would 404 anyway.
    return (
      <div className="page page-narrow">
        <Empty>Not in this edition.</Empty>
      </div>
    );
  }

  return (
    <div className="page page-narrow">
      <h1 className="page-title">The desk</h1>
      <p className="page-sub">Photos awaiting review, and reader reports</p>

      <div className="seg">
        {(
          [
            ["photos", "Photos"],
            ["reports", "Reports"],
          ] as const
        ).map(([key, label]) => (
          <label key={key} className="seg-opt">
            <input
              type="radio"
              name="desk-column"
              checked={column === key}
              onChange={() => setColumn(key)}
            />
            {label}
          </label>
        ))}
      </div>

      <SectionHead title={column === "photos" ? "The photo queue" : "Open reports"} />
      {column === "photos" ? <PhotoQueue /> : <ReportQueue />}
    </div>
  );
}
