import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, m } from 'framer-motion'
import { Link, useLocation } from 'react-router-dom'
import { LogoMark } from '@/components/Logo'
import { ThemeToggle } from '@/components/ThemeToggle'
import { Tooltip } from '@/components/Tooltip'
import { spring } from '@/lib/motion'

const LINKS = [
  { to: '/weekends', label: 'Weekends', hint: 'Browse analysed race weekends' },
  { to: '/season', label: 'Season', hint: 'Season-long constructor competitiveness' },
  { to: '/subscribe', label: 'Subscribe', hint: 'Get the weekly email digest' },
]

function MenuIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <line x1="4" x2="20" y1="6" y2="6" />
      <line x1="4" x2="20" y1="12" y2="12" />
      <line x1="4" x2="20" y1="18" y2="18" />
    </svg>
  )
}

function CloseIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M18 6 6 18" />
      <path d="m6 6 12 12" />
    </svg>
  )
}

const mobileListVariants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.05, delayChildren: 0.05 } },
}

const mobileItemVariants = {
  hidden: { opacity: 0, y: 32 },
  show: { opacity: 1, y: 0, transition: spring },
  exit: { opacity: 0, y: 16, transition: spring },
}

export function Nav() {
  const { pathname } = useLocation()
  const homeActive = pathname === '/'
  const [menuOpen, setMenuOpen] = useState(false)
  const menuTriggerRef = useRef<HTMLButtonElement>(null)

  // Full-screen mobile menu: lock the page behind it and pull it out of the tab order so
  // keyboard/screen-reader users can't reach content hidden underneath the overlay.
  useEffect(() => {
    if (!menuOpen) return
    const prevOverflow = document.documentElement.style.overflow
    document.documentElement.style.overflow = 'hidden'
    const inertTargets = document.querySelectorAll('main, footer')
    inertTargets.forEach((el) => el.setAttribute('inert', ''))
    return () => {
      document.documentElement.style.overflow = prevOverflow
      inertTargets.forEach((el) => el.removeAttribute('inert'))
    }
  }, [menuOpen])

  useEffect(() => {
    if (!menuOpen) return
    const overlay = document.getElementById('mobile-nav-overlay')
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setMenuOpen(false)
        menuTriggerRef.current?.focus()
        return
      }
      if (e.key !== 'Tab' || !overlay) return
      const focusable = overlay.querySelectorAll<HTMLElement>('a[href], button')
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }
    const raf = requestAnimationFrame(() => {
      overlay?.querySelector<HTMLElement>('a[href]')?.focus()
    })
    window.addEventListener('keydown', onKey)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('keydown', onKey)
    }
  }, [menuOpen])

  // Route changes (link click) close the menu on their own via `pathname` below; this also
  // catches back/forward navigation while the overlay happens to be open.
  useEffect(() => {
    setMenuOpen(false)
  }, [pathname])

  return (
    <>
      <header className="sticky top-0 z-40 border-b-[1.5px] border-ink bg-glass backdrop-blur-md">
      <nav className="mx-auto flex h-16 max-w-[1312px] items-center justify-between px-6">
        <Link
          to="/"
          aria-current={homeActive ? 'page' : undefined}
          aria-label="Telogify home"
          className={`group flex items-center gap-2.5 border-b-2 pb-0.5 text-ink transition-colors ${
            homeActive ? 'border-accent' : 'border-transparent'
          }`}
        >
          <LogoMark />
          <span className="font-display text-3xl leading-none tracking-tight">
            Telo<span className="text-accent">gify</span>
          </span>
        </Link>
        <div className="flex items-center gap-1">
          <div className="hidden items-center gap-1 md:flex">
            {LINKS.map((l) => {
              const active = pathname.startsWith(l.to)
              return (
                <Tooltip key={l.to} label={l.hint}>
                  <Link
                    to={l.to}
                    aria-current={active ? 'page' : undefined}
                    aria-label={l.label}
                    className={`kicker border-b-2 px-3 py-2 transition-colors ${
                      active
                        ? 'border-accent font-semibold text-ink'
                        : 'border-transparent text-muted hover:border-ink hover:text-ink'
                    }`}
                  >
                    {l.label}
                  </Link>
                </Tooltip>
              )
            })}
          </div>
          <ThemeToggle />
          <button
            ref={menuTriggerRef}
            type="button"
            aria-expanded={menuOpen}
            aria-controls="mobile-nav-overlay"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            onClick={() => setMenuOpen((o) => !o)}
            className="flex h-10 w-10 items-center justify-center text-ink transition-colors hover:bg-ink hover:text-bg md:hidden"
          >
            <span className="relative grid h-6 w-6 place-items-center">
              <m.span
                aria-hidden
                style={{ gridArea: '1 / 1' }}
                className="flex items-center justify-center"
                initial={false}
                animate={{ opacity: menuOpen ? 0 : 1 }}
                transition={{ duration: 0.15 }}
              >
                <MenuIcon />
              </m.span>
              <m.span
                aria-hidden
                style={{ gridArea: '1 / 1' }}
                className="flex items-center justify-center"
                initial={false}
                animate={{ opacity: menuOpen ? 1 : 0 }}
                transition={{ duration: 0.15 }}
              >
                <CloseIcon />
              </m.span>
            </span>
          </button>
        </div>
      </nav>
    </header>

      {/* Sibling of `<header>`, not a descendant: `backdrop-blur-md` above puts a `backdrop-filter`
          on the header, which (like `transform`/`filter`) makes it the containing block for any
          `position: fixed` descendant -- nesting the overlay inside header collapsed it into the
          header's own 64px box instead of the viewport. */}
      <AnimatePresence>
        {menuOpen && (
          <m.div
            key="mobile-nav-overlay"
            id="mobile-nav-overlay"
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
            className="fixed inset-x-0 top-16 bottom-0 z-40 flex flex-col bg-bg md:hidden"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            onClick={(e) => {
              if (e.target === e.currentTarget) setMenuOpen(false)
            }}
          >
            <m.ul
              className="flex grow list-none flex-col items-center justify-center gap-8 px-6"
              variants={mobileListVariants}
              initial="hidden"
              animate="show"
              exit="hidden"
              aria-label="Mobile sections"
            >
              {LINKS.map((l) => {
                const active = pathname.startsWith(l.to)
                return (
                  <m.li key={l.to} variants={mobileItemVariants}>
                    <Link
                      to={l.to}
                      aria-current={active ? 'page' : undefined}
                      className={`block rounded-sm py-1 text-center font-display text-6xl font-medium tracking-tight outline-none transition-colors focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-4 focus-visible:ring-offset-bg ${
                        active ? 'text-ink underline decoration-accent decoration-2 underline-offset-[0.25em]' : 'text-muted hover:text-ink'
                      }`}
                    >
                      {l.label}
                    </Link>
                  </m.li>
                )
              })}
            </m.ul>
          </m.div>
        )}
      </AnimatePresence>
    </>
  )
}
