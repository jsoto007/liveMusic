/**
 * The pages the links in our emails land on: confirming an address, asking for
 * a reset, and setting a new password.
 *
 * The "ask for a link" pages deliberately give the same answer whether or not
 * the address has an account — the server does too, and a UI that said "no
 * such account" would hand back the oracle the API just closed.
 */

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { CheckCircle } from "lucide-react";

import { Notice, Spinner } from "../components/Primitives";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";

const MIN_PASSWORD_LENGTH = 12;

/** Confirming an address. The token arrives in the query string. */
export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const { refreshProfile } = useAuth();

  const [state, setState] = useState<"working" | "done" | "failed">("working");
  const [message, setMessage] = useState<string | null>(null);
  // StrictMode double-invokes effects in development; without this the second
  // run redeems an already-used token and reports failure on a success.
  const attempted = useRef(false);

  useEffect(() => {
    if (attempted.current) return;
    attempted.current = true;

    if (!token) {
      setState("failed");
      setMessage("That link is missing its token.");
      return;
    }

    void api.post<{ verified: boolean }>("/api/v1/auth/verify-email", { token }).then(
      async (result) => {
        if (result.ok) {
          setState("done");
          await refreshProfile();
        } else {
          setState("failed");
          setMessage(result.error);
        }
      },
    );
  }, [token, refreshProfile]);

  if (state === "working") {
    return (
      <div className="page page-narrow">
        <Spinner label="Confirming" />
      </div>
    );
  }

  if (state === "failed") {
    return (
      <div className="page page-narrow">
        <h1 className="page-title">That link has expired</h1>
        <Notice tone="error">{message ?? "The link is no longer valid."}</Notice>
        <p className="form-note">
          Ask for a new one from <Link to="/account">your account</Link>.
        </p>
      </div>
    );
  }

  return (
    <div className="page page-narrow" style={{ textAlign: "center" }}>
      <CheckCircle
        size={34}
        strokeWidth={1.2}
        color="var(--color-accent)"
        aria-hidden
        style={{ margin: "var(--space-8) auto 0" }}
      />
      <h1 className="page-title" style={{ marginTop: "var(--space-3)" }}>
        You&rsquo;re confirmed
      </h1>
      <p className="listing-meta">That address is verified. Nothing else to do.</p>
      <Link className="btn btn-primary btn-block" to="/" style={{ marginTop: "var(--space-6)" }}>
        Read the bill
      </Link>
    </div>
  );
}

/** Asking for a reset link. */
export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    await api.post("/api/v1/auth/forgot-password", { email });
    setBusy(false);
    // Always the same outcome — the API will not say whether the address is
    // registered, and neither will this page.
    setSent(true);
  }

  if (sent) {
    return (
      <div className="page page-narrow">
        <h1 className="page-title">Check your email</h1>
        <p className="prose" style={{ marginTop: "var(--space-4)" }}>
          If that address has an account, a link to set a new password is on its
          way. It works once and expires in half an hour.
        </p>
        <Link className="btn btn-ghost" to="/sign-in">
          Back to sign in
        </Link>
      </div>
    );
  }

  return (
    <form className="page page-narrow" onSubmit={(e) => void handleSubmit(e)}>
      <h1 className="page-title">Reset your password</h1>
      <p className="form-note">We&rsquo;ll email you a link to set a new one.</p>

      <div className="field" style={{ marginTop: "var(--space-6)" }}>
        <label htmlFor="forgot-email">Email</label>
        <input
          id="forgot-email"
          className="input"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
      </div>

      <button type="submit" className="btn btn-primary btn-block" disabled={busy}
        style={{ marginTop: "var(--space-4)" }}>
        {busy ? "Sending…" : "Send the link"}
      </button>
      <p className="form-note" style={{ textAlign: "center" }}>
        <Link to="/sign-in">Back to sign in</Link>
      </p>
    </form>
  );
}

/** Setting the new password, from the link in the email. */
export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (password !== confirm) {
      setError("Those two passwords don't match.");
      return;
    }
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }

    setBusy(true);
    setError(null);
    const result = await api.post("/api/v1/auth/reset-password", { token, password });
    setBusy(false);

    if (!result.ok) {
      setError(result.error);
      return;
    }
    setDone(true);
  }

  if (!token) {
    return (
      <div className="page page-narrow">
        <h1 className="page-title">That link is incomplete</h1>
        <Notice tone="error">The reset link is missing its token.</Notice>
        <Link className="btn btn-ghost" to="/forgot-password">
          Ask for a new one
        </Link>
      </div>
    );
  }

  if (done) {
    return (
      <div className="page page-narrow">
        <h1 className="page-title">Password changed</h1>
        <p className="prose" style={{ marginTop: "var(--space-4)" }}>
          Every device that was signed in has been signed out — including, if it
          came to that, whoever prompted you to do this.
        </p>
        <button
          type="button"
          className="btn btn-primary btn-block"
          onClick={() => navigate("/sign-in")}
        >
          Sign in
        </button>
      </div>
    );
  }

  return (
    <form className="page page-narrow" onSubmit={(e) => void handleSubmit(e)}>
      <h1 className="page-title">Set a new password</h1>
      {error ? <Notice tone="error">{error}</Notice> : null}

      <div className="stack" style={{ marginTop: "var(--space-6)" }}>
        <div className="field">
          <label htmlFor="new-password">New password</label>
          <input
            id="new-password"
            className="input"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={MIN_PASSWORD_LENGTH}
            required
          />
          <p className="form-note">At least {MIN_PASSWORD_LENGTH} characters.</p>
        </div>
        <div className="field">
          <label htmlFor="confirm-password">Again</label>
          <input
            id="confirm-password"
            className="input"
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
          />
        </div>
      </div>

      <button type="submit" className="btn btn-primary btn-block" disabled={busy}
        style={{ marginTop: "var(--space-4)" }}>
        {busy ? "Saving…" : "Set the password"}
      </button>
    </form>
  );
}
