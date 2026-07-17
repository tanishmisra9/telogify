import { useEffect, useState } from 'react'
import { AnimatePresence, m } from 'framer-motion'
import { spring } from '@/lib/motion'

export interface NavSection {
  id: string
  label: string
}

// Fixed left-hand rail: dots double as the "jump to section" utility, the up/down arrows step
// sequentially, and the top dot (right below the header) doubles as back-to-top -- one
// restrained widget instead of three separate floating pieces. Shared by WeekendPage and
// SeasonPage.
export function SectionNav({ sections }: { sections: NavSection[] }) {
  const [active, setActive] = useState(sections[0]?.id)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const onScroll = () => setVisible(window.scrollY > 400)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    const els = sections.map((s) => document.getElementById(s.id)).filter((e): e is HTMLElement => e !== null)
    if (els.length === 0) return
    const observer = new IntersectionObserver(
      (entries) => {
        const intersecting = entries.filter((e) => e.isIntersecting)
        if (intersecting.length === 0) return
        const topMost = intersecting.reduce((a, b) => (a.boundingClientRect.top < b.boundingClientRect.top ? a : b))
        setActive(topMost.target.id)
      },
      { rootMargin: '-20% 0px -70% 0px' },
    )
    els.forEach((el) => observer.observe(el))
    return () => observer.disconnect()
  }, [sections])

  const activeIndex = Math.max(
    0,
    sections.findIndex((s) => s.id === active),
  )

  function jump(id: string) {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  if (sections.length < 2) return null

  return (
    <AnimatePresence>
      {visible && (
        <m.nav
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -8 }}
          transition={spring}
          aria-label="Section navigation"
          className="fixed left-8 top-1/2 z-30 hidden -translate-y-1/2 flex-col items-center gap-4 xl:flex"
        >
          <button
            type="button"
            onClick={() => sections[activeIndex - 1] && jump(sections[activeIndex - 1].id)}
            disabled={activeIndex <= 0}
            aria-label="Previous section"
            className="text-muted transition-colors hover:text-ink disabled:opacity-20"
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="m18 15-6-6-6 6" />
            </svg>
          </button>
          <div className="flex flex-col gap-3.5">
            {sections.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => jump(s.id)}
                aria-label={`Jump to ${s.label}`}
                aria-current={s.id === active}
                className="group relative flex items-center py-1"
              >
                <span
                  className={`h-3 w-3 rounded-full border-[1.5px] border-ink transition-colors ${s.id === active ? 'border-accent bg-accent' : 'bg-transparent group-hover:bg-ink/40'}`}
                />
                <span className="pointer-events-none absolute left-5 whitespace-nowrap rounded bg-ink px-2 py-1 text-sm text-bg opacity-0 transition-opacity group-hover:opacity-100">
                  {s.label}
                </span>
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => sections[activeIndex + 1] && jump(sections[activeIndex + 1].id)}
            disabled={activeIndex >= sections.length - 1}
            aria-label="Next section"
            className="text-muted transition-colors hover:text-ink disabled:opacity-20"
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="m6 9 6 6 6-6" />
            </svg>
          </button>
        </m.nav>
      )}
    </AnimatePresence>
  )
}
