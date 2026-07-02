import { m, useReducedMotion } from 'framer-motion'
import type { ReactNode } from 'react'
import { blurFadeIn, spring } from '@/lib/motion'

// Reveal that enhances an already-visible default: it animates on mount (not gated on
// scroll/visibility), and collapses to no movement under prefers-reduced-motion.
export function BlurFade({
  children,
  delay = 0,
  className,
}: {
  children: ReactNode
  delay?: number
  className?: string
}) {
  const reduce = useReducedMotion()
  return (
    <m.div
      className={className}
      initial={reduce ? false : blurFadeIn.initial}
      animate={blurFadeIn.animate}
      transition={{ ...spring, delay: reduce ? 0 : delay }}
    >
      {children}
    </m.div>
  )
}
