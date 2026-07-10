// The mark: a telemetry trace that starts as noise and resolves into a clean signal line,
// the accent picking out the resolved half. One glyph for the whole mission ("cut the
// noise"): deterministic insight out of noisy data. Ink follows currentColor so the mark
// flips with the theme like every other ink element.
export function LogoMark({ size = 22 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      strokeWidth={3}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M2 16 L6 7 L10 25 L13 11 L16 20 L18 16" stroke="currentColor" />
      <path d="M18 16 L30 16" stroke="var(--color-accent)" />
    </svg>
  )
}
