/**
 * Adds the dark and tinted iOS app-icon appearances to the asset catalog.
 *
 * SDK 51's prebuild only understands a single `icon` path — the
 * `ios.icon.{light,dark,tinted}` object arrived in SDK 52 — so the base icon
 * plugin writes an AppIcon.appiconset holding just the light image. This runs
 * in the `finalized` phase, which the mod compiler always orders after the
 * base (dangerous) mods, and appends the two appearance entries the same way
 * SDK 52 would. Delete it on upgrade to SDK 52+ and move the variants into
 * `ios.icon` in app.json instead.
 */
const { withFinalizedMod, IOSConfig } = require("@expo/config-plugins");
const fs = require("fs");
const path = require("path");

const APPEARANCES = [
  { source: "icon-dark-1024.png", value: "dark" },
  { source: "icon-tinted-1024.png", value: "tinted" },
];

module.exports = function withIosIconAppearances(config) {
  return withFinalizedMod(config, [
    "ios",
    async (config) => {
      const { projectRoot, platformProjectRoot } = config.modRequest;
      const projectName = IOSConfig.XcodeUtils.getProjectName(projectRoot);
      const iconsetDir = path.join(
        platformProjectRoot,
        projectName,
        "Images.xcassets",
        "AppIcon.appiconset",
      );
      const contentsPath = path.join(iconsetDir, "Contents.json");
      if (!fs.existsSync(contentsPath)) {
        throw new Error(
          `withIosIconAppearances: ${contentsPath} not found — expected the base icon plugin to have written it first.`,
        );
      }

      const contents = JSON.parse(fs.readFileSync(contentsPath, "utf8"));
      contents.images = contents.images.filter((image) => !image.appearances);

      for (const { source, value } of APPEARANCES) {
        const sourcePath = path.join(projectRoot, "assets", "icons", source);
        if (!fs.existsSync(sourcePath)) {
          throw new Error(`withIosIconAppearances: missing ${sourcePath}`);
        }
        const filename = `App-Icon-1024x1024@1x-${value}.png`;
        fs.copyFileSync(sourcePath, path.join(iconsetDir, filename));
        contents.images.push({
          appearances: [{ appearance: "luminosity", value }],
          filename,
          idiom: "universal",
          platform: "ios",
          size: "1024x1024",
        });
      }

      fs.writeFileSync(contentsPath, JSON.stringify(contents, null, 2));
      return config;
    },
  ]);
};
