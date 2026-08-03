/**
 * The web app's API client.
 *
 * Same-origin by default: the SPA and the Flask API are served from one origin
 * in every deployed environment, and Vite proxies `/api` in dev. That keeps
 * the httpOnly refresh cookie first-party — a cross-site setup would have the
 * browser drop it and the session would end on every reload.
 */

import { ApiClient } from "@live-msc/shared";

function resolveBaseUrl(): string {
  const configured = (import.meta.env.VITE_API_URL ?? "").trim();
  // Only an explicit absolute URL is honoured. Anything else resolves to the
  // origin that served the page; a localhost fallback shipped to production
  // would break auth for every visitor.
  return /^https?:\/\//i.test(configured) ? configured.replace(/\/$/, "") : "";
}

export const api = new ApiClient({ baseUrl: resolveBaseUrl() });
