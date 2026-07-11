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

// The same motif stretched into a full-bleed banner: noise decaying into a long clean signal
// line, for the footer to use as its dominant visual element instead of a small corner icon.
// preserveAspectRatio="none" lets the fixed-aspect path fill any container width; the wide
// viewBox (10:1) keeps the stretch mild so the diagonal noise strokes don't visibly skew.
export function LogoWaveform({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 400 40"
      preserveAspectRatio="none"
      fill="none"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={className}
    >
      <path
        d="M0 20 L14 5 L28 33 L42 9 L56 29 L70 12 L84 27 L98 14 L112 25 L126 15 L140 24
           L154 16 L168 23 L182 17 L196 22 L210 18 L224 21 L238 19 L252 20.5 L266 20"
        stroke="currentColor"
      />
      <path d="M266 20 L400 20" stroke="var(--color-accent)" />
    </svg>
  )
}
