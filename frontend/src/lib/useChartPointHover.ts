import { useEffect, useRef, useState, type MouseEvent, type RefObject, type TouchEvent } from 'react'

export interface HoveredPoint {
  key: string
  round: number
  // Position of the point inside `wrapRef`, so the readout can sit beside it.
  left: number
  top: number
}

// Hover/tap state for a "by round" line chart with a dot per real round (Race starts, Gap by round).
// `containerRef` is the horizontally scrolling box, `wrapRef` the non-scrolling positioned box the
// readout lives in. Spread `pointHandlers(key, round)` on each dot's <g>. Hard-won details, kept here
// so every chart gets them:
// - `isScrolling` is true while the chart scrolls (200ms debounce): put `pointer-events-none` on the
//   dots then, or a wheel/trackpad scroll under a still cursor fires a real mouseenter and swaps the point.
// - Touch uses touchstart/touchend only, with a >10px threshold (a scroll-drag lifts wherever the finger
//   ends) and preventDefault on touchend to suppress the synthetic mouse events; tapping the open point closes it.
export function useChartPointHover(containerRef: RefObject<HTMLElement | null>, wrapRef: RefObject<HTMLElement | null>) {
  const [hovered, setHovered] = useState<HoveredPoint | null>(null)
  const [isScrolling, setIsScrolling] = useState(false)
  const touchStartRef = useRef<{ x: number; y: number } | null>(null)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    let t: ReturnType<typeof setTimeout>
    const onScroll = () => {
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
    const wrap = wrapRef.current?.getBoundingClientRect()
    const c = el.getBoundingClientRect()
    if (!wrap) return
    setHovered({ key, round, left: c.left - wrap.left + c.width / 2, top: c.top - wrap.top })
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
      const start = touchStartRef.current
      const t = e.changedTouches[0]
      if (start && Math.hypot(t.clientX - start.x, t.clientY - start.y) > 10) return
      if (hovered?.key === key && hovered.round === round) setHovered(null)
      else showTip(key, round, e.currentTarget)
    },
  })

  return { hovered, setHovered, isScrolling, pointHandlers }
}
