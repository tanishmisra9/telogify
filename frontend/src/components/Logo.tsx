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

import { smoothPath } from '@/lib/svgPath'

const WAVEFORM_WIDTH = 400
const WAVEFORM_BASELINE = 20
const NOISE_WIDTH = 320 // converges over the first 80% of the banner, then holds flat as one line
const FADE_WIDTH = 60 // the noise-to-accent color fade runs over this final stretch of NOISE_WIDTH
const SAMPLE_STEP = 4 // viewBox units between sampled points feeding smoothPath's curve fit

// One trace, not several: overlapping lines kept reading as a dense "blob" at the point they
// converged no matter how the crossing was tuned. A single line can taper but can't clump.
const WAVE_FREQ = 3.5
const WAVE_PHASE = 0.4
const WAVE_AMP = 17
const WAVE_SETTLE_X = 280 // where the trace reaches baseline and goes flat

function wavePoints(): { x: number; y: number }[] {
  const points: { x: number; y: number }[] = []
  for (let x = 0; x < WAVE_SETTLE_X; x += SAMPLE_STEP) {
    const decay = 1 - x / WAVE_SETTLE_X // linear: constant-rate shrink, no late steep pinch
    points.push({
      x,
      y: WAVEFORM_BASELINE + WAVE_AMP * decay * Math.sin(2 * Math.PI * WAVE_FREQ * (x / WAVE_SETTLE_X) + WAVE_PHASE),
    })
  }
  points.push({ x: WAVE_SETTLE_X, y: WAVEFORM_BASELINE })
  points.push({ x: WAVEFORM_WIDTH, y: WAVEFORM_BASELINE })
  return points
}

const WAVE_PATH = smoothPath(wavePoints())

// The same motif stretched into a full-bleed banner: several thin noisy traces converging into
// one clean signal line, for the footer to use as its dominant visual element instead of a
// small corner icon. preserveAspectRatio="none" lets the fixed-aspect path fill any container
// width; the wide viewBox (10:1) keeps the stretch mild so strokes don't visibly skew.
const GRADIENT_ID = 'logo-waveform-fade'

export function LogoWaveform({ className }: { className?: string }) {
  return (
    <svg
      viewBox={`0 0 ${WAVEFORM_WIDTH} 40`}
      preserveAspectRatio="none"
      fill="none"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={className}
    >
      <defs>
        {/* The noise trace fades from ink into the accent color as it nears the convergence
            point, so the join reads as a natural resolve instead of a hard color cut. */}
        <linearGradient
          id={GRADIENT_ID}
          gradientUnits="userSpaceOnUse"
          x1={NOISE_WIDTH - FADE_WIDTH}
          y1="0"
          x2={NOISE_WIDTH}
          y2="0"
        >
          <stop offset="0" stopColor="currentColor" />
          <stop offset="1" stopColor="var(--color-accent)" />
        </linearGradient>
      </defs>
      {/* One continuous path, not two joined at a seam — a second path starting exactly where
          this one ends produced a visible knot where their round linecaps overlapped. The
          gradient already fades to solid accent color by NOISE_WIDTH and holds (pad) past it. */}
      <path d={WAVE_PATH} stroke={`url(#${GRADIENT_ID})`} strokeWidth={1.5} />
    </svg>
  )
}
