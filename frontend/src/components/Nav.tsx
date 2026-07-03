import { Link, useLocation } from 'react-router-dom'
import { ThemeToggle } from '@/components/ThemeToggle'
import { Tooltip } from '@/components/Tooltip'

const LINKS = [
  { to: '/weekends', label: 'Weekends', hint: 'Browse analysed race weekends' },
  { to: '/season', label: 'Season', hint: 'Season-long constructor competitiveness' },
  { to: '/subscribe', label: 'Subscribe', hint: 'Get the weekly email digest' },
]

export function Nav() {
  const { pathname } = useLocation()
  return (
    <header className="sticky top-0 z-40 border-b-[1.5px] border-ink bg-glass backdrop-blur-md">
      <nav className="mx-auto flex max-w-6xl flex-col items-start gap-2 px-6 py-3 sm:h-16 sm:flex-row sm:items-center sm:justify-between sm:gap-0 sm:py-0">
        <div className="flex items-center gap-4">
          <ThemeToggle />
          <Link to="/" className="group flex items-baseline gap-2">
            <span className="font-display text-3xl leading-none tracking-tight">
              Telo<span className="text-accent">gify</span>
            </span>
          </Link>
        </div>
        <div className="flex items-center gap-1">
          {LINKS.map((l) => {
            const active = pathname.startsWith(l.to)
            return (
              <Tooltip key={l.to} label={l.hint}>
                <Link
                  to={l.to}
                  className={`kicker border px-3 py-2 transition-colors ${
                    active
                      ? 'border-ink bg-ink text-bg'
                      : 'border-transparent text-muted hover:border-ink hover:text-ink'
                  }`}
                >
                  {l.label}
                </Link>
              </Tooltip>
            )
          })}
        </div>
      </nav>
    </header>
  )
}
