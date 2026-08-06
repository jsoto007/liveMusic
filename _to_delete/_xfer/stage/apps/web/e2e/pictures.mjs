/**
 * End-to-end check of the picture flows, driven through the real UI against
 * the real Flask API. Only storage is local (see apps/server/devserver.py).
 *
 * What it walks:
 *   1. join → create a band → add a band photo
 *   2. post a show WITH a poster from the main form
 *   3. post a show WITHOUT one, then add the poster from the show page
 *   4. replace that poster
 *   5. a second account must not be offered the control on someone else's show
 *   6. with storage unconfigured — production's current state — the reader is
 *      told so, in words, instead of the button failing silently
 */
import { chromium } from "playwright";

const BASE = "http://localhost:5055";
const results = { pass: [], fail: [] };
const check = (name, ok, detail = "") =>
  (ok ? results.pass : results.fail).push(`${name}${detail ? ` — ${detail}` : ""}`);

// A tiny valid PNG, so the server's content-type check has something real.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAYAAADED76LAAAAHUlEQVR42mP8z8BQz0AEYBxVSF+F" +
    "/xkYGP4DAG9lB/1H8YsyAAAAAElFTkSuQmCC",
  "base64",
);
const file = (name) => ({ name, mimeType: "image/png", buffer: PNG });

const browser = await chromium.launch();
let crashed = null;
try {

async function session() {
  const context = await browser.newContext({ viewport: { width: 1100, height: 1000 } });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  return { context, page, errors };
}

async function join(page, email) {
  await page.goto(`${BASE}/join`);
  await page.locator("#name").fill(email.split("@")[0]);
  await page.locator("#join-email").fill(email);
  await page.locator("#city").fill("Providence");
  await page.locator("#join-password").fill("a-long-enough-passphrase-9");
  await page.locator('button[type="submit"]').click();
  await page.waitForTimeout(2000);
  const shown = await page.locator("body").innerText();
  if (page.url().includes("/join")) throw new Error(`join failed: ${shown.slice(0, 300)}`);
}

async function postShow(page, headline, withPoster) {
  await page.goto(`${BASE}/post`);
  await page.waitForTimeout(400);
  await page.locator("#headline").fill(headline);
  await page.locator("#venue").fill("Dusk");
  await page.locator("#city").fill("Providence");
  await page.locator("#date").fill("2026-09-12");
  await page.locator("#time").fill("21:00");
  if (withPoster) await page.locator("#poster").setInputFiles(file("poster.png"));
  await page.locator('button[type="submit"]').click();
  await page.waitForTimeout(2000);
}

// ── Account one ────────────────────────────────────────────────────────────
const one = await session();
await join(one.page, "band@example.com");
check("account created and signed in", !one.page.url().includes("/join"), one.page.url());

// ── The poster field is in the form proper, not folded away ───────────────
await one.page.goto(`${BASE}/post`);
await one.page.waitForTimeout(500);
check("poster field is visible without opening 'Add the details'", await one.page.locator("#poster").isVisible());
const accept = await one.page.locator("#poster").getAttribute("accept");
check(
  "poster picker offers exactly the formats the server signs",
  accept === "image/jpeg,image/png,image/webp,image/avif",
  accept,
);

// ── Band photo ─────────────────────────────────────────────────────────────
await one.page.goto(`${BASE}/account`);
await one.page.waitForTimeout(600);
await one.page.getByLabel("Band name").fill("Bloodroot Choir");
await one.page.getByRole("button", { name: /^Create$/ }).click();
await one.page.waitForTimeout(2000);
const photoButton = one.page.getByRole("button", { name: /Add a band photo/i });
check("band photo control offered to its owner", (await photoButton.count()) === 1);

if (await photoButton.count()) {
  await one.page.locator('input[type="file"]').first().setInputFiles(file("band.png"));
  await one.page.waitForTimeout(3000);
  check("band photo uploaded and rendered", (await one.page.locator(".plate img").count()) === 1);
  check(
    "the button now offers to replace it",
    (await one.page.getByRole("button", { name: /Replace the photo/i }).count()) === 1,
  );
}

// ── A show posted with a poster ────────────────────────────────────────────
await postShow(one.page, "Bloodroot Choir", true);
check("show posted", /It.s on the bill/i.test(await one.page.locator("body").innerText()));
check(
  "no poster warning when the upload worked",
  !/did not upload/i.test(await one.page.locator("body").innerText()),
);

await one.page.getByRole("button", { name: /See it in the bill/i }).click();
await one.page.waitForTimeout(1500);
const withPosterUrl = one.page.url();
check("poster attached during posting is on the show page", (await one.page.locator(".plate img").count()) === 1);

// ── A show posted without one, then fixed from the show page ──────────────
await postShow(one.page, "Second Bill", false);
await one.page.getByRole("button", { name: /See it in the bill/i }).click();
await one.page.waitForTimeout(1500);
const showUrl = one.page.url();

check("a bare show shows the empty plate", (await one.page.locator(".plate-empty").count()) === 1);
const addPoster = one.page.getByRole("button", { name: /Add a poster/i });
check("the owner is offered 'Add a poster' after the fact", (await addPoster.count()) === 1, showUrl);

if (await addPoster.count()) {
  await one.page.locator('input[type="file"]').first().setInputFiles(file("late.png"));
  await one.page.waitForTimeout(2500);
  check("poster added after the show was posted", (await one.page.locator(".plate img").count()) === 1);

  const firstSrc = await one.page.locator(".plate img").first().getAttribute("src");
  await one.page.getByRole("button", { name: /Replace the poster/i }).click({ trial: true });
  await one.page.locator('input[type="file"]').first().setInputFiles(file("replacement.png"));
  await one.page.waitForTimeout(2500);
  const secondSrc = await one.page.locator(".plate img").first().getAttribute("src");
  check("replacing the poster lands on a new object", firstSrc !== secondSrc, `${firstSrc} → ${secondSrc}`);
}

// ── A hard load must give the owner the same page as a click-through ──────
// Regression: the detail was fetched on mount, before the silent refresh
// restored the session, so opening a show from a link or a browser reload
// answered with the anonymous view — no poster control, and the reader's own
// saved shows shown as unsaved.
await one.page.goto(showUrl, { waitUntil: "load" });
await one.page.waitForTimeout(3000);
check(
  "the owner keeps the control on a cold page load",
  (await one.page.getByRole("button", { name: /poster/i }).count()) === 1,
);
check(
  "and the anonymous view is never flashed first",
  !/Sign in to/i.test(await one.page.locator("body").innerText()),
);

// ── A second account must not be offered the control ──────────────────────
const two = await session();
await join(two.page, "stranger@example.com");
await two.page.goto(showUrl);
await two.page.waitForTimeout(1500);
check(
  "a stranger sees the poster but no control",
  (await two.page.getByRole("button", { name: /poster/i }).count()) === 0,
);

const anon = await browser.newContext();
const anonPage = await anon.newPage();
await anonPage.goto(showUrl);
await anonPage.waitForTimeout(1500);
check(
  "a signed-out reader sees no control",
  (await anonPage.getByRole("button", { name: /poster/i }).count()) === 0,
);
check("...but can still read the listing", /Second Bill/i.test(await anonPage.locator("body").innerText()));

// ── Storage unconfigured: production's current state ──────────────────────
await fetch(`${BASE}/__control/storage`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ configured: false }),
});

await one.page.goto(showUrl);
try {
  await one.page.getByRole("button", { name: /poster/i }).waitFor({ timeout: 15000 });
} catch (e) {
  console.log("DEBUG url:", one.page.url());
  console.log("DEBUG body:", (await one.page.locator("body").innerText()).slice(0, 700));
  throw e;
}
await one.page.locator('input[type="file"]').first().setInputFiles(file("blocked.png"));
await one.page.waitForTimeout(2500);
const shown = await one.page.locator("body").innerText();
check(
  "an unconfigured bucket tells the reader so, in the server's own words",
  /temporarily unavailable/i.test(shown),
  shown.split("\n").find((l) => /unavailable|failed|error/i.test(l)) ?? "(nothing shown)",
);

await postShow(one.page, "Third Bill", true);
const afterPost = await one.page.locator("body").innerText();
check("the show still posts when the poster cannot", /It.s on the bill/i.test(afterPost));
check(
  "and the band is told the poster did not go up",
  /did not upload/i.test(afterPost),
  afterPost.split("\n").find((l) => /poster/i.test(l)) ?? "(nothing shown)",
);

await fetch(`${BASE}/__control/storage`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ configured: true }),
});

check("no page errors", one.errors.length === 0 && two.errors.length === 0, [...one.errors, ...two.errors].slice(0, 2).join(" | "));

await one.page.goto(withPosterUrl);
await one.page.waitForTimeout(1200);
await one.page.screenshot({ path: new URL("show-poster.png", import.meta.url).pathname, fullPage: false });

} catch (e) {
  crashed = e;
}
await browser.close();

if (crashed) check("harness ran to completion", false, String(crashed).split("\n")[0]);

console.log("\nPASS");
for (const p of results.pass) console.log("  ✓ " + p);
if (results.fail.length) {
  console.log("\nFAIL");
  for (const f of results.fail) console.log("  ✗ " + f);
}
console.log(`\n${results.pass.length} passed, ${results.fail.length} failed`);
process.exit(results.fail.length ? 1 : 0);
