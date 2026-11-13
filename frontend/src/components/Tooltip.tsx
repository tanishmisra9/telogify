import { cloneElement, useEffect, useId, useLayoutEffect, useRef, useState, type ReactElement } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, m, useReducedMotion } from 'framer-motion'
import { placeBubble } from '@/lib/placeBubble'

// Accessible control hint: shows on hover AND keyboard focus, links to the trigger via
// aria-describedby. Paper-card styling flips with the theme. The bubble is rendered in a portal on
// <body>, positioned in document coordinates, so it sits on the page surface: it can overlap
// neighbouring content, is never clipped by a chart card, and is kept inside the viewport (flipping
// above when there is no room below). `align` is the preferred anchor: centered on the trigger, or its
// left (`start`) / right (`end`) edge, before the viewport clamp. `wrap` caps a long label at 18rem; any
// label is also capped to the viewport width so it breaks rather than overflowing a phone.
// It closes on scroll or resize: the portal is anchored to document coordinates, so a trigger in a
// sticky element (the Nav) would otherwise leave it behind.
export function Tooltip({
  label,
  children,
  align = 'center',
  wrap = false,
  className = 'relative inline-flex',
}: {
  label: string
  children: ReactElement
  align?: 'center' | 'start' | 'end'
  // Cap a long label at 18rem (for hints longer than a short phrase) instead of one line up to the viewport width.
  wrap?: boolean
  // The wrapper's own classes (must keep `relative`): lets a caller make it fill a positioned
  // parent, e.g. a bar segment, instead of shrink-wrapping its child.
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null)
  const id = useId()
  const reduce = useReducedMotion()
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const autoHideTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const wrapperRef = useRef<HTMLSpanElement>(null)
  const bubbleRef = useRef<HTMLSpanElement>(null)

  // Hover waits ~500ms so it doesn't flash on pass-through; focus shows immediately.
  const show = (delay: number) => {
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setOpen(true), delay)
  }
  const hide = () => {
    clearTimeout(timer.current)
    clearTimeout(autoHideTimer.current)
    setOpen(false)
  }
  // Touch has no hover/blur to dismiss on, so a tap opens the tooltip immediately and it closes
  // itself after a beat instead of sticking open until the next unrelated tap.
  const tap = () => {
    clearTimeout(timer.current)
    setOpen(true)
    clearTimeout(autoHideTimer.current)
    autoHideTimer.current = setTimeout(() => setOpen(false), 1500)
  }

  // Measure the bubble and the trigger before paint, so it never flashes in the wrong place.
  useLayoutEffect(() => {
    // On close the last position is kept, so the exit fade plays where the bubble was.
    if (!open) return
    const wrapper = wrapperRef.current
    const bubble = bubbleRef.current
    if (!wrapper || !bubble) return
    const a = wrapper.getBoundingClientRect()
    const b = bubble.getBoundingClientRect()
    const sx = window.scrollX
    const sy = window.scrollY
    const anchor = { left: a.left + sx, top: a.top + sy, right: a.right + sx, bottom: a.bottom + sy }
    const view = { w: document.documentElement.clientWidth, h: window.innerHeight, scrollX: sx, scrollY: sy }
    setPos(placeBubble(anchor, { w: b.width, h: b.height }, view, align))
  }, [open, label, align])

  useEffect(() => {
    if (!open) return
    const sx = window.scrollX
    const sy = window.scrollY
    // Page scrolls of a couple of px don't count: ThemeToggle nudges the page by 1px on every theme
    // change (a Safari toolbar workaround), which must not dismiss its own "Switch to ... mode" bubble.
    const onScroll = (e: Event) => {
      if (e.target === document && Math.abs(window.scrollX - sx) <= 2 && Math.abs(window.scrollY - sy) <= 2) return
      hide()
    }
    window.addEventListener('scroll', onScroll, { capture: true, passive: true })
    window.addEventListener('resize', hide)
    return () => {
      window.removeEventListener('scroll', onScroll, { capture: true })
      window.removeEventListener('resize', hide)
    }
  }, [open])

  const trigger = open
    ? cloneElement(children as ReactElement<{ 'aria-describedby'?: string }>, { 'aria-describedby': id })
    : children

  return (
    <span
      ref={wrapperRef}
      className={className}
      onMouseEnter={() => show(500)}
      onMouseLeave={hide}
      onFocusCapture={() => show(0)}
      onBlurCapture={hide}
      onClick={tap}
    >
      {trigger}
      {createPortal(
        <AnimatePresence>
          {open && (
            <m.span
              ref={bubbleRef}
              role="tooltip"
              id={id}
              initial={reduce ? { opacity: 0 } : { opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.14 }}
              style={{ left: pos?.left ?? 0, top: pos?.top ?? 0, visibility: pos ? 'visible' : 'hidden' }}
              className={`pointer-events-none absolute z-50 w-max ${wrap ? 'max-w-[min(18rem,calc(100vw-1rem))]' : 'max-w-[calc(100vw-1rem)]'} border-[1.5px] border-ink bg-surface px-2.5 py-1.5 text-[11px] font-medium tracking-wide text-ink shadow-[3px_3px_0_var(--color-shadow)]`}
            >
              {label}
            </m.span>
          )}
        </AnimatePresence>,
        document.body,
      )}
    </span>
  )
}
