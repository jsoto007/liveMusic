import { useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import {
  Bell,
  Bookmark,
  Mail,
  MapPin,
  Megaphone,
  Newspaper,
  Plus,
  Rss,
  Scale,
  Search,
  User,
} from "lucide-react";

import { LogoMark } from "./components/LogoMark";
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
import { ClassifiedsPage } from "./pages/Classifieds";
import { DeskPage } from "./pages/Desk";
import { FeedPageView } from "./pages/Feed";
import { GigDetailPage } from "./pages/GigDetail";
import { ListDetailPageView } from "./pages/ListDetail";
import { MessagesPage, ThreadPage } from "./pages/Messages";
import { MyListPage } from "./pages/MyList";
import { NotificationsPage } from "./pages/Notifications";
import { PlanPage } from "./pages/Plan";
import { PostGigPage } from "./pages/PostGig";
import { PostShowPage } from "./pages/PostShow";
import { ProfilePage } from "./pages/Profile";
import { SearchPage } from "./pages/Search";
import { ShowDetailPage } from "./pages/ShowDetail";
import { api } from "./lib/api";

const NAV = [
  { to: "/", label: "The Bill", icon: Newspaper, end: true },
  { to: "/following", label: "Following", icon: Rss, end: false },
  { to: "/plan", label: "The Plan", icon: MapPin, end: false },
  { to: "/classifieds", label: "Classifieds", icon: Megaphone, end: false },
  { to: "/search", label: "Look it up", icon: Search, end: false },
  { to: "/post", label: "Post a show", icon: Plus, end: false },
  { to: "/list", label: "Your list", icon: Bookmark, end: false },
  { to: "/account", label: "You", icon: User, end: false },
];

/**
 * The inbox link, with its unread figure. Re-checked on navigation and on a
 * slow poll — the bell should never be minutes stale, and either trigger is
 * one cheap COUNT.
 */
function InboxLink() {
  const { user } = useAuth();
  const location = useLocation();
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    if (!user) {
      setUnread(0);
      return;
    }
    let cancelled = false;
    const check = async () => {
      const result = await api.get<{ unread_count: number }>(
        "/api/v1/me/notifications/unread-count",
      );
      if (!cancelled && result.ok) setUnread(result.data.unread_count);
    };
    void check();
    const timer = window.setInterval(() => void check(), 90_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [user, location.pathname]);

  if (!user) return null;
  return (
    <NavLink to="/notifications">
      <Bell size={15} aria-hidden />
      Inbox
      {unread > 0 ? <span className="nav-count"> ({unread})</span> : null}
    </NavLink>
  );
}

/** The mailbox link, same posture as the inbox bell. */
function MessagesLink() {
  const { user } = useAuth();
  const location = useLocation();
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    if (!user) {
      setUnread(0);
      return;
    }
    let cancelled = false;
    const check = async () => {
      const result = await api.get<{ unread_count: number }>(
        "/api/v1/me/conversations/unread-count",
      );
      if (!cancelled && result.ok) setUnread(result.data.unread_count);
    };
    void check();
    const timer = window.setInterval(() => void check(), 90_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [user, location.pathname]);

  if (!user) return null;
  return (
    <NavLink to="/messages">
      <Mail size={15} aria-hidden />
      Messages
      {unread > 0 ? <span className="nav-count"> ({unread})</span> : null}
    </NavLink>
  );
}

/** Editors only — everyone else never sees the link, and the API 404s. */
function DeskLink() {
  const { user } = useAuth();
  if (user?.role !== "admin") return null;
  return (
    <NavLink to="/desk">
      <Scale size={15} aria-hidden />
      The desk
    </NavLink>
  );
}

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
            <LogoMark className="wordmark-mark" />
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
          <MessagesLink />
          <InboxLink />
          <DeskLink />
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
          <Route path="/u/:handle" element={<ProfilePage />} />
          <Route path="/lists/:listId" element={<ListDetailPageView />} />
          <Route path="/following" element={<FeedPageView />} />
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/classifieds" element={<ClassifiedsPage />} />
          <Route path="/gigs/new" element={<PostGigPage />} />
          <Route path="/gigs/:gigId" element={<GigDetailPage />} />
          <Route path="/messages" element={<MessagesPage />} />
          <Route path="/messages/:conversationId" element={<ThreadPage />} />
          <Route path="/desk" element={<DeskPage />} />
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
