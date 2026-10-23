/**
 * Where the policy documents live.
 *
 * The App Store listing needs a reachable privacy policy, and Guideline 1.2
 * expects a user-generated-content app to put terms in front of people before
 * they post. Both documents are served by the web app, so there is one copy to
 * keep current rather than one per platform; these are the links into it.
 *
 * Derived from the API URL by default so a staging build points at staging
 * without a second setting, and overridable in `app.json` for the day the
 * marketing site and the API stop sharing a host.
 */

import Constants from "expo-constants";

import { API_BASE_URL } from "./config";

const configured = Constants.expoConfig?.extra?.webUrl as string | undefined;

/** The reader-facing web app — the same paper, in a browser. */
export const WEB_BASE_URL = (configured ?? API_BASE_URL).replace(/\/$/, "");

export const TERMS_URL = `${WEB_BASE_URL}/terms`;
export const PRIVACY_URL = `${WEB_BASE_URL}/privacy`;
