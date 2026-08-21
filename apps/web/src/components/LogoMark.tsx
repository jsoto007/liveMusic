/**
 * The Live Msc mark — a hairline circle around the "M" pulse, drawn as
 * strokes in the accent, never filled. Geometry is traced from the icon
 * export (design/logo), so this stays in register with the app icon and
 * favicon; the mobile LogoMark carries the same numbers.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="-3 -3 453 453"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      <g
        fill="none"
        stroke="var(--color-accent)"
        strokeWidth={20}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <circle cx="223.5" cy="223.5" r="213.5" />
        <polyline points="138,223.5 181,181.5 223.5,245 266,138 309,223.5" />
      </g>
    </svg>
  );
}
