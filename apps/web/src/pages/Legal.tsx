/**
 * The terms of use and the privacy policy.
 *
 * These are not decoration. The App Store listing needs a reachable privacy
 * policy URL, and Guideline 1.2 expects an app carrying user-generated content
 * to put terms — including an explicit no-tolerance line about objectionable
 * content — in front of people before they post. The mobile app links here
 * from Join and from the account screen, so there is one copy of each rather
 * than one per platform.
 *
 * Written from what the app actually does, checked against the schema and the
 * routes rather than from a template. Two things still need a human:
 * `OPERATOR` below is a placeholder for the legal entity, and a lawyer should
 * read both documents before launch. Everything else is accurate today, and
 * needs updating whenever the data the server stores changes.
 */

import { useEffect } from "react";
import { Link } from "react-router-dom";

/** The entity behind the paper. Replace before launch. */
const OPERATOR = "Live Msc";
const CONTACT = "hello@livemsc.org";
const LAST_UPDATED = "2 September 2026";

/** Sets the document title, so a policy tab is identifiable among twenty. */
function useDocumentTitle(title: string) {
  useEffect(() => {
    const previous = document.title;
    document.title = `${title} — Live Msc`;
    return () => {
      document.title = previous;
    };
  }, [title]);
}

function Masthead({ title }: { title: string }) {
  return (
    <>
      <p className="kicker">Live Msc</p>
      <h1 className="display display-h2">{title}</h1>
      <p className="kicker" style={{ marginTop: "var(--space-2)" }}>
        Last updated {LAST_UPDATED}
      </p>
      <hr className="rule rule-strong" style={{ marginTop: "var(--space-4)" }} />
    </>
  );
}

export function TermsPage() {
  useDocumentTitle("Terms of use");

  return (
    <div className="page page-narrow">
      <Masthead title="Terms of use" />

      <p>
        Live Msc is a listings paper for live music. Bands post shows, everyone
        else reads tonight&rsquo;s bill, marks what they are going to, and finds
        the room. These terms cover using it. By creating an account you accept
        them.
      </p>

      <h2 className="display display-h4">Your account</h2>
      <p>
        You need to be 13 or older to hold an account. Keep your password to
        yourself; you are responsible for what is posted from your account. Give
        us an address you actually read — it is how we send a password reset,
        and it is the only way we can reach you.
      </p>
      <p>
        You can delete your account at any time, from the account screen in the
        app or on this site. Deletion is permanent and immediate: your profile,
        your list, your band pages and everything you have written go with it.
        Shows you posted that have not happened yet are cancelled, so nobody
        turns up to a night with no band behind it; listings for nights that
        already happened stay in the record with your name removed.
      </p>

      <h2 className="display display-h4">What you post</h2>
      <p>
        What you write stays yours. By posting it you give {OPERATOR} permission
        to show it in the paper — on the web, in the apps, and in the emails
        readers have asked for — and nothing beyond that. We do not sell it and
        we do not license it on.
      </p>
      <p>
        A listing is a claim that a show is happening. Post shows you are
        actually involved in, with details that are true: the room, the date,
        the door price, the age policy. A ticket link must point at the page
        where the tickets are genuinely sold.
      </p>

      <h2 className="display display-h4">
        There is no tolerance for objectionable content
      </h2>
      <p>
        This is the short version, and it is not negotiable. Do not post, send
        or upload:
      </p>
      <ul>
        <li>
          content that harasses, threatens, bullies or targets anyone, or that
          attacks people for who they are;
        </li>
        <li>
          sexual content involving minors, in any form — this is reported to the
          authorities, not merely deleted;
        </li>
        <li>
          content that is violent, hateful, or that promotes self-harm or
          illegal activity;
        </li>
        <li>
          impersonation of a band, a venue, a promoter or another person;
        </li>
        <li>
          spam, scams, fake listings, or a ticket link that goes anywhere other
          than a real ticket page;
        </li>
        <li>anyone else&rsquo;s photograph or artwork without their permission.</li>
      </ul>
      <p>
        Every listing, comment, review, photograph and profile can be reported,
        from a flag on the item itself. Reports go to the editors, who read them
        and act — removing the content, taking a listing off the bill, or
        removing the account. You can also block another reader, which hides you
        from each other in both directions.
      </p>
      <p>
        We may remove content or close an account that breaks these rules,
        without notice where the content is serious enough to warrant it.
      </p>

      <h2 className="display display-h4">Tickets are not sold here</h2>
      <p>
        Live Msc does not sell tickets and takes no cut of any sale. A
        &ldquo;buy tickets&rdquo; link hands you to whoever the band or venue
        named — a box office, a ticketing site, a Bandcamp page — and that sale
        is between you and them, under their terms. We do not check those pages
        and we cannot help with a refund. Door prices in a listing are what the
        poster typed and can be wrong or out of date; the venue&rsquo;s own page
        is the authority.
      </p>

      <h2 className="display display-h4">What we do not promise</h2>
      <p>
        The paper is provided as it is. We do not guarantee that a listing is
        accurate, that a show will happen, or that the service will be
        available without interruption. To the extent the law allows,{" "}
        {OPERATOR} is not liable for a wasted journey, a cancelled night, or a
        transaction with a third-party ticket seller.
      </p>

      <h2 className="display display-h4">Changes and endings</h2>
      <p>
        We may change these terms. Material changes will be posted here with a
        new date at the top, and continuing to use the app after that means you
        accept them. You may stop using Live Msc at any time by deleting your
        account.
      </p>

      <h2 className="display display-h4">Reaching us</h2>
      <p>
        Write to <a href={`mailto:${CONTACT}`}>{CONTACT}</a>. To report
        something urgent, use the flag on the item — that goes straight to the
        editors&rsquo; queue.
      </p>

      <hr className="rule" style={{ marginTop: "var(--space-6)" }} />
      <p className="kicker">
        See also the <Link to="/privacy">privacy policy</Link>.
      </p>
    </div>
  );
}

export function PrivacyPage() {
  useDocumentTitle("Privacy policy");

  return (
    <div className="page page-narrow">
      <Masthead title="Privacy policy" />

      <p>
        This says what Live Msc stores, why, and what you can do about it. It is
        written from the actual database, not from a template.
      </p>

      <h2 className="display display-h4">What we store</h2>
      <ul>
        <li>
          <strong>Your account.</strong> Email address, display name, the
          @handle your page lives at, an optional bio, home city and portrait.
          Your password is stored only as a bcrypt hash — we cannot read it.
        </li>
        <li>
          <strong>What you write.</strong> Listings, comments, reviews, lists,
          classified adverts, and letters between readers. Messages between two
          readers are private to those two people, but they are not
          end-to-end encrypted: they are stored on our server and an
          administrator could technically read them. Do not send anything you
          would not want read.
        </li>
        <li>
          <strong>Photographs and audio you upload.</strong> Posters, band
          photos, portraits and sound samples, held in Cloudflare R2 object
          storage.
        </li>
        <li>
          <strong>Who you follow, block and are going to see.</strong>
        </li>
        <li>
          <strong>Sign-in records.</strong> Refresh tokens tied to your
          sessions, and a count of failed sign-in attempts so an account can be
          locked against guessing.
        </li>
        <li>
          <strong>Server logs</strong> containing a request identifier, the
          route and the timing. Tokens, passwords and full email addresses are
          never written to a log.
        </li>
      </ul>

      <h2 className="display display-h4">Location</h2>
      <p>
        The map asks for your location only when you tap <em>use my location</em>,
        never in the background and never on first launch. The coordinates are
        sent to our server to work out which shows are nearest to you, and they
        are <strong>not written to the database</strong> — the query is answered
        and the coordinates are gone. If you do not grant it, the map centres on
        your home city instead, or on nothing in particular.
      </p>
      <p>
        When a band posts a show, the venue address is sent to LocationIQ to
        turn it into a map pin. That is an address for a public venue, not a
        person&rsquo;s location.
      </p>

      <h2 className="display display-h4">What we do not do</h2>
      <p>
        There is no advertising, no analytics SDK, no tracking across other
        companies&rsquo; apps or websites, and no sale of anyone&rsquo;s data to
        anyone. The apps contain no third-party trackers.
      </p>

      <h2 className="display display-h4">Who else sees it</h2>
      <p>Only the services that make the paper work:</p>
      <ul>
        <li>
          <strong>Render</strong> — hosting for the site, the API and the
          database.
        </li>
        <li>
          <strong>Cloudflare R2</strong> — storage for uploaded images and
          audio.
        </li>
        <li>
          <strong>Resend</strong> — sending the mail you have asked for.
        </li>
        <li>
          <strong>LocationIQ</strong> — turning a venue address into
          coordinates.
        </li>
        <li>
          <strong>Apple Maps</strong> — drawing the map on iOS, on the device.
        </li>
      </ul>
      <p>
        We will also hand over information where the law requires it, and where
        it concerns the safety of a child.
      </p>

      <h2 className="display display-h4">Email</h2>
      <p>
        Two kinds of mail are optional and can be switched off from your
        account: a note when a band you follow posts a show, and a reminder the
        day before a show you said you were going to. Every one of them carries
        a one-click unsubscribe. Mail about your account itself — confirming
        your address, resetting your password — is not optional, because
        suppressing a password reset would lock you out.
      </p>

      <h2 className="display display-h4">How long it is kept</h2>
      <p>
        Until you delete it. Delete your account and it goes, permanently and
        immediately: your profile, your list, your bands, your uploads and
        everything you have written. Upcoming shows you posted are cancelled;
        past listings remain as a record of the night, with your name off them.
        Unfinished uploads are swept away automatically.
      </p>

      <h2 className="display display-h4">Your rights</h2>
      <p>
        You can edit your profile and preferences from your account, and delete
        the whole account from the same screen — in the app and on this site,
        without asking us. For a copy of your data, or anything else, write to{" "}
        <a href={`mailto:${CONTACT}`}>{CONTACT}</a>.
      </p>

      <h2 className="display display-h4">Children</h2>
      <p>
        Live Msc is not for under-13s and we do not knowingly hold data about
        one. If you believe we do, write to{" "}
        <a href={`mailto:${CONTACT}`}>{CONTACT}</a> and it will be deleted.
      </p>

      <hr className="rule" style={{ marginTop: "var(--space-6)" }} />
      <p className="kicker">
        See also the <Link to="/terms">terms of use</Link>.
      </p>
    </div>
  );
}
