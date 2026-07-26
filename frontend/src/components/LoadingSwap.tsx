import { AnimatePresence, m, useReducedMotion } from 'framer-motion'
import type { ReactNode } from 'react'
import { blurFadeIn, blurFadeOut, spring } from '@/lib/motion'

// Placeholder and content occupy the same grid cell (both col-start-1 row-start-1) so the swap is
// a crossfade, not an unmount-then-mount: the skeleton blur-fades out as the real content blur-fades
// in, instead of vanishing and leaving a blank gap until the content's own reveal begins. Default
// (sync) AnimatePresence mode keeps both mounted while the exiting one animates out, which is what
// makes the overlap possible; `initial={false}` only suppresses the very first mount's entrance
// (the placeholder), not the content's entrance once it replaces it.
export function LoadingSwap({
  loading,
  placeholder,
  children,
}: {
  loading: boolean
  placeholder: ReactNode
  children: ReactNode
}) {
  const reduce = useReducedMotion()
  return (
    <div className="grid [&>*]:col-start-1 [&>*]:row-start-1">
      <AnimatePresence initial={false}>
        {loading ? (
          <m.div key="placeholder" exit={reduce ? undefined : blurFadeOut} transition={spring}>
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
