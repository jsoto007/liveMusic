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

export type UploadPurpose = "artist_audio" | "artist_photo" | "event_poster";

export interface User {
  id: string;
  display_name: string;
  role: UserRole;
  home_city: string | null;
  /** False until the reader clicks the link in their confirmation mail. */
  email_verified: boolean;
  created_at: string;
  /** Present only on the caller's own record. */
  email?: string;
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
  lineup?: LineupSlot[];
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
  /** R2's endpoint. The client posts the file here, not to the API. */
  url: string;
  fields: Record<string, string>;
  max_bytes: number;
  expires_at: string;
}

export interface AuthSession {
  user: User;
  access_token: string;
  /** Native clients only; browsers get an httpOnly cookie instead. */
  refresh_token?: string;
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
