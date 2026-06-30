import { Link } from 'react-router-dom'

export function Nav() {
  return (
    <header className="sticky top-0 z-40 glass">
      <nav className="mx-auto max-w-5xl flex items-center justify-between px-6 h-14">
        <Link to="/" className="text-lg font-semibold tracking-tight">
          Telo<span className="text-accent">gify</span>
        </Link>
        <div className="flex gap-6 text-sm text-muted">
          <Link to="/" className="hover:text-ink transition-colors">
            Weekends
          </Link>
          <Link to="/subscribe" className="hover:text-ink transition-colors">
            Subscribe
          </Link>
        </div>
      </nav>
    </header>
  )
}
