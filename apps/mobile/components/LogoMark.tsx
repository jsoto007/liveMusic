/**
 * The Live Msc mark — a hairline circle around the "M" pulse, drawn as
 * strokes in the accent, never filled. Same traced geometry as the web
 * LogoMark, the favicon and the app icon, so the mark stays in register
 * everywhere it appears.
 */
import Svg, { Circle, Polyline } from "react-native-svg";

import { colors } from "../lib/theme";

export function LogoMark({ size = 22 }: { size?: number }) {
  return (
    <Svg
      viewBox="-3 -3 453 453"
      width={size}
      height={size}
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
    >
      <Circle
        cx={223.5}
        cy={223.5}
        r={213.5}
        fill="none"
        stroke={colors.accent}
        strokeWidth={20}
      />
      <Polyline
        points="138,223.5 181,181.5 223.5,245 266,138 309,223.5"
        fill="none"
        stroke={colors.accent}
        strokeWidth={20}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}
