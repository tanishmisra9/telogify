import { useEffect, useState } from 'react'
import { m } from 'framer-motion'
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

  // Active = the last section (nav order is DOM order) whose top has crossed 20% down the
  // viewport. Unlike an IntersectionObserver "top-most wins", this stays correct when a nav item
  // (a chart) sits inside another (its section).
  useEffect(() => {
    const onScroll = () => {
      const line = window.innerHeight * 0.2
      const atBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2
      let next = sections[0]?.id
      for (const s of sections) {
        const el = document.getElementById(s.id)
        if (el && el.getBoundingClientRect().top <= line) next = s.id
      }
      setActive(atBottom ? sections[sections.length - 1]?.id : next)
    }
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
    }
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
    <m.nav
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={spring}
      aria-label="Section navigation"
      className="fixed left-8 top-1/2 z-30 hidden -translate-y-1/2 flex-col items-center gap-4 min-[1400px]:flex"
    >
      <button
        type="button"
        onClick={() => sections[activeIndex - 1] && jump(sections[activeIndex - 1].id)}
        disabled={activeIndex <= 0}
        aria-label="Previous section"
        className="-m-3 rounded-full p-3 text-muted transition-[color,background-color,opacity] enabled:hover:bg-accent/10 enabled:hover:text-accent enabled:active:bg-accent/20 disabled:pointer-events-none disabled:opacity-0"
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
              className={`h-[17px] w-[17px] rounded-full border-[1.5px] border-ink transition-colors ${s.id === active ? 'border-accent bg-accent' : 'bg-transparent group-hover:bg-ink/40'}`}
            />
            <span className="pointer-events-none absolute left-7 whitespace-nowrap rounded bg-ink px-2 py-1 text-sm text-bg opacity-0 transition-opacity group-hover:opacity-100">
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
        className="-m-3 rounded-full p-3 text-muted transition-[color,background-color,opacity] enabled:hover:bg-accent/10 enabled:hover:text-accent enabled:active:bg-accent/20 disabled:pointer-events-none disabled:opacity-0"
      >
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
    </m.nav>
  )
}
