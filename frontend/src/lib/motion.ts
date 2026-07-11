import type { Transition } from 'framer-motion'

// Spring physics, ease-out feel, no bounce.
export const spring: Transition = { type: 'spring', stiffness: 120, damping: 20 }

// Ease-out-quint: a clean "drawing" feel for an SVG line/path reveal, no bounce. Shared by every
// chart with a click-to-isolate legend (Tyre degradation, Gap by round) so newly-revealed lines
// draw in consistently.
export const drawTransition: Transition = {
  pathLength: { duration: 0.5, ease: [0.16, 1, 0.3, 1] },
  opacity: { duration: 0.2 },
}

export const blurFadeIn = {
  initial: { opacity: 0, filter: 'blur(10px)', y: 10 },
  animate: { opacity: 1, filter: 'blur(0px)', y: 0 },
}
