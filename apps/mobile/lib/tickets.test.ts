/**
 * Ticket links point at other people's payment pages, so the two things worth
 * pinning are that we name the right host before sending someone there, and
 * that a scheme we should never open cannot get through.
 */

import { describe, expect, it } from "vitest";
import {
  isOpenableTicketUrl,
  ticketButtonLabel,
  ticketHost,
} from "@live-msc/shared";

describe("ticketHost", () => {
  it("names the host a reader is about to be sent to", () => {
    expect(ticketHost("https://dice.fm/event/abc123")).toBe("dice.fm");
    expect(ticketHost("https://www.eventbrite.com/e/999")).toBe("eventbrite.com");
    expect(ticketHost("http://mercuryeastpresents.com/tickets")).toBe(
      "mercuryeastpresents.com",
    );
  });

  it("keeps a subdomain that is not www, because it identifies the seller", () => {
    expect(ticketHost("https://tickets.bowerypresents.com/x")).toBe(
      "tickets.bowerypresents.com",
    );
  });

  it("refuses anything that is not http(s)", () => {
    // The server validates the scheme on write; a client must not be the only
    // thing standing between a stored `javascript:` URL and a navigation.
    expect(ticketHost("javascript:alert(1)")).toBeNull();
    expect(ticketHost("data:text/html,<script>alert(1)</script>")).toBeNull();
    expect(ticketHost("file:///etc/passwd")).toBeNull();
  });

  it("returns null for nothing, junk, and a bare path", () => {
    expect(ticketHost(null)).toBeNull();
    expect(ticketHost(undefined)).toBeNull();
    expect(ticketHost("")).toBeNull();
    expect(ticketHost("not a url")).toBeNull();
    expect(ticketHost("/tickets")).toBeNull();
  });
});

describe("ticketButtonLabel", () => {
  it("says where the money is going", () => {
    expect(ticketButtonLabel("https://dice.fm/event/abc")).toBe(
      "Buy tickets at dice.fm",
    );
  });

  it("falls back to a plain label rather than printing a raw URL", () => {
    expect(ticketButtonLabel("not a url")).toBe("Buy tickets");
    expect(ticketButtonLabel(null)).toBe("Buy tickets");
  });
});

describe("isOpenableTicketUrl", () => {
  it("gates the link opener on the same check as the label", () => {
    expect(isOpenableTicketUrl("https://dice.fm/e/1")).toBe(true);
    expect(isOpenableTicketUrl("javascript:alert(1)")).toBe(false);
    expect(isOpenableTicketUrl(null)).toBe(false);
  });
});
