/**
 * The small social pieces: faces, bylines, stars, the follow control, and the
 * report dialog. All stroke, no fill — same rules as everything else.
 */

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Flag, Star, UserMinus, UserPlus } from "lucide-react";
import type { ReportReason, UserCard } from "@live-msc/shared";
import { REPORT_REASONS } from "@live-msc/shared";

import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";
import { Notice } from "./Primitives";

export function Avatar({
  user,
  size = "sm",
}: {
  user: Pick<UserCard, "avatar_url" | "display_name">;
  size?: "sm" | "lg";
}) {
  const className = size === "lg" ? "avatar avatar-lg" : "avatar";
  if (user.avatar_url) {
    // The face is named by the text next to it everywhere this renders, so
    // the image itself is decorative.
    return <img className={className} src={user.avatar_url} alt="" loading="lazy" />;
  }
  return (
    <span className={`${className} avatar-blank`} aria-hidden>
      {(user.display_name || "?").trim().charAt(0).toUpperCase()}
    </span>
  );
}

export function Byline({
  user,
  sub,
  size = "sm",
}: {
  user: UserCard;
  sub?: string | null;
  size?: "sm" | "lg";
}) {
  return (
    <Link className="byline" to={`/u/${user.handle}`}>
      <Avatar user={user} size={size} />
      <span className="byline-text">
        <span className="byline-name">{user.display_name}</span>
        <span className="byline-sub">@{user.handle}{sub ? ` · ${sub}` : ""}</span>
      </span>
    </Link>
  );
}

/** Read-only stars: ★★★★☆, accent-inked, spoken as a figure. */
export function Stars({ rating }: { rating: number }) {
  return (
    <span className="stars" role="img" aria-label={`${rating} of 5`}>
      {"★".repeat(rating)}
      <span className="stars-off">{"★".repeat(5 - rating)}</span>
    </span>
  );
}

/** Star input — five outlined buttons, the chosen count inked. */
export function StarInput({
  value,
  onChange,
}: {
  value: number;
  onChange: (rating: number) => void;
}) {
  return (
    <div className="star-input" role="radiogroup" aria-label="Rating">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          role="radio"
          aria-checked={value === n}
          aria-label={`${n} star${n === 1 ? "" : "s"}`}
          className="star-btn"
          onClick={() => onChange(n)}
        >
          <Star
            size={18}
            aria-hidden
            fill={n <= value ? "currentColor" : "none"}
          />
        </button>
      ))}
    </div>
  );
}

export function FollowButton({
  handle,
  following,
  onChange,
}: {
  handle: string;
  following: boolean;
  onChange: () => void;
}) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);

  const toggle = async () => {
    if (!user) {
      navigate("/sign-in");
      return;
    }
    setBusy(true);
    if (following) await api.delete(`/api/v1/users/${handle}/follow`);
    else await api.post(`/api/v1/users/${handle}/follow`);
    setBusy(false);
    onChange();
  };

  return (
    <button
      type="button"
      className={following ? "btn btn-toggle btn-on" : "btn btn-toggle"}
      onClick={() => void toggle()}
      disabled={busy}
      aria-pressed={following}
    >
      {following ? (
        <>
          <UserMinus size={15} aria-hidden /> Following
        </>
      ) : (
        <>
          <UserPlus size={15} aria-hidden /> Follow
        </>
      )}
    </button>
  );
}

/** One row in a people list — search results, followers, the blocked page. */
export function PersonRow({
  person,
  onFollowChange,
}: {
  person: UserCard;
  onFollowChange?: () => void;
}) {
  return (
    <div className="person-row">
      <Byline user={person} sub={person.bio ?? undefined} />
      {onFollowChange && person.is_self !== true && person.is_following !== undefined ? (
        <FollowButton
          handle={person.handle}
          following={Boolean(person.is_following)}
          onChange={onFollowChange}
        />
      ) : null}
    </div>
  );
}

/**
 * "Report" — a small dialog naming a reason. Used for listings, comments,
 * reviews and people; exactly one subject id is passed.
 */
export function ReportButton({
  subject,
  label = "Report",
}: {
  subject: {
    comment_id?: string;
    review_id?: string;
    reported_user_id?: string;
    event_id?: string;
  };
  label?: string;
}) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<ReportReason>("spam");
  const [detail, setDetail] = useState("");
  const [state, setState] = useState<"idle" | "busy" | "done" | "error">("idle");

  const submit = async () => {
    setState("busy");
    const result = await api.post("/api/v1/reports", {
      ...subject,
      reason,
      detail: detail.trim() || undefined,
    });
    setState(result.ok ? "done" : "error");
  };

  return (
    <>
      <button
        type="button"
        className="btn btn-ghost btn-quiet"
        onClick={() => {
          if (!user) {
            navigate("/sign-in");
            return;
          }
          setOpen(true);
          setState("idle");
        }}
      >
        <Flag size={13} aria-hidden /> {label}
      </button>
      {open ? (
        <div className="dialog-backdrop" onClick={() => setOpen(false)}>
          <div
            className="dialog"
            role="dialog"
            aria-modal="true"
            aria-label="Report to the editors"
            onClick={(event) => event.stopPropagation()}
          >
            <p className="dialog-title">Report to the editors</p>
            <div className="dialog-body">
              {state === "done" ? (
                <Notice>Thank you — the editors will take a look.</Notice>
              ) : (
                <>
                  {REPORT_REASONS.map((option) => (
                    <label key={option.value} className="radio">
                      <input
                        type="radio"
                        name="report-reason"
                        checked={reason === option.value}
                        onChange={() => setReason(option.value)}
                      />
                      {option.label}
                    </label>
                  ))}
                  <textarea
                    className="input"
                    rows={2}
                    maxLength={500}
                    placeholder="Anything the editors should know (optional)"
                    value={detail}
                    onChange={(event) => setDetail(event.target.value)}
                  />
                  {state === "error" ? (
                    <Notice tone="error">That report could not be sent.</Notice>
                  ) : null}
                </>
              )}
            </div>
            <div className="dialog-actions">
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => setOpen(false)}
              >
                {state === "done" ? "Close" : "Never mind"}
              </button>
              {state !== "done" ? (
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={state === "busy"}
                  onClick={() => void submit()}
                >
                  Send report
                </button>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}

/** Comment bodies print @handles as links without trusting any markup. */
export function MentionText({ text }: { text: string }) {
  const parts = text.split(/(@[a-z0-9_]{3,30})/gi);
  return (
    <>
      {parts.map((part, index) =>
        /^@[a-z0-9_]{3,30}$/i.test(part) ? (
          <Link key={index} className="mention" to={`/u/${part.slice(1).toLowerCase()}`}>
            {part}
          </Link>
        ) : (
          <span key={index}>{part}</span>
        ),
      )}
    </>
  );
}
