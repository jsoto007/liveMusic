/** One classified: the ask, the terms, and the hands raised for it. */

import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ChevronLeft } from "lucide-react";
import type { Gig, GigApplication } from "@live-msc/shared";

import { MessageButton } from "../components/MessageButton";
import { Empty, Notice, Rule, SectionHead, Spinner, Tag } from "../components/Primitives";
import { Byline } from "../components/Social";
import { useAuth } from "../context/AuthContext";
import { useResource } from "../hooks/useResource";
import { api } from "../lib/api";

export function GigDetailPage() {
  const { gigId = "" } = useParams();
  const navigate = useNavigate();
  const { user, artists, initializing } = useAuth();

  const [artistId, setArtistId] = useState("");
  const [message, setMessage] = useState("");
  const [applyError, setApplyError] = useState<string | null>(null);
  const [applying, setApplying] = useState(false);

  const { data, error, loading, reload } = useResource<{ gig: Gig }>(
    () => api.get<{ gig: Gig }>(`/api/v1/gigs/${gigId}`),
    [gigId, user?.id ?? ""],
    { enabled: !initializing },
  );
  const gig = data?.gig ?? null;

  const applications = useResource<{ applications: GigApplication[] }>(
    () => api.get(`/api/v1/gigs/${gigId}/applications`),
    [gigId, user?.id ?? "", gig?.can_manage ? "y" : "n"],
    { enabled: !initializing && Boolean(gig?.can_manage) },
  );

  const myBands = artists ?? [];
  const appliedArtistIds = new Set(
    (gig?.my_applications ?? []).map((application) => application.artist_id),
  );
  const bandsFree = myBands.filter((band) => !appliedArtistIds.has(band.id));
  const firstFree = bandsFree.length > 0 ? bandsFree[0] : undefined;

  const apply = async () => {
    const chosen = artistId || firstFree?.id;
    if (!chosen) return;
    setApplying(true);
    setApplyError(null);
    const result = await api.post(`/api/v1/gigs/${gigId}/applications`, {
      artist_id: chosen,
      message: message.trim() || undefined,
    });
    setApplying(false);
    if (!result.ok) {
      setApplyError(result.error);
      return;
    }
    setMessage("");
    reload();
  };

  const withdraw = async (applicationId: string) => {
    await api.delete(`/api/v1/gigs/${gigId}/applications/${applicationId}`);
    reload();
  };

  const decide = async (applicationId: string, status: "accepted" | "declined") => {
    await api.patch(`/api/v1/gigs/${gigId}/applications/${applicationId}`, { status });
    applications.reload();
  };

  const close = async () => {
    await api.patch(`/api/v1/gigs/${gigId}`, {
      status: gig?.status === "open" ? "closed" : "open",
    });
    reload();
  };

  const removeGig = async () => {
    await api.delete(`/api/v1/gigs/${gigId}`);
    navigate("/classifieds");
  };

  if ((loading || initializing) && !gig) {
    return <div className="page page-narrow"><Spinner /></div>;
  }
  if (error || !gig) {
    return (
      <div className="page page-narrow">
        <Notice tone="error">{error ?? "That listing could not be found."}</Notice>
        <Link className="btn btn-ghost" to="/classifieds">Back to the classifieds</Link>
      </div>
    );
  }

  return (
    <article className="page page-narrow">
      <button type="button" className="btn btn-ghost" onClick={() => navigate(-1)}>
        <ChevronLeft size={16} aria-hidden /> Back
      </button>

      <header style={{ paddingTop: "var(--space-4)" }}>
        <p className="kicker kicker-accent">
          Classified · {gig.status === "open" ? "taking applications" : "closed"}
        </p>
        <h1 className="detail-title">{gig.title}</h1>
        <div style={{ marginTop: "var(--space-3)" }}>
          <Byline user={gig.posted_by} sub="posted this" />
        </div>
      </header>

      <Rule />

      <table className="table spec-table">
        <tbody>
          <tr>
            <th scope="row">Where</th>
            <td>
              {[gig.venue_name, gig.neighborhood, gig.city].filter(Boolean).join(", ")}
            </td>
          </tr>
          {gig.date_label ? (
            <tr>
              <th scope="row">When</th>
              <td>
                {gig.date_label}
                {gig.time_label ? `, ${gig.time_label}` : ""}
              </td>
            </tr>
          ) : null}
          <tr>
            <th scope="row">Pay</th>
            <td>
              {gig.pay_label ?? "Not stated"}
              {gig.pay_note ? ` — ${gig.pay_note}` : ""}
            </td>
          </tr>
          {gig.genre_label ? (
            <tr>
              <th scope="row">Wanted</th>
              <td>{gig.genre_label}</td>
            </tr>
          ) : null}
        </tbody>
      </table>

      {gig.description ? (
        <p className="prose" style={{ marginTop: "var(--space-4)" }}>{gig.description}</p>
      ) : null}

      {/* ── The reader's side ─────────────────────────────────────────── */}

      {(gig.my_applications ?? []).length > 0 ? (
        <>
          <SectionHead title="Your hand" />
          {gig.my_applications?.map((application) => (
            <div key={application.id} className="person-row">
              <span>
                <span className="byline-name">{application.artist?.name}</span>
                <span className="byline-sub"> · {application.status}</span>
              </span>
              <span className="comment-actions" style={{ marginTop: 0 }}>
                <MessageButton
                  anchor={{ application_id: application.id }}
                  recipientName={gig.posted_by.display_name}
                  label="Message"
                />
                {application.status === "pending" ? (
                  <button
                    type="button"
                    className="btn btn-ghost btn-quiet"
                    onClick={() => void withdraw(application.id)}
                  >
                    Withdraw
                  </button>
                ) : (
                  <Tag>{application.status}</Tag>
                )}
              </span>
            </div>
          ))}
        </>
      ) : null}

      {user && !gig.can_manage && gig.status === "open" && firstFree ? (
        <>
          <SectionHead title="Raise a hand" />
          {bandsFree.length > 1 ? (
            <select
              className="input"
              value={artistId || firstFree.id}
              onChange={(event) => setArtistId(event.target.value)}
              aria-label="Apply as"
            >
              {bandsFree.map((band) => (
                <option key={band.id} value={band.id}>{band.name}</option>
              ))}
            </select>
          ) : (
            <p className="form-note">Applying as {firstFree.name}</p>
          )}
          <textarea
            className="input"
            rows={3}
            maxLength={1000}
            placeholder="A line to the poster (optional)"
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            style={{ marginTop: "var(--space-2)" }}
          />
          <div className="actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={applying}
              onClick={() => void apply()}
            >
              Apply for this gig
            </button>
          </div>
          {applyError ? <Notice tone="error">{applyError}</Notice> : null}
        </>
      ) : null}

      {user && !gig.can_manage && myBands.length === 0 ? (
        <>
          <Rule />
          <Empty>
            Applying takes a band account —{" "}
            <Link to="/account">start yours under You</Link>.
          </Empty>
        </>
      ) : null}
      {!user && !initializing ? (
        <>
          <Rule />
          <Empty>
            <Link to="/sign-in">Sign in</Link> to apply with your band.
          </Empty>
        </>
      ) : null}

      {/* ── The poster's side ─────────────────────────────────────────── */}

      {gig.can_manage ? (
        <>
          <SectionHead
            title="Applications"
            count={
              typeof gig.application_count === "number"
                ? `${gig.application_count}`
                : undefined
            }
          />
          {applications.loading && !applications.data ? <Spinner /> : null}
          {applications.data && applications.data.applications.length === 0 ? (
            <Empty>No hands raised yet.</Empty>
          ) : null}
          {applications.data?.applications.map((application) => (
            <div key={application.id} className="comment">
              <div className="comment-head">
                <span>
                  {application.artist ? (
                    <Link
                      className="byline-name"
                      to={`/bands/${application.artist.slug}`}
                      style={{ textDecoration: "none", color: "inherit" }}
                    >
                      {application.artist.name}
                    </Link>
                  ) : (
                    <span className="byline-name">A band</span>
                  )}
                  <span className="byline-sub"> · {application.status}</span>
                </span>
                <span className="comment-actions" style={{ marginTop: 0 }}>
                  <MessageButton
                    anchor={{ application_id: application.id }}
                    recipientName={application.artist?.name ?? "the band"}
                    label="Message"
                  />
                  {application.status === "pending" ? (
                    <>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={() => void decide(application.id, "accepted")}
                      >
                        Accept
                      </button>
                      <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => void decide(application.id, "declined")}
                      >
                        Decline
                      </button>
                    </>
                  ) : null}
                </span>
              </div>
              {application.message ? (
                <p className="comment-body">{application.message}</p>
              ) : null}
            </div>
          ))}

          <div className="actions">
            <button type="button" className="btn btn-secondary" onClick={() => void close()}>
              {gig.status === "open" ? "Close the listing" : "Reopen the listing"}
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-quiet"
              onClick={() => void removeGig()}
            >
              Delete
            </button>
          </div>
        </>
      ) : null}
    </article>
  );
}
