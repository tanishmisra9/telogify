import { Link } from 'react-router-dom'
import { LogoMark } from '@/components/Logo'

// App-wide footer: gives every page a bottom instead of stopping after its content.
export function Footer() {
  return (
    <footer className="mt-24 border-t-[1.5px] border-ink">
      <div className="mx-auto flex max-w-[1312px] flex-col gap-5 px-6 py-10 sm:flex-row sm:items-center sm:justify-between">
        <Link to="/" className="flex items-center gap-2.5 text-ink" aria-label="Telogify home">
          <LogoMark size={18} />
          <span className="font-display text-2xl leading-none tracking-tight">
            Telo<span className="text-accent">gify</span>
          </span>
        </Link>
        <p className="text-sm text-muted">Timing data via FastF1</p>
      </div>
    </footer>
  )
}
