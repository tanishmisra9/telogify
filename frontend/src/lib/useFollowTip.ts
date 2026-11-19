import { useEffect, useRef, useState, type MouseEvent, type RefObject, type TouchEvent } from 'react'

export interface FollowTipAt {
  key: string
  // The pointer in DOCUMENT coordinates (client position + page scroll) when the key was selected; `pointer` keeps tracking.
  x: number
  y: number
}

// How long a mouseleave waits before closing the tip. Moving from one row to the next fires leave then enter back to back; an
// immediate close would unmount the tip and it could never glide between rows. The next enter cancels the close.
const LEAVE_GRACE_MS = 60

// Hover/tap state for a readout that FOLLOWS the pointer (the weekend charts' tooltips). Spread `handlers(key)` on whatever
// is hoverable. `at` changes only when the hovered key does; the pointer itself lives in a ref (`pointer`), because a React
// render per mousemove would be wasted work: `FollowTip` reads the ref in its own animation frame loop.
// - Mouse: enter selects, move updates the ref (and reopens a tip that a scroll closed), leave closes after the grace period.
// - Touch: touchstart/touchend only, with a >10px threshold (a scroll-drag lifts wherever the finger ends) and preventDefault on
//   touchend to suppress the synthetic mouse events; tapping the open key closes it.
// - A real page scroll closes it (the pointer position is stale); a <=2px scroll is ignored because ThemeToggle nudges the page
//   1px on every theme change. `containerRef` (a horizontally scrolling chart) also closes it and raises `isScrolling` for
//   200ms: put `pointer-events-none` on the hoverables then, or a wheel scroll under a still cursor fires a real mouseenter.
export function useFollowTip(containerRef?: RefObject<HTMLElement | null>) {
  const [at, setAt] = useState<FollowTipAt | null>(null)
  const [isScrolling, setIsScrolling] = useState(false)
  const pointer = useRef({ x: 0, y: 0 })
  const touchStart = useRef<{ x: number; y: number } | null>(null)
  const leaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastY = useRef(0)

  useEffect(() => {
    lastY.current = window.scrollY
    let t: ReturnType<typeof setTimeout>
    const onWindowScroll = () => {
      if (Math.abs(window.scrollY - lastY.current) > 2) setAt(null)
      lastY.current = window.scrollY
    }
    // The chart's own scroll box: a capture listener on the document (element scroll events do not bubble), matched against
    // the container AT EVENT TIME, so a container that mounts after this effect ran (data arrives, a tab swaps the list) still
    // gets its guard.
    const onAnyScroll = (e: Event) => {
      if (!containerRef?.current || e.target !== containerRef.current) return
      setAt(null)
      setIsScrolling(true)
      clearTimeout(t)
      t = setTimeout(() => setIsScrolling(false), 200)
    }
    const onResize = () => setAt(null)
    // Touch has no mouseleave: a tap anywhere that is not a hoverable (they carry data-follow) dismisses the tip.
    const onTouchOutside = (e: Event) => {
      if (!(e.target instanceof Element) || !e.target.closest('[data-follow]')) setAt(null)
    }
    document.addEventListener('touchstart', onTouchOutside, { capture: true, passive: true })
    window.addEventListener('scroll', onWindowScroll, { passive: true })
    window.addEventListener('resize', onResize)
    document.addEventListener('scroll', onAnyScroll, { capture: true, passive: true })
    return () => {
      window.removeEventListener('scroll', onWindowScroll)
      window.removeEventListener('resize', onResize)
      document.removeEventListener('scroll', onAnyScroll, { capture: true })
      document.removeEventListener('touchstart', onTouchOutside, { capture: true })
      clearTimeout(t)
      if (leaveTimer.current) clearTimeout(leaveTimer.current)
    }
  }, [containerRef])

  const track = (clientX: number, clientY: number) => {
    pointer.current = { x: clientX + window.scrollX, y: clientY + window.scrollY }
  }
  const cancelLeave = () => {
    if (leaveTimer.current) clearTimeout(leaveTimer.current)
    leaveTimer.current = null
  }

  const handlers = (key: string) => ({
    'data-follow': '', // marks a hoverable, so a tap OUTSIDE every hoverable can dismiss the tip
    onMouseEnter: (e: MouseEvent<Element>) => {
      cancelLeave()
      track(e.clientX, e.clientY)
      setAt({ key, ...pointer.current })
    },
    // Movement over a hoverable also (re)opens it: a scroll closes the tip while the pointer still rests on the row, and moving
    // within that row fires no new mouseenter, so without this the tip stayed dead until you left the row and came back.
    // Same key = same state object = React bails out, so this costs nothing per move.
    onMouseMove: (e: MouseEvent<Element>) => {
      cancelLeave()
      track(e.clientX, e.clientY)
      setAt((cur) => (cur?.key === key ? cur : { key, ...pointer.current }))
    },
    onMouseLeave: () => {
      cancelLeave()
      leaveTimer.current = setTimeout(() => setAt(null), LEAVE_GRACE_MS)
    },
    onTouchStart: (e: TouchEvent<Element>) => {
      const t = e.touches[0]
      touchStart.current = { x: t.clientX, y: t.clientY }
    },
    onTouchEnd: (e: TouchEvent<Element>) => {
      e.preventDefault()
      const start = touchStart.current
      const t = e.changedTouches[0]
      if (start && Math.hypot(t.clientX - start.x, t.clientY - start.y) > 10) return
      track(t.clientX, t.clientY)
      setAt((cur) => (cur?.key === key ? null : { key, ...pointer.current }))
    },
  })

  return { at, setAt, isScrolling, handlers, pointer }
}
