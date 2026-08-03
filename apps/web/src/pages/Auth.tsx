/** Sign in and create an account. */

import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Notice } from "../components/Primitives";
import { useAuth } from "../context/AuthContext";

const MIN_PASSWORD_LENGTH = 12;

export function SignInPage() {
  const navigate = useNavigate();
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const message = await signIn(email, password);
    setBusy(false);
    if (message) {
      setError(message);
      return;
    }
    navigate("/");
  }

  return (
    <form className="page page-narrow" onSubmit={(e) => void handleSubmit(e)}>
      <h1 className="page-title">Sign in</h1>
      {error ? <Notice tone="error">{error}</Notice> : null}

      <div className="stack" style={{ marginTop: "var(--space-6)" }}>
        <div className="field">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            className="input"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            className="input"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
      </div>

      <button type="submit" className="btn btn-primary btn-block" disabled={busy}
        style={{ marginTop: "var(--space-4)" }}>
        {busy ? "Signing in…" : "Sign in"}
      </button>
      <p className="form-note" style={{ textAlign: "center" }}>
        <Link to="/forgot-password">Forgotten your password?</Link>
      </p>
      <p className="form-note" style={{ textAlign: "center" }}>
        No account yet? <Link to="/join">Join</Link>
      </p>
    </form>
  );
}

export function JoinPage() {
  const navigate = useNavigate();
  const { register } = useAuth();
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [homeCity, setHomeCity] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    // Checked here for a fast, friendly message; the server enforces the real
    // policy (length, common passwords, no email inside it) regardless.
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    setBusy(true);
    setError(null);
    const message = await register({ email, password, displayName, homeCity });
    setBusy(false);
    if (message) {
      setError(message);
      return;
    }
    navigate("/");
  }

  return (
    <form className="page page-narrow" onSubmit={(e) => void handleSubmit(e)}>
      <h1 className="page-title">Join</h1>
      <p className="form-note">Read the bill, keep shows, and post your own.</p>
      {error ? <Notice tone="error">{error}</Notice> : null}

      <div className="stack" style={{ marginTop: "var(--space-6)" }}>
        <div className="field">
          <label htmlFor="name">Your name</label>
          <input
            id="name"
            className="input"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            maxLength={80}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="join-email">Email</label>
          <input
            id="join-email"
            className="input"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="city">Home city</label>
          <input
            id="city"
            className="input"
            value={homeCity}
            onChange={(e) => setHomeCity(e.target.value)}
            placeholder="Providence"
            maxLength={120}
          />
        </div>
        <div className="field">
          <label htmlFor="join-password">Password</label>
          <input
            id="join-password"
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
      </div>

      <button type="submit" className="btn btn-primary btn-block" disabled={busy}
        style={{ marginTop: "var(--space-4)" }}>
        {busy ? "Creating…" : "Create account"}
      </button>
      <p className="form-note" style={{ textAlign: "center" }}>
        Already have one? <Link to="/sign-in">Sign in</Link>
      </p>
    </form>
  );
}
