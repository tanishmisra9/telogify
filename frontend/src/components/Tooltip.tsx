import { cloneElement, useId, useRef, useState, type ReactElement } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'

// Accessible control hint: shows on hover AND keyboard focus, links to the trigger via
// aria-describedby. Paper-card styling flips with the theme. Anchored below the trigger so
// it never gets clipped by the charts' cards.
export function Tooltip({ label, children }: { label: string; children: ReactElement }) {
  const [open, setOpen] = useState(false)
  const id = useId()
  const reduce = useReducedMotion()
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)

  // Hover waits ~500ms so it doesn't flash on pass-through; focus shows immediately.
  const show = (delay: number) => {
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setOpen(true), delay)
  }
  const hide = () => {
    clearTimeout(timer.current)
    setOpen(false)
  }

  const trigger = open
    ? cloneElement(children as ReactElement<{ 'aria-describedby'?: string }>, { 'aria-describedby': id })
    : children

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => show(500)}
      onMouseLeave={hide}
      onFocus={() => show(0)}
      onBlur={hide}
    >
      {trigger}
      <AnimatePresence>
        {open && (
          <motion.span
            role="tooltip"
            id={id}
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.14 }}
            className="pointer-events-none absolute left-1/2 top-full z-50 mt-2 -translate-x-1/2 whitespace-nowrap border-[1.5px] border-ink bg-surface px-2.5 py-1.5 text-[11px] font-medium tracking-wide text-ink shadow-[3px_3px_0_var(--color-shadow)]"
          >
            {label}
          </motion.span>
        )}
      </AnimatePresence>
    </span>
  )
}
