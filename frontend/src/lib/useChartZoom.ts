import { useCallback, useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react'
import { anchorScroll, clampZoom, MIN_ZOOM, pinchZoom, stepZoom, wheelZoom } from '@/lib/zoom'

// Persistent zoom for a "by round" chart's scrolling viewport. The zoom is plain state: pinch, let go,
// and it stays; the viewport's own scrollbars navigate the zoomed chart. Inputs:
// - the +/- / reset buttons (zoom about the viewport centre),
// - a two-finger touch pinch (about the finger midpoint),
// - trackpad pinch and ctrl/cmd + wheel (Chrome/Firefox send a trackpad pinch as a wheel event with ctrlKey),
// - Safari's proprietary gesturestart/change/end (macOS trackpad pinch; on iOS it fires alongside the
//   touch pinch, so it is ignored while a touch pinch is active).
// The touch and wheel listeners are native and `passive: false`: React attaches its own handlers as
// passive, so a React onTouchMove/onWheel could not preventDefault the browser's page zoom.
// Also returns the viewport's content width (ignoring 0, which is a collapsed section: keep the last real
// width so reopening doesn't re-lay out) so the chart can size its plot from it.
export function useChartZoom(viewportRef: RefObject<HTMLElement | null>) {
  const [zoom, setZoom] = useState(MIN_ZOOM)
  const [width, setWidth] = useState(0)
  const [zooming, setZooming] = useState(false)
  const zoomRef = useRef(MIN_ZOOM)
  // True during a pinch and for a beat after the last finger lifts, so lifting two fingers over a dot
  // is never read as a tap on it.
  const pinchingRef = useRef(false)
  const pending = useRef<{ fx: number; fy: number; w: number; h: number; sl: number; st: number } | null>(null)
  const zoomingTimer = useRef<ReturnType<typeof setTimeout>>(undefined)

  // Change the zoom and remember what to keep under the focal point; the scroll is corrected in the layout
  // effect below, once the resized content is in the DOM. Several calls before a commit keep the FIRST
  // sizes/scroll (the DOM hasn't changed yet) and the latest focal point.
  const applyZoom = useCallback(
    (nextZoom: number, focal?: { x: number; y: number }) => {
      const next = clampZoom(nextZoom)
      if (next === zoomRef.current) return
      const el = viewportRef.current
      if (el) {
        const f = focal ?? { x: el.clientWidth / 2, y: el.clientHeight / 2 }
        const p = pending.current
        pending.current = p
          ? { ...p, fx: f.x, fy: f.y }
          : { fx: f.x, fy: f.y, w: el.scrollWidth, h: el.scrollHeight, sl: el.scrollLeft, st: el.scrollTop }
      }
      zoomRef.current = next
      setZoom(next)
      // While zooming the chart must not glide its lines and dots (that animation is for tab switches).
      setZooming(true)
      clearTimeout(zoomingTimer.current)
      zoomingTimer.current = setTimeout(() => setZooming(false), 250)
    },
    [viewportRef],
  )

  useLayoutEffect(() => {
    const p = pending.current
    const el = viewportRef.current
    if (!p || !el) return
    pending.current = null
    el.scrollLeft = anchorScroll(p.sl, p.fx, p.w, el.scrollWidth, el.clientWidth)
    el.scrollTop = anchorScroll(p.st, p.fy, p.h, el.scrollHeight, el.clientHeight)
  }, [zoom, viewportRef])

  useEffect(() => {
    const el = viewportRef.current
    if (!el) return
    const rect = () => el.getBoundingClientRect()

    const ro = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width > 0) setWidth(entry.contentRect.width)
    })
    ro.observe(el)

    // One zoom update per frame, however many touchmove/wheel events arrive; the wheel accumulates on
    // the latest target rather than the last applied value.
    let raf = 0
    let target: { z: number; fx: number; fy: number } | null = null
    const flush = () => {
      raf = 0
      const t = target
      target = null
      if (t) applyZoom(t.z, { x: t.fx, y: t.fy })
    }
    const schedule = (z: number, fx: number, fy: number) => {
      target = { z, fx, fy }
      if (!raf) raf = requestAnimationFrame(flush)
    }

    let pinch: { d0: number; z0: number } | null = null
    let pinchEndTimer: ReturnType<typeof setTimeout> | undefined
    const dist = (t: TouchList) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY)
    const onTouchStart = (e: TouchEvent) => {
      if (e.touches.length !== 2) return
      pinch = { d0: dist(e.touches), z0: zoomRef.current }
      pinchingRef.current = true
      clearTimeout(pinchEndTimer)
    }
    const onTouchMove = (e: TouchEvent) => {
      if (!pinch || e.touches.length !== 2) return
      e.preventDefault()
      const r = rect()
      const mx = (e.touches[0].clientX + e.touches[1].clientX) / 2 - r.left
      const my = (e.touches[0].clientY + e.touches[1].clientY) / 2 - r.top
      schedule(pinchZoom(pinch.z0, pinch.d0, dist(e.touches)), mx, my)
    }
    const onTouchEnd = (e: TouchEvent) => {
      if (!pinch || e.touches.length >= 2) return
      pinch = null
      pinchEndTimer = setTimeout(() => {
        pinchingRef.current = false
      }, 350)
    }

    let gesture: { z0: number } | null = null
    const onGestureStart = (e: Event) => {
      e.preventDefault()
      gesture = { z0: zoomRef.current }
    }
    const onGestureChange = (e: Event) => {
      e.preventDefault()
      if (pinch || !gesture) return
      const ge = e as unknown as { scale: number; clientX?: number; clientY?: number }
      const r = rect()
      const fx = Number.isFinite(ge.clientX) ? (ge.clientX as number) - r.left : r.width / 2
      const fy = Number.isFinite(ge.clientY) ? (ge.clientY as number) - r.top : r.height / 2
      schedule(clampZoom(gesture.z0 * ge.scale), fx, fy)
    }
    const onGestureEnd = (e: Event) => {
      e.preventDefault()
      gesture = null
    }

    const onWheel = (e: WheelEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return // a plain wheel still scrolls the chart and then the page
      e.preventDefault()
      if (gesture) return
      const r = rect()
      schedule(wheelZoom(target?.z ?? zoomRef.current, e.deltaY, e.deltaMode), e.clientX - r.left, e.clientY - r.top)
    }

    el.addEventListener('touchstart', onTouchStart, { passive: true })
    el.addEventListener('touchmove', onTouchMove, { passive: false })
    el.addEventListener('touchend', onTouchEnd, { passive: true })
    el.addEventListener('touchcancel', onTouchEnd, { passive: true })
    el.addEventListener('wheel', onWheel, { passive: false })
    el.addEventListener('gesturestart', onGestureStart, { passive: false })
    el.addEventListener('gesturechange', onGestureChange, { passive: false })
    el.addEventListener('gestureend', onGestureEnd, { passive: false })
    return () => {
      ro.disconnect()
      cancelAnimationFrame(raf)
      clearTimeout(pinchEndTimer)
      el.removeEventListener('touchstart', onTouchStart)
      el.removeEventListener('touchmove', onTouchMove)
      el.removeEventListener('touchend', onTouchEnd)
      el.removeEventListener('touchcancel', onTouchEnd)
      el.removeEventListener('wheel', onWheel)
      el.removeEventListener('gesturestart', onGestureStart)
      el.removeEventListener('gesturechange', onGestureChange)
      el.removeEventListener('gestureend', onGestureEnd)
    }
  }, [viewportRef, applyZoom])

  useEffect(() => () => clearTimeout(zoomingTimer.current), [])

  return {
    zoom,
    width,
    zooming,
    pinchingRef,
    zoomIn: () => applyZoom(stepZoom(zoomRef.current, 1)),
    zoomOut: () => applyZoom(stepZoom(zoomRef.current, -1)),
    reset: () => applyZoom(MIN_ZOOM),
  }
}
