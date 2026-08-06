/**
 * End-to-end check of the rebuilt Plan map against the real production bundle.
 *
 * The sandbox cannot reach the tile CDN, so tile requests are intercepted and
 * answered with a generated PNG. That still exercises the whole path: Leaflet
 * computes the tile URLs, requests them, lays them out, and positions the pins
 * against them. What it cannot prove is that CARTO serves that URL — checked
 * separately against the live host.
 */
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

const DIST = new URL("../dist/", import.meta.url).pathname;
const PORT = 4173;

// Three rooms in Providence, a few blocks apart.
const VENUES = [
  { name: "The Met", lat: 41.8206, lon: -71.4085, hood: "Downtown" },
  { name: "Askew", lat: 41.8258, lon: -71.4155, hood: "West End" },
  { name: "Fete Music Hall", lat: 41.8155, lon: -71.4302, hood: "Olneyville" },
];

const apiCalls = [];

function nearby(url) {
  const q = new URL(url, "http://x").searchParams;
  apiCalls.push({
    latitude: Number(q.get("latitude")),
    longitude: Number(q.get("longitude")),
    radius_miles: Number(q.get("radius_miles")),
  });
  const events = VENUES.map((v, i) => ({
    id: `evt-${i}`,
    headline: `Band ${i + 1}`,
    support_line: null,
    genre: "rock",
    genre_label: "Rock",
    status: "published",
    starts_at: "2026-08-06T01:00:00+00:00",
    doors_at: null,
    time_label: "9:00 PM",
    doors_label: null,
    day_bucket: "tomorrow",
    day_label: "Tomorrow",
    date_long: "Thursday 6 August",
    price_cents: 1200,
    price_label: "$12",
    age_restriction: "all_ages",
    age_label: "All ages",
    short_line: null,
    poster_url: null,
    venue: {
      id: `ven-${i}`,
      name: v.name,
      slug: `v${i}`,
      address: null,
      neighborhood: v.hood,
      city: "Providence",
      latitude: v.lat,
      longitude: v.lon,
      timezone: "America/New_York",
    },
    artist: null,
    saved: false,
    going: false,
    already_started: false,
    distance_miles: 0.4 + i * 0.3,
    distance_label: `${(0.4 + i * 0.3).toFixed(1)} mi`,
    pin_number: i + 1,
  }));
  return { data: { events, count: events.length, radius_miles: 5 }, error: null };
}

const MIME = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".map": "application/json",
  ".png": "image/png",
  ".svg": "image/svg+xml",
};

const server = http.createServer((req, res) => {
  if (req.url.startsWith("/api/v1/events/nearby")) {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify(nearby(req.url)));
    return;
  }
  if (req.url.startsWith("/api/")) {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ data: null, error: null }));
    return;
  }
  const clean = req.url.split("?")[0];
  let file = path.join(DIST, clean);
  if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) file = path.join(DIST, "index.html");
  res.writeHead(200, { "content-type": MIME[path.extname(file)] ?? "text/plain" });
  res.end(fs.readFileSync(file));
});

// A 1x1 grey PNG, stretched by Leaflet to fill each tile slot.
const FAKE_TILE = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "base64",
);

const results = { pass: [], fail: [] };
const check = (name, ok, detail = "") =>
  (ok ? results.pass : results.fail).push(`${name}${detail ? ` — ${detail}` : ""}`);

await new Promise((r) => server.listen(PORT, r));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1100, height: 900 } });

const tileUrls = [];
await page.route("**://basemaps.cartocdn.com/**", (route) => {
  tileUrls.push(route.request().url());
  route.fulfill({ status: 200, contentType: "image/png", body: FAKE_TILE });
});

const consoleErrors = [];
const blockedRequests = [];
page.on("requestfailed", (r) => blockedRequests.push(`${r.url()} ${r.failure()?.errorText}`));
page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
page.on("pageerror", (e) => consoleErrors.push(String(e)));

await page.goto(`http://localhost:${PORT}/plan`, { waitUntil: "networkidle" });
await page.waitForTimeout(1200);

// ── The map exists and is a real Leaflet map ─────────────────────────────
check("leaflet initialised the frame", (await page.locator(".mapframe.leaflet-container").count()) === 1);
check("tiles requested from the configured host", tileUrls.length > 0, `${tileUrls.length} tiles`);
check(
  "tile URL is the CARTO Positron path",
  tileUrls.some((u) => /basemaps\.cartocdn\.com\/light_all\/\d+\/\d+\/\d+(@2x)?\.png/.test(u)),
  tileUrls[0] ?? "none",
);
check("tiles actually laid into the pane", (await page.locator(".leaflet-tile-loaded").count()) > 0);

// ── Pins ─────────────────────────────────────────────────────────────────
const pins = page.locator(".mapframe .mappin");
check("one pin per located show", (await pins.count()) === 3, `${await pins.count()} pins`);
check("pins are numbered", (await pins.nth(0).innerText()).trim() === "1");

// Pins must sit at distinct positions — the old projection collapsed them when
// a span was zero, and a stack of three discs looks identical to one.
const boxes = [];
for (let i = 0; i < 3; i++) boxes.push(await pins.nth(i).boundingBox());
const distinct = new Set(boxes.map((b) => `${Math.round(b.x)},${Math.round(b.y)}`));
check("pins are at distinct screen positions", distinct.size === 3, [...distinct].join(" "));

// Geography must be right: Fete (west, south) should be left of and below The Met.
const met = boxes[0];
const fete = boxes[2];
check("westernmost venue draws to the left", fete.x < met.x, `fete ${Math.round(fete.x)} < met ${Math.round(met.x)}`);
check("southernmost venue draws lower", fete.y > met.y, `fete ${Math.round(fete.y)} > met ${Math.round(met.y)}`);

// ── Hover sync between the listing and the pin ───────────────────────────
await page.locator(".listing").nth(1).hover();
await page.waitForTimeout(200);
check(
  "hovering a listing lights its pin",
  (await page.locator('.mapframe .mappin[data-active="true"]').count()) === 1,
);

// ── Attribution + scale (licence conditions, and legibility) ─────────────
const attribution = await page.locator(".leaflet-control-attribution").innerText();
check("OpenStreetMap credited", /OpenStreetMap/i.test(attribution), attribution.slice(0, 60));
check("CARTO credited", /CARTO/i.test(attribution));
check("scale bar present", (await page.locator(".leaflet-control-scale-line").count()) > 0);

// The two bottom controls must not sit on top of each other.
const scaleBox = await page.locator(".leaflet-control-scale-line").boundingBox();
const attrBox = await page.locator(".leaflet-control-attribution").boundingBox();
const overlaps =
  scaleBox.x < attrBox.x + attrBox.width &&
  scaleBox.x + scaleBox.width > attrBox.x &&
  scaleBox.y < attrBox.y + attrBox.height &&
  scaleBox.y + scaleBox.height > attrBox.y;
check("scale bar does not overlap the attribution", !overlaps);

// The Classical grade must actually be reaching the tiles.
const tileFilter = await page.evaluate(
  () => getComputedStyle(document.querySelector(".mapframe .leaflet-tile-pane")).filter,
);
check("tile pane carries the warm grade", /sepia/.test(tileFilter), tileFilter);

// The frame must clip Leaflet's panes, or tiles bleed past the rounded border.
const clipped = await page.evaluate(
  () => getComputedStyle(document.querySelector(".mapframe")).overflow,
);
check("map frame clips its tiles", clipped === "hidden", clipped);
check("zoom controls present", (await page.locator(".leaflet-control-zoom a").count()) === 2);

// ── Keyboard reachability ────────────────────────────────────────────────
check(
  "pins are tab-reachable",
  (await page.locator(".mapframe .leaflet-marker-icon[tabindex]").count()) === 3,
);

// ── Panning re-queries the API for the new frame ─────────────────────────
const firstLoadCalls = apiCalls.length;
const before = apiCalls.length;
const frame = await page.locator(".mapframe").boundingBox();
await page.mouse.move(frame.x + frame.width / 2, frame.y + frame.height / 2);
await page.mouse.down();
await page.mouse.move(frame.x + frame.width / 2 - 260, frame.y + frame.height / 2 - 160, { steps: 12 });
await page.mouse.up();
await page.waitForTimeout(1400);

check("panning issues a new query", apiCalls.length > before, `${before} → ${apiCalls.length}`);
check("first load queries exactly once", firstLoadCalls === 1, `${firstLoadCalls} calls`);
if (apiCalls.length > before) {
  const first = apiCalls[0];
  const latest = apiCalls[apiCalls.length - 1];
  check(
    "the new query is centred on the new frame",
    Math.abs(first.latitude - latest.latitude) > 1e-4 || Math.abs(first.longitude - latest.longitude) > 1e-4,
    `${first.latitude.toFixed(4)},${first.longitude.toFixed(4)} → ${latest.latitude.toFixed(4)},${latest.longitude.toFixed(4)}`,
  );
  check(
    "radius stays inside the API's 0 < r <= 50 range",
    apiCalls.every((c) => c.radius_miles > 0 && c.radius_miles <= 50),
    apiCalls.map((c) => c.radius_miles).join(", "),
  );
}

// The pan must not have blanked the map while the new response was in flight.
check("listings survive a pan", (await page.locator(".listing").count()) === 3);

// ── Zooming out far must not ask for an illegal radius ───────────────────
await page.evaluate(() => window.scrollTo(0, 0));
for (let i = 0; i < 9; i++) {
  await page.locator(".leaflet-control-zoom-out").click();
  await page.waitForTimeout(90);
}
await page.waitForTimeout(1200);
check(
  "world-scale zoom still asks for a legal radius",
  apiCalls.every((c) => c.radius_miles > 0 && c.radius_miles <= 50),
  `max ${Math.max(...apiCalls.map((c) => c.radius_miles))}`,
);

// The sandbox blocks every non-allowlisted host, so a failed request here is
// only meaningful if it is one of ours. Google Fonts is expected to fail.
// Google Fonts is unreachable from the sandbox. Tile requests Leaflet cancels
// mid-pan surface as ERR_ABORTED and are normal map behaviour, not failures.
const ourFailures = blockedRequests.filter(
  (u) => !/fonts\.(googleapis|gstatic)\.com/.test(u) && !/cartocdn\.com.*ERR_ABORTED/.test(u),
);
check("no blocked requests of our own", ourFailures.length === 0, ourFailures.slice(0, 3).join(" | "));
const realErrors = consoleErrors.filter((e) => !/ERR_TUNNEL_CONNECTION_FAILED|fonts\.(googleapis|gstatic)/.test(e));
check("no page errors", realErrors.length === 0, realErrors.slice(0, 3).join(" | "));
console.log("\nblocked by the sandbox (expected):", [...new Set(blockedRequests.map((u) => new URL(u.split(" ")[0]).host))].join(", ") || "none");

await page.goto(`http://localhost:${PORT}/plan`, { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
await page.screenshot({ path: new URL("plan-map.png", import.meta.url).pathname });

await browser.close();
server.close();

console.log("\nPASS");
for (const p of results.pass) console.log("  ✓ " + p);
if (results.fail.length) {
  console.log("\nFAIL");
  for (const f of results.fail) console.log("  ✗ " + f);
}
console.log(`\n${results.pass.length} passed, ${results.fail.length} failed`);
process.exit(results.fail.length ? 1 : 0);
