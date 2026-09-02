/**
 * Removes purpose strings for capabilities this app does not use.
 *
 * Expo's prebuild template ships an `Info.plist` carrying a default set of
 * `NS*UsageDescription` keys, each with a boilerplate
 * "Allow $(PRODUCT_NAME) to access your …" string. Four of them describe
 * things Live Msc never does:
 *
 *   NSCameraUsageDescription      — only the library picker is ever opened
 *   NSMicrophoneUsageDescription  — expo-av is used for playback, never to record
 *   NSFaceIDUsageDescription      — expo-secure-store, with no biometric gate
 *   NSLocationAlways*             — location is read once, in the foreground
 *
 * Shipping them is a Guideline 5.1.1 problem on its own (a purpose string has
 * to describe a real purpose), and the background-location pair invites a
 * review question the app cannot answer because it never asks for background
 * location. The microphone one was worse still: it read, in full, "Not used."
 *
 * This cannot be fixed by editing `ios/Info.plist` — `ios/` is prebuild
 * output and is gitignored, so the defaults come back on every EAS build.
 * Setting the keys to `false` in `app.json` does not work either: that writes
 * a literal `<false/>` where iOS expects a string. Deleting them in a mod is
 * the only thing that actually removes them, which is what this does.
 *
 * Registered FIRST in the plugins array, which is what makes it run LAST.
 * Expo composes `withInfoPlist` mods by wrapping, so the earliest-registered
 * action is the outermost and therefore the last to execute. Registering this
 * at the end instead left `NSFaceIDUsageDescription` in the output, because
 * expo-secure-store's own mod ran afterwards and put it back. Verified by
 * running `expo prebuild` and reading the generated plist — do the same if
 * you move it.
 */
const { withInfoPlist } = require("@expo/config-plugins");

const UNUSED_KEYS = [
  "NSCameraUsageDescription",
  "NSMicrophoneUsageDescription",
  "NSFaceIDUsageDescription",
  "NSLocationAlwaysUsageDescription",
  "NSLocationAlwaysAndWhenInUseUsageDescription",
];

module.exports = function withTrimmedInfoPlist(config) {
  return withInfoPlist(config, (config) => {
    for (const key of UNUSED_KEYS) {
      delete config.modResults[key];
    }
    return config;
  });
};
