import { m, useReducedMotion } from 'framer-motion'
import type { ReactNode } from 'react'
import { blurFadeIn, spring } from '@/lib/motion'

// Same blur-fade recipe as BlurFade, but triggered when the section scrolls into view instead
// of on mount, for content further down the page than the initial fold.
export function ScrollReveal({
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
      whileInView={blurFadeIn.animate}
      viewport={{ once: true, margin: '-80px' }}
      transition={{ ...spring, delay: reduce ? 0 : delay }}
    >
      {children}
    </m.div>
  )
}
