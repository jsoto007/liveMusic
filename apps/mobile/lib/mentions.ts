/**
 * Split a comment body on @handles so they can print as links.
 *
 * The pattern mirrors the server's handle rule — 3–30 of a–z, 0–9 and `_` —
 * and a match glued to the tail of a word (an email address, mid-token `@`)
 * is left as plain text. No lookbehind: Hermes raises a SyntaxError on the
 * assertion, so the boundary is checked by hand.
 */

export interface MentionSegment {
  text: string;
  /** Set when this segment is a mention. `text` still carries the `@`. */
  handle?: string;
}

// Case-insensitive to match the server's parser — "@Ada" notifies ada, so it
// must also print as a link. Navigation lowercases; the server does too.
const MENTION = /@([a-z0-9_]{3,30})/gi;

export function splitMentions(body: string): MentionSegment[] {
  const segments: MentionSegment[] = [];
  let last = 0;

  for (const match of body.matchAll(MENTION)) {
    const index = match.index ?? 0;
    const text = match[0] ?? "";
    const before = index > 0 ? body[index - 1] : "";
    // "name@example" is an address, not a mention of @example.
    if (before && /[a-z0-9_]/i.test(before)) continue;

    if (index > last) segments.push({ text: body.slice(last, index) });
    // The handle is the *address*, so it is normalized the way the server
    // stores it; the text keeps whatever casing the writer typed.
    segments.push({ text, handle: (match[1] ?? "").toLowerCase() });
    last = index + text.length;
  }

  if (last < body.length || segments.length === 0) {
    segments.push({ text: body.slice(last) });
  }
  return segments;
}
