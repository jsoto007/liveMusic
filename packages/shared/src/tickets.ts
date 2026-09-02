/**
 * Where a listing's "buy tickets" link actually goes.
 *
 * A ticket link is typed in by whoever posted the show, so it points at
 * somebody else's site — a venue's box office, Dice, Eventbrite, a Bandcamp
 * page. Two consequences the UI has to honour:
 *
 * 1. **Say where it goes before it goes there.** A reader about to leave for a
 *    payment page deserves to see whose page it is, so the button names the
 *    host rather than saying an anonymous "Tickets".
 * 2. **Open it outside the app.** Never in a web view that shares our session
 *    or looks like part of Live Msc — this is a third-party page asking for
 *    card details, and it must wear its own address bar.
 */

/** The bare host of a ticket URL — "dice.fm", "www." trimmed — or null. */
export function ticketHost(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const { protocol, hostname } = new URL(url);
    // Only ever http(s). A `javascript:` or `data:` URL that reached the
    // database through an older client must not be handed to a link opener.
    if (protocol !== "http:" && protocol !== "https:") return null;
    return hostname.replace(/^www\./i, "") || null;
  } catch {
    return null;
  }
}

/**
 * The label for the buy button: names the host when we can read one.
 *
 * Falls back to a plain label rather than printing a raw URL — a long
 * ticketing URL in a button is unreadable and pushes the layout around.
 */
export function ticketButtonLabel(url: string | null | undefined): string {
  const host = ticketHost(url);
  return host ? `Buy tickets at ${host}` : "Buy tickets";
}

/**
 * Whether this URL is safe to hand to a link opener.
 *
 * The server validates the scheme on write, but a listing stored before that
 * check — or any future path that skips it — must not turn into a
 * `javascript:` navigation in a client.
 */
export function isOpenableTicketUrl(url: string | null | undefined): boolean {
  return ticketHost(url) !== null;
}
