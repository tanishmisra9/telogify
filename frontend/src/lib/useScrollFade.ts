import { useEffect, useState, type RefObject } from 'react'

// Whether a horizontally-scrollable element has more content past its right edge right now --
// true only while there's actually somewhere left to scroll, so an edge-fade hint can appear
// only when it's true (content overflows a narrow mobile card) and disappear once the reader
// reaches the end.
export function useScrollFade(ref: RefObject<HTMLElement | null>) {
  const [canScrollRight, setCanScrollRight] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const update = () => setCanScrollRight(el.scrollWidth - el.scrollLeft - el.clientWidth > 2)
    update()
    el.addEventListener('scroll', update, { passive: true })
    const observer = new ResizeObserver(update)
    observer.observe(el)
    return () => {
      el.removeEventListener('scroll', update)
      observer.disconnect()
    }
  }, [ref])

  return canScrollRight
}
