import { describe, expect, it } from "vitest";

import { splitMentions } from "./mentions";

describe("splitMentions", () => {
  it("returns one plain segment when nothing matches", () => {
    expect(splitMentions("no handles here")).toEqual([{ text: "no handles here" }]);
    expect(splitMentions("")).toEqual([{ text: "" }]);
  });

  it("finds a mention at the start, middle and end", () => {
    expect(splitMentions("@ada was there")).toEqual([
      { text: "@ada", handle: "ada" },
      { text: " was there" },
    ]);
    expect(splitMentions("ask @ada about it")).toEqual([
      { text: "ask " },
      { text: "@ada", handle: "ada" },
      { text: " about it" },
    ]);
    expect(splitMentions("thanks @ada")).toEqual([
      { text: "thanks " },
      { text: "@ada", handle: "ada" },
    ]);
  });

  it("keeps punctuation next to a mention out of the handle", () => {
    expect(splitMentions("(@dust_bowl_99!)")).toEqual([
      { text: "(" },
      { text: "@dust_bowl_99", handle: "dust_bowl_99" },
      { text: "!)" },
    ]);
  });

  it("ignores handles that break the server's rule", () => {
    // Too short — under three characters is never a handle.
    expect(splitMentions("hey @ab there")).toEqual([{ text: "hey @ab there" }]);
  });

  it("matches case-insensitively and addresses the lowercase handle", () => {
    // The server's mention parser is case-insensitive — "@Ada" notifies ada —
    // so the client must print the same span as a link.
    expect(splitMentions("thanks @Ada_Fournier")).toEqual([
      { text: "thanks " },
      { text: "@Ada_Fournier", handle: "ada_fournier" },
    ]);
  });

  it("does not linkify the domain of an email address", () => {
    expect(splitMentions("write to booking@dusk.example")).toEqual([
      { text: "write to booking@dusk.example" },
    ]);
  });

  it("handles adjacent mentions", () => {
    expect(splitMentions("@ada @lin")).toEqual([
      { text: "@ada", handle: "ada" },
      { text: " " },
      { text: "@lin", handle: "lin" },
    ]);
  });

  it("caps a runaway handle at thirty characters", () => {
    const long = "a".repeat(40);
    const segments = splitMentions(`@${long}`);
    expect(segments[0]).toEqual({ text: `@${"a".repeat(30)}`, handle: "a".repeat(30) });
  });
});
