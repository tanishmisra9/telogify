import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { BlurFade } from '@/components/BlurFade'

/** A short terminal page: status marker, verdict, one line of explanation, up to two actions.
 *
 * The chassis is NotFoundPage's, which is the right shape for this kind of page: min-h-[60vh]
 * plus centred flex column so a three-line page reads as deliberate rather than stranded at the
 * top of the viewport. Shared here because verify and unsubscribe would otherwise be the third
 * and fourth copies of it.
 */
export function StatusPage({
  marker,
  heading,
  children,
  actions,
}: {
  marker: string
  heading: string
  children?: ReactNode
  actions?: ReactNode
}) {
  return (
    <main className="mx-auto flex min-h-[60vh] max-w-[1312px] flex-col justify-center px-6 py-16">
      <BlurFade>
        <p className="kicker text-accent">{marker}</p>
        <h1 className="mt-3 font-display text-[3.375rem] leading-[0.95] tracking-tight sm:text-[5.4rem]">
          {heading}
        </h1>
        {children && <div className="mt-4 max-w-lg text-lg text-muted">{children}</div>}
        {actions && <div className="mt-8 flex flex-wrap gap-4">{actions}</div>}
      </BlurFade>
    </main>
  )
}

const BUTTON_BASE =
  'lift inline-flex items-center rounded-panel border-[1.5px] border-ink px-6 py-2.5 font-display text-2xl shadow-[4px_4px_0_var(--color-shadow)] outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-4 focus-visible:ring-offset-bg'

export function StatusLink({
  to,
  variant = 'secondary',
  children,
}: {
  to: string
  variant?: 'primary' | 'secondary'
  children: ReactNode
}) {
  const tone = variant === 'primary' ? 'bg-accent text-accent-ink' : 'bg-surface text-ink'
  return (
    <Link to={to} className={`${BUTTON_BASE} ${tone}`}>
      {children}
    </Link>
  )
}

export function StatusButton({
  onClick,
  disabled,
  children,
}: {
  onClick: () => void
  disabled?: boolean
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`${BUTTON_BASE} bg-accent text-accent-ink disabled:opacity-60`}
    >
      {children}
    </button>
  )
}
