import { Link, NavLink, Route, Routes } from "react-router-dom";
import { Bookmark, MapPin, Newspaper, Plus, Search, User } from "lucide-react";

import { useAuth } from "./context/AuthContext";
import { AccountPage } from "./pages/Account";
import { JoinPage, SignInPage } from "./pages/Auth";
import {
  ForgotPasswordPage,
  ResetPasswordPage,
  VerifyEmailPage,
} from "./pages/EmailFlows";
import { BandPage } from "./pages/Band";
import { BillPage } from "./pages/Bill";
import { MyListPage } from "./pages/MyList";
import { PlanPage } from "./pages/Plan";
import { PostShowPage } from "./pages/PostShow";
import { SearchPage } from "./pages/Search";
import { ShowDetailPage } from "./pages/ShowDetail";

const NAV = [
  { to: "/", label: "The Bill", icon: Newspaper, end: true },
  { to: "/plan", label: "The Plan", icon: MapPin, end: false },
  { to: "/search", label: "Look it up", icon: Search, end: false },
  { to: "/post", label: "Post a show", icon: Plus, end: false },
  { to: "/list", label: "Your list", icon: Bookmark, end: false },
  { to: "/account", label: "You", icon: User, end: false },
];

function todayLine(): string {
  return new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    day: "numeric",
    month: "long",
  }).format(new Date());
}

export function App() {
  const { user } = useAuth();

  return (
    <div className="shell">
      {/* A keyboard reader should be able to skip six nav links to reach the
          listings — this is the first focusable thing on the page. */}
      <a className="skip-link" href="#main">
        Skip to the listings
      </a>

      <header className="masthead">
        <div className="masthead-inner">
          <Link className="wordmark" to="/">
            Live Msc
          </Link>
          <div style={{ textAlign: "right" }}>
            <p className="kicker">{todayLine()}</p>
            <p className="kicker">
              A listings paper for live music
              {user?.home_city ? (
                <>
                  {" in "}
                  <span className="kicker-accent">{user.home_city}</span>
                </>
              ) : null}
            </p>
          </div>
        </div>
        <nav className="mainnav" aria-label="Sections">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end}>
              <Icon size={15} aria-hidden />
              {label}
            </NavLink>
          ))}
        </nav>
      </header>

      <main id="main">
        <Routes>
          <Route path="/" element={<BillPage />} />
          <Route path="/plan" element={<PlanPage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/post" element={<PostShowPage />} />
          <Route path="/list" element={<MyListPage />} />
          <Route path="/account" element={<AccountPage />} />
          <Route path="/shows/:eventId" element={<ShowDetailPage />} />
          <Route path="/bands/:handle" element={<BandPage />} />
          <Route path="/sign-in" element={<SignInPage />} />
          <Route path="/join" element={<JoinPage />} />
          {/* The routes our emails link to. */}
          <Route path="/verify-email" element={<VerifyEmailPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route
            path="*"
            element={
              <div className="page page-narrow">
                <h1 className="page-title">Not in this edition</h1>
                <p className="empty">
                  That page isn&rsquo;t here. <Link to="/">Back to the bill</Link>.
                </p>
              </div>
            }
          />
        </Routes>
      </main>
    </div>
  );
}
