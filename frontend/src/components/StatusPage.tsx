import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { BlurFade } from '@/components/BlurFade'
import { Skeleton } from '@/components/Skeleton'

/** The persistent chassis for a short terminal page: min-h-[60vh] plus centred flex column so a
 * three-line page reads as deliberate rather than stranded at the top of the viewport. Mounted
 * ONCE per page (unlike the old single `StatusPage`, which was called fresh per result state) so
 * that swapping `StatusContent` inside it via `LoadingSwap` crossfades instead of hard-cutting.
 */
export function StatusShell({ children }: { children: ReactNode }) {
  return (
    <main className="mx-auto flex min-h-[60vh] max-w-[1312px] flex-col justify-center px-6 py-16">
      {children}
    </main>
  )
}

/** One state's content: status marker, verdict, one line of explanation, up to two actions.
 * `marker` is optional -- a kicker that only restates the heading in fewer words (e.g.
 * "Checking" above "Confirming your seat.") is the eyebrow-redundant-with-heading pattern
 * DESIGN.md already warns `.kicker` against, so a loading state can render heading-only.
 */
export function StatusContent({
  marker,
  heading,
  children,
  actions,
}: {
  // ReactNode, not string: the loading placeholder puts a <Skeleton /> in this slot so its
  // heading picks up the same `mt-3` offset the terminal states have, keeping both headings on
  // one baseline through the crossfade.
  marker?: ReactNode
  heading: string
  children?: ReactNode
  actions?: ReactNode
}) {
  return (
    <BlurFade>
      {marker && <p className="kicker text-accent">{marker}</p>}
      <h1 className={`font-display text-[3.375rem] leading-[0.95] tracking-tight sm:text-[5.4rem] ${marker ? 'mt-3' : ''}`}>
        {heading}
      </h1>
      {children && <div className="mt-4 max-w-lg text-lg text-muted">{children}</div>}
      {actions && <div className="mt-8 flex flex-wrap gap-4">{actions}</div>}
    </BlurFade>
  )
}

/** The loading state for Verify/Unsubscribe, shaped to reserve a terminal state's footprint.
 *
 * StatusShell is `min-h-[60vh]` + `justify-center`, so it centres whatever it holds: a short
 * loading state and a tall settled one centre at different offsets and the heading visibly jumps
 * mid-crossfade. Measured at 1280px before this existed: the h1 moved 60.36px (275.95 -> 215.59).
 *
 * Every height here is measured off the real confirmed state, per frontend/CLAUDE.md's rule that
 * placeholders mirror measured heights rather than a guessed total. The containers carry the
 * height; the bars inside are decoration, so re-styling them cannot silently change the
 * reservation:
 *
 *   kicker   17px both widths
 *   body     84px at sm+ (3 lines x 28px), 112px below sm (copy wraps to 4)
 *   actions  54px at sm+ (one row), 124px below sm (the two buttons wrap to two rows)
 *
 * Tuned against confirmed/unsubscribed, the overwhelmingly common path. Branches with one button
 * and shorter copy (expired, invalid, error) land close but not exact; equalising every state at
 * every width would mean forcing all of them to a single height, which is a worse trade.
 */
export function CheckingPlaceholder({ heading }: { heading: string }) {
  return (
    <StatusContent
      marker={<Skeleton className="h-[17px] w-24" />}
      heading={heading}
      actions={<Skeleton className="h-[54px] w-56 max-sm:h-[124px] max-sm:w-full" />}
    >
      <div className="h-[84px] space-y-3 max-sm:h-[112px]">
        <Skeleton className="h-5 w-full" />
        <Skeleton className="h-5 w-full" />
        <Skeleton className="h-5 w-2/3" />
      </div>
    </StatusContent>
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
