/**
 * The wire shapes, mirroring `apps/server/app/routes/serializers.py`.
 *
 * Every entity carries both the raw value and the label the server rendered
 * from it (`price_cents` + `price_label`, `starts_at` + `time_label`). Print
 * the label; compute on the raw value. Labels are built server-side so the web
 * and mobile listings read identically — never re-derive one on the client.
 */

export type UserRole = "listener" | "artist" | "admin";

export type EventStatus = "draft" | "published" | "cancelled";

export type AgeRestriction = "all_ages" | "18_plus" | "21_plus";

export type Genre =
  | "rock_punk"
  | "jazz"
  | "classical"
  | "electronic"
  | "folk_country"
  | "metal"
  | "hip_hop"
  | "gospel_soul"
  | "open_mic"
  | "festival"
  | "other";

/** Which section of the paper a listing sets into. */
export type DayBucket = "tonight" | "tomorrow" | "weekend" | "later";

export type UploadPurpose =
  | "artist_audio"
  | "artist_photo"
  | "event_poster"
  | "user_avatar";

export interface User {
  id: string;
  /** The public @name the profile lives at. Lowercase, unique. */
  handle: string;
  display_name: string;
  avatar_url: string | null;
  bio: string | null;
  role: UserRole;
  home_city: string | null;
  /** False until the reader clicks the link in their confirmation mail. */
  email_verified: boolean;
  created_at: string;
  /** Present only on the caller's own record. */
  email?: string;
}

/** The byline form of a person — what comments, followers and bells carry. */
export interface UserCard {
  id: string;
  handle: string;
  display_name: string;
  avatar_url: string | null;
  /** Search results include it. */
  bio?: string | null;
  is_following?: boolean;
  is_self?: boolean;
}

/** A public profile page. Never carries an email. */
export interface Profile extends UserCard {
  bio: string | null;
  home_city: string | null;
  role: UserRole;
  member_since: string;
  follower_count: number;
  following_count: number;
  public_list_count: number;
  review_count: number;
  artists: Artist[];
  is_self: boolean;
  /** Present only for a signed-in viewer looking at someone else. */
  is_following?: boolean;
  /** Whether the *viewer* has blocked this person. The reverse direction is
   *  never serialized. */
  is_blocked?: boolean;
}

export interface Venue {
  id: string;
  name: string;
  slug: string;
  address: string | null;
  neighborhood: string | null;
  city: string;
  latitude: number | null;
  longitude: number | null;
  /** IANA zone. Listing times are already rendered in it server-side. */
  timezone: string;
}

export interface AudioSample {
  id: string;
  title: string;
  duration_seconds: number | null;
  duration_label: string | null;
  content_type: string;
  /**
   * A short-lived signed URL, minted per request. Never cache it — it stops
   * working when the signature ages out.
   */
  stream_url: string | null;
  created_at: string;
}

export interface ArtistMember {
  name: string;
  instrument: string | null;
}

export interface Artist {
  id: string;
  name: string;
  slug: string;
  city: string | null;
  neighborhood: string | null;
  one_liner: string | null;
  style_tags: string[];
  available_for_hire: boolean;
  verified: boolean;
  photo_url: string | null;
  follower_count?: number;
  is_following?: boolean;
  /** Detail view only. */
  bio?: string | null;
  sounds_like?: string | null;
  members?: ArtistMember[];
  samples?: AudioSample[];
}

export interface LineupSlot {
  name: string;
  note: string | null;
  starts_at: string | null;
  time_label: string | null;
}

/** Aggregate rating block; rides on event detail and review listings. */
export interface RatingSummary {
  review_count: number;
  avg_rating: number | null;
  rating_label: string | null;
}

export interface EventListing {
  id: string;
  headline: string;
  support_line: string | null;
  genre: Genre;
  genre_label: string;
  status: EventStatus;
  starts_at: string;
  doors_at: string | null;
  time_label: string | null;
  doors_label: string | null;
  day_bucket: DayBucket;
  day_label: string;
  date_long: string;
  /** `null` means the price was never stated; `0` means free. */
  price_cents: number | null;
  price_label: string | null;
  age_restriction: AgeRestriction;
  age_label: string;
  short_line: string | null;
  poster_url: string | null;
  /** Set only when the poster came from an openly-licensed source this app
   * attached itself (e.g. Wikimedia Commons) rather than a band's own
   * upload — CC BY / CC BY-SA require a visible credit wherever shown. */
  poster_credit: string | null;
  venue: Venue | null;
  artist: Pick<Artist, "id" | "name" | "slug"> | null;
  saved: boolean;
  going: boolean;
  /** True once the doors are behind you — listings linger a few hours. */
  already_started: boolean;
  /** Present on the nearby (map) response only. */
  distance_miles?: number;
  distance_label?: string;
  pin_number?: number;
  /** Detail view only. */
  blurb?: string | null;
  ticket_url?: string | null;
  published_at?: string | null;
  cancelled?: boolean;
  /**
   * Whether this reader may attach a poster to this show. Decided by the
   * server from the authenticated user — never inferred here from the artist
   * id, which the client also holds but cannot verify ownership of. Absent on
   * list responses, and `undefined` is treated as "no".
   */
  can_manage?: boolean;
  lineup?: LineupSlot[];
  /** Engagement counts — present where the server computed them (detail
   *  pages), absent elsewhere. Absent ≠ zero. */
  comment_count?: number;
  review_count?: number;
  avg_rating?: number | null;
  rating_label?: string | null;
}

/** The listings feed. `count` is this page; `total` is the whole filtered set. */
export interface BillPage {
  events: EventListing[];
  sections: DaySection[];
  count: number;
  total: number;
  has_more: boolean;
  /** The 30-day window hit its cap; some listings are not represented. */
  window_truncated: boolean;
}

export interface DaySection {
  key: DayBucket;
  label: string;
  count_label: string;
  events: EventListing[];
}

/** One address suggestion from the geocoding proxy. */
export interface Place {
  label: string;
  name: string;
  city: string | null;
  neighborhood: string | null;
  postcode: string | null;
  country: string | null;
  latitude: number;
  longitude: number;
}

export interface PlaceSearchResult {
  places: Place[];
  /** False when LocationIQ has no key set — fall back to a plain text field
   *  rather than showing a typeahead that can never suggest anything. */
  configured: boolean;
}

export interface EmailPreferences {
  notify_new_shows: boolean;
  notify_show_reminders: boolean;
  unsubscribed_all: boolean;
}

export interface UploadTicket {
  upload_id: string;
  /** R2's endpoint. The client PUTs the file body here, not to the API. */
  url: string;
  key: string;
  /** Headers to send with the PUT, exactly as given — Content-Type is signed. */
  headers: Record<string, string>;
  max_bytes: number;
  expires_at: string;
}

export interface AuthSession {
  user: User;
  access_token: string;
  /** Native clients only; browsers get an httpOnly cookie instead. */
  refresh_token?: string;
}

// ── Lists ──────────────────────────────────────────────────────────────────

export interface EventList {
  id: string;
  name: string;
  description: string | null;
  is_public: boolean;
  created_at: string;
  updated_at: string;
  item_count?: number;
  count_label?: string;
  owner?: UserCard;
}

export interface ListEntry {
  event: EventListing;
  note: string | null;
  added_at: string;
}

export interface ListDetailPage {
  list: EventList;
  entries: ListEntry[];
  total: number;
  has_more: boolean;
  can_manage: boolean;
}

// ── Comments and reviews ───────────────────────────────────────────────────

export interface Comment {
  id: string;
  event_id: string;
  author: UserCard;
  body: string;
  like_count: number;
  viewer_liked: boolean;
  can_delete: boolean;
  created_at: string;
}

export interface CommentPage {
  comments: Comment[];
  total: number;
  has_more: boolean;
}

export interface Review {
  id: string;
  event_id: string;
  author: UserCard;
  /** 1–5. */
  rating: number;
  rating_label: string;
  body: string | null;
  can_edit: boolean;
  created_at: string;
  edited: boolean;
  /** Present on profile review listings. */
  event?: EventListing;
}

export interface ReviewPage extends RatingSummary {
  reviews: Review[];
  total: number;
  has_more: boolean;
  my_review: Review | null;
}

// ── Notifications ──────────────────────────────────────────────────────────

export type NotificationKind =
  | "new_follower"
  | "event_comment"
  | "comment_like"
  | "mention"
  | "event_review"
  | "gig_application"
  | "gig_accepted"
  | "gig_declined"
  | "image_removed";

export interface Notification {
  id: string;
  kind: NotificationKind;
  /** The sentence, built server-side; print it as-is. */
  line: string;
  actor: UserCard | null;
  event_id: string | null;
  event_headline: string | null;
  gig_id: string | null;
  gig_title: string | null;
  comment_excerpt: string | null;
  read: boolean;
  created_at: string;
}

export interface NotificationPage {
  notifications: Notification[];
  total: number;
  has_more: boolean;
  unread_count: number;
}

// ── Reports ────────────────────────────────────────────────────────────────

export type ReportReason = "spam" | "harassment" | "inappropriate" | "other";

export const REPORT_REASONS: ReadonlyArray<{ value: ReportReason; label: string }> = [
  { value: "spam", label: "Spam" },
  { value: "harassment", label: "Harassment" },
  { value: "inappropriate", label: "Inappropriate" },
  { value: "other", label: "Something else" },
];

// ── Gigs ───────────────────────────────────────────────────────────────────

export type GigStatus = "open" | "closed";

export type GigApplicationStatus = "pending" | "accepted" | "declined";

export interface Gig {
  id: string;
  title: string;
  city: string;
  neighborhood: string | null;
  venue_name: string | null;
  starts_at: string | null;
  date_label: string | null;
  time_label: string | null;
  /** Integer cents; `null` means "pay not stated". */
  pay_cents: number | null;
  pay_label: string | null;
  pay_note: string | null;
  genre: Genre | null;
  genre_label: string | null;
  status: GigStatus;
  posted_by: UserCard;
  created_at: string;
  /** Detail view only. */
  description?: string;
  can_manage?: boolean;
  /** Poster's own reads only. */
  application_count?: number;
  /** The viewer's own hands raised on this gig. */
  my_applications?: GigApplication[];
}

export interface GigApplication {
  id: string;
  gig_id: string;
  artist_id: string;
  message: string | null;
  status: GigApplicationStatus;
  created_at: string;
  artist?: Artist;
  gig?: Gig;
}

export interface GigPage {
  gigs: Gig[];
  total: number;
  has_more: boolean;
}

// ── The Following feed ─────────────────────────────────────────────────────

export type FeedItemType = "new_show" | "review" | "list_add";

export interface FeedItem {
  type: FeedItemType;
  at: string;
  /** The sentence, built server-side. */
  line: string;
  event: EventListing;
  actor: UserCard | null;
  review?: Review;
  list?: EventList;
}

export interface FeedPage {
  items: FeedItem[];
  total: number;
  has_more: boolean;
  window_days: number;
  window_truncated: boolean;
}

// ── People pages ───────────────────────────────────────────────────────────

export interface PeoplePage {
  people: UserCard[];
  total: number;
  has_more: boolean;
}

// ── Messages ───────────────────────────────────────────────────────────────

export interface ChatMessage {
  id: string;
  conversation_id: string;
  sender: UserCard;
  body: string;
  created_at: string;
}

export interface Conversation {
  id: string;
  /** The other party, from the viewer's side of the thread. */
  with: UserCard;
  /** "About <band>" / "About “<gig>”" when a hire anchor opened the thread. */
  subject: string | null;
  artist_id: string | null;
  gig_id: string | null;
  unread: boolean;
  last_message_at: string;
  created_at: string;
  /** List responses only. */
  last_line?: string | null;
  last_from_me?: boolean;
}

export interface ConversationPage {
  conversations: Conversation[];
  total: number;
  has_more: boolean;
}

export interface MessagePage {
  messages: ChatMessage[];
  total: number;
  has_more: boolean;
}

// ── The photo desk (admin) ─────────────────────────────────────────────────

export type ImageReviewStatus = "pending" | "approved" | "removed";

export interface ImageReview {
  id: string;
  purpose: UploadPurpose;
  /** Short-lived presigned URL, minted per request. */
  image_url: string | null;
  status: ImageReviewStatus;
  uploader: UserCard | null;
  created_at: string;
  reviewed_at: string | null;
}

// ── Admin reports (the desk) ───────────────────────────────────────────────

export interface AdminReport {
  id: string;
  subject_type: "comment" | "review" | "user" | "event" | "removed";
  reason: ReportReason;
  detail: string | null;
  status: "open" | "resolved" | "dismissed";
  created_at: string;
  resolved_at: string | null;
  reporter?: UserCard;
  comment?: Comment;
  review?: Review;
  reported_user?: UserCard;
  event?: EventListing;
}

/** Display order and copy for the genre chips, matching the paper's buckets. */
export const GENRES: ReadonlyArray<{ value: Genre; label: string }> = [
  { value: "rock_punk", label: "Rock & punk" },
  { value: "jazz", label: "Jazz" },
  { value: "classical", label: "Classical" },
  { value: "electronic", label: "Electronic" },
  { value: "folk_country", label: "Folk & country" },
  { value: "metal", label: "Metal" },
  { value: "hip_hop", label: "Hip-hop" },
  { value: "gospel_soul", label: "Gospel & soul" },
  { value: "open_mic", label: "Open mic" },
  { value: "festival", label: "Festival" },
  { value: "other", label: "Other" },
];

/**
 * House stock photographs, one per genre — the stand-in plate for a listing
 * whose poster has not been uploaded yet, so no post ever prints without a
 * photograph. Derivatives of the original editorial images checked in under
 * `apps/server/seed_photos/`: no performer likenesses, no logos, no
 * third-party credit line required. The web serves them from `public/stock/`;
 * mobile bundles the same files from `assets/stock/` (held in lockstep by
 * `apps/mobile/lib/stockPosters.test.ts`).
 */
export const STOCK_POSTERS: Readonly<Record<Genre, string>> = {
  rock_punk: "rock_punk.jpg",
  jazz: "jazz.jpg",
  classical: "classical.jpg",
  electronic: "electronic.jpg",
  folk_country: "folk_country.jpg",
  metal: "metal.jpg",
  hip_hop: "hip_hop.jpg",
  gospel_soul: "gospel_soul.jpg",
  open_mic: "open_mic.jpg",
  festival: "festival.jpg",
  other: "other.jpg",
};

export const AGE_OPTIONS: ReadonlyArray<{ value: AgeRestriction; label: string }> = [
  { value: "all_ages", label: "All ages" },
  { value: "18_plus", label: "18+" },
  { value: "21_plus", label: "21+" },
];

export const DAY_FILTERS: ReadonlyArray<{ value: "all" | DayBucket; label: string }> = [
  { value: "all", label: "All" },
  { value: "tonight", label: "Tonight" },
  { value: "tomorrow", label: "Tomorrow" },
  { value: "weekend", label: "Weekend" },
];
