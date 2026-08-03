/**
 * Where the API lives.
 *
 * Read from the Expo config so a build can be pointed at staging or
 * production without a code change. A native app has no "same origin" to fall
 * back to, so this must always be an absolute URL.
 */

import Constants from "expo-constants";

const configured =
  (Constants.expoConfig?.extra?.apiUrl as string | undefined) ??
  process.env.EXPO_PUBLIC_API_URL;

if (!configured) {
  throw new Error(
    "No API URL configured. Set `extra.apiUrl` in app.json or EXPO_PUBLIC_API_URL.",
  );
}

if (!/^https?:\/\//i.test(configured)) {
  throw new Error(`API URL must be absolute, got: ${configured}`);
}

// A release build must not be talking to a plaintext endpoint — tokens and
// credentials would cross the network in the clear.
if (!__DEV__ && configured.startsWith("http://")) {
  throw new Error("The production API URL must use https.");
}

export const API_BASE_URL = configured.replace(/\/$/, "");
