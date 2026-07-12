import { Link, useLocation } from 'react-router-dom'
import { LogoMark } from '@/components/Logo'
import { ThemeToggle } from '@/components/ThemeToggle'
import { Tooltip } from '@/components/Tooltip'

const LINKS = [
  { to: '/weekends', label: 'Weekends', hint: 'Browse analysed race weekends' },
  { to: '/season', label: 'Season', hint: 'Season-long constructor competitiveness' },
  { to: '/subscribe', label: 'Subscribe', hint: 'Get the weekly email digest' },
]

export function Nav() {
  const { pathname } = useLocation()
  const homeActive = pathname === '/'
  return (
    <header className="sticky top-0 z-40 border-b-[1.5px] border-ink bg-glass backdrop-blur-md">
      <nav className="mx-auto flex max-w-[1312px] flex-col items-start gap-2 px-6 py-3 sm:h-16 sm:flex-row sm:items-center sm:justify-between sm:gap-0 sm:py-0">
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
          <ThemeToggle />
        </div>
      </nav>
    </header>
  )
}
