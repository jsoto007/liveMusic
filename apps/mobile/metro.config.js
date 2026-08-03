// Metro must be told about the monorepo: the app imports @live-msc/shared from
// outside its own directory, and pnpm's store lives at the workspace root.
const path = require("node:path");

const { getDefaultConfig } = require("expo/metro-config");

const projectRoot = __dirname;
const workspaceRoot = path.resolve(projectRoot, "../..");

const config = getDefaultConfig(projectRoot);

config.watchFolders = [workspaceRoot];
config.resolver.nodeModulesPaths = [
  path.resolve(projectRoot, "node_modules"),
  path.resolve(workspaceRoot, "node_modules"),
];
// pnpm symlinks aggressively; without this Metro resolves a package to two
// different copies and React ends up loaded twice.
config.resolver.disableHierarchicalLookup = true;

module.exports = config;
