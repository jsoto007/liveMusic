/**
 * Dynamic wrapper over app.json.
 *
 * One job: let a dev session point the app at a local API without editing
 * the checked-in production URL. `EXPO_PUBLIC_API_URL` is read by the CLI
 * process at bundle/manifest time; release builds built without the variable
 * keep the app.json value exactly as before.
 */

module.exports = ({ config }) => ({
  ...config,
  extra: {
    ...config.extra,
    apiUrl: process.env.EXPO_PUBLIC_API_URL ?? config.extra?.apiUrl,
  },
});
