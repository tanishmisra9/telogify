import { useEffect, useRef, useState, type MouseEvent, type RefObject, type TouchEvent } from 'react'
import type { Box } from '@/lib/placeBubble'

export interface HoveredPoint {
  key: string
  round: number
  // The dot's box in DOCUMENT coordinates (viewport rect + page scroll), so a readout rendered in a
  // portal on <body> stays put as the page scrolls.
  box: Box
}

// Hover/tap state for a "by round" line chart with a dot per real round (Race starts, Gap by round).
// `containerRef` is the horizontally scrolling box. Spread `pointHandlers(key, round)` on each dot's <g>.
// Hard-won details, kept here so every chart gets them:
// - `isScrolling` is true while the chart scrolls (200ms debounce): put `pointer-events-none` on the
//   dots then, or a wheel/trackpad scroll under a still cursor fires a real mouseenter and swaps the point.
// - Touch uses touchstart/touchend only, with a >10px threshold (a scroll-drag lifts wherever the finger
//   ends) and preventDefault on touchend to suppress the synthetic mouse events; tapping the open point closes it.
// - `isBlocked` (true during and just after a pinch-zoom) stops lifting two fingers over a dot from counting as a tap.
export function useChartPointHover(containerRef: RefObject<HTMLElement | null>, isBlocked?: () => boolean) {
  const [hovered, setHovered] = useState<HoveredPoint | null>(null)
  const [isScrolling, setIsScrolling] = useState(false)
  const touchStartRef = useRef<{ x: number; y: number } | null>(null)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    let t: ReturnType<typeof setTimeout>
    const onScroll = () => {
      // The dot moves under a readout that is anchored to where it WAS, so scrolling the chart closes it.
      setHovered(null)
      setIsScrolling(true)
      clearTimeout(t)
      t = setTimeout(() => setIsScrolling(false), 200)
    }
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      el.removeEventListener('scroll', onScroll)
      clearTimeout(t)
    }
  }, [containerRef])

  const showTip = (key: string, round: number, el: Element) => {
    const c = el.getBoundingClientRect()
    const sx = window.scrollX
    const sy = window.scrollY
    setHovered({ key, round, box: { left: c.left + sx, top: c.top + sy, right: c.right + sx, bottom: c.bottom + sy } })
  }

  const pointHandlers = (key: string, round: number) => ({
    onMouseEnter: (e: MouseEvent<Element>) => showTip(key, round, e.currentTarget),
    onMouseLeave: () => setHovered(null),
    onTouchStart: (e: TouchEvent<Element>) => {
      const t = e.touches[0]
      touchStartRef.current = { x: t.clientX, y: t.clientY }
    },
    onTouchEnd: (e: TouchEvent<Element>) => {
      e.preventDefault()
      if (isBlocked?.()) return
      const start = touchStartRef.current
      const t = e.changedTouches[0]
      if (start && Math.hypot(t.clientX - start.x, t.clientY - start.y) > 10) return
      if (hovered?.key === key && hovered.round === round) setHovered(null)
      else showTip(key, round, e.currentTarget)
    },
  })

  return { hovered, setHovered, isScrolling, pointHandlers }
}
