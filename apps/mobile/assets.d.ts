/**
 * Static image assets. Metro resolves an image import to an opaque asset id
 * (a number) that `<Image source>` accepts — `ImageRequireSource` is exactly
 * that alias in react-native's own types.
 */
declare module "*.jpg" {
  import type { ImageRequireSource } from "react-native";

  const asset: ImageRequireSource;
  export default asset;
}
