import { Link } from 'react-router-dom'
import { BlurFade } from '@/components/BlurFade'

export function NotFoundPage() {
  return (
    <main className="mx-auto flex min-h-[60vh] max-w-[1312px] flex-col justify-center px-6 py-16">
      <BlurFade>
        <p className="kicker text-accent">404</p>
        <h1 className="mt-3 font-display text-[3.375rem] leading-[0.95] tracking-tight sm:text-[5.4rem]">
          This page didn&apos;t finish the race.
        </h1>
        <p className="mt-4 max-w-lg text-lg text-muted">
          There's nothing at this address. It may have retired, or never existed.
        </p>
        <div className="mt-8 flex flex-wrap gap-4">
          <Link
            to="/weekends"
            className="lift inline-flex items-center border-[1.5px] border-ink bg-accent px-6 py-2.5 font-display text-2xl text-accent-ink shadow-[4px_4px_0_var(--color-shadow)]"
          >
            Browse weekends
          </Link>
          <Link
            to="/"
            className="lift inline-flex items-center border-[1.5px] border-ink bg-surface px-6 py-2.5 font-display text-2xl text-ink shadow-[4px_4px_0_var(--color-shadow)]"
          >
            Go home
          </Link>
        </div>
      </BlurFade>
    </main>
  )
}
