import type { Transition } from 'framer-motion'

// Spring physics, ease-out feel, no bounce.
export const spring: Transition = { type: 'spring', stiffness: 120, damping: 20 }

// Quicker settle than `spring`: for disclosure/collapse toggles, which should feel snappy
// rather than like a section-level reveal.
export const expandTransition: Transition = { type: 'spring', stiffness: 380, damping: 32 }

// Ease-out-quint: a clean "drawing" feel for an SVG line/path reveal, no bounce. Shared by every
// chart with a click-to-isolate legend (Tyre degradation, Gap by round) so newly-revealed lines
// draw in consistently.
export const drawTransition: Transition = {
  pathLength: { duration: 0.5, ease: [0.16, 1, 0.3, 1] },
  opacity: { duration: 0.2 },
}

// Ease-in-out tween for morphing an SVG path's `d` between two point sets with the same command
// structure — a shape-to-shape transform, not a reveal, so it gets the standard ease-in-out
// curve rather than drawTransition's ease-out-quint (which is for draw-in reveals specifically).
export const morphTransition: Transition = { duration: 0.6, ease: [0.65, 0, 0.35, 1] }

export const blurFadeIn = {
  initial: { opacity: 0, filter: 'blur(10px)', y: 10 },
  animate: { opacity: 1, filter: 'blur(0px)', y: 0 },
}
