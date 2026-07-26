import { AnimatePresence, m, useReducedMotion } from 'framer-motion'
import type { ReactNode } from 'react'
import { blurFadeIn, blurFadeOut, spring } from '@/lib/motion'

// Placeholder and content occupy the same grid cell (both col-start-1 row-start-1) so the swap is
// a crossfade, not an unmount-then-mount: the skeleton blur-fades out as the real content blur-fades
// in, instead of vanishing and leaving a blank gap until the content's own reveal begins. Default
// (sync) AnimatePresence mode keeps both mounted while the exiting one animates out, which is what
// makes the overlap possible.
//
// The placeholder gets the *same* blur-fade entrance as content (via `delay`, matched to the
// adjacent SectionTitle's own delay at each call site) rather than popping in instantly -- without
// this, the loader appeared crisp and fully-formed the moment the page mounted, while its own
// heading was still mid blur-fade above it: a jarring mismatch between "everything reveals softly"
// and "except this one hard-edged box". `initial={false}` is deliberately NOT set on
// AnimatePresence: that prop only affects whichever child is present on this component's very
// first render, and here that's exactly the child (the placeholder) that needs its entrance to
// play, not be suppressed.
//
// `min-w-0` on the grid children is load-bearing, not decorative: a CSS grid item's default
// `min-width` is `auto`, which resolves to its content's min-content size rather than 0 -- so
// wide content placed inside this wrapper (e.g. Ranking's table, `min-w-[480px]`) was forcing
// the grid track, and with it the whole page, to grow wide enough to fit it instead of staying
// within the viewport and scrolling internally via its own `overflow-x-auto`. That surfaced as
// the entire page scrolling horizontally when a user tried to scroll just the table.
export function LoadingSwap({
  loading,
  placeholder,
  children,
  delay = 0,
}: {
  loading: boolean
  placeholder: ReactNode
  children: ReactNode
  // Applied only to the placeholder's entrance (its mount coincides with the section's heading,
  // so it should reveal in lockstep with it) -- never to content's entrance, which should start
  // the instant its data is ready rather than wait out a delay meant for the page-load moment.
  delay?: number
}) {
  const reduce = useReducedMotion()
  return (
    <div className="grid [&>*]:col-start-1 [&>*]:row-start-1 [&>*]:min-w-0">
      <AnimatePresence>
        {loading ? (
          <m.div
            key="placeholder"
            initial={reduce ? false : blurFadeIn.initial}
            animate={blurFadeIn.animate}
            exit={reduce ? undefined : blurFadeOut}
            transition={{ ...spring, delay: reduce ? 0 : delay }}
          >
            {placeholder}
          </m.div>
        ) : (
          <m.div
            key="content"
            initial={reduce ? false : blurFadeIn.initial}
            animate={blurFadeIn.animate}
            transition={spring}
          >
            {children}
          </m.div>
        )}
      </AnimatePresence>
    </div>
  )
}
