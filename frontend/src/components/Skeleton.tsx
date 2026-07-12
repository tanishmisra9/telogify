// Height-reserving loading placeholders: a soft pulse (native Tailwind `animate-pulse`) on the
// design tokens, so a section holds its footprint while its data loads instead of the page
// growing and reflowing as each fetch resolves. `bg-surface`/`.glass` flip in dark mode for free.

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-[--radius-panel] bg-surface ${className}`} />
}

// Dressed as a paper card so the loading state matches the real `.glass` panels it stands in for.
// `label` previews the real heading (same position/size it'll render at) so a reader can tell
// which chart is still loading instead of every section looking like the same blank pulse.
export function SkeletonCard({ className = '', label }: { className?: string; label?: string }) {
  return (
    <div className={`glass animate-pulse rounded-[--radius-panel] ${label ? 'p-6' : ''} ${className}`}>
      {label && (
        <p className="font-display text-[2.025rem] font-semibold tracking-tight text-muted sm:text-[2.7rem]">
          {label}
        </p>
      )}
    </div>
  )
}
