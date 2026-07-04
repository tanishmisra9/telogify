// Height-reserving loading placeholders: a soft pulse (native Tailwind `animate-pulse`) on the
// design tokens, so a section holds its footprint while its data loads instead of the page
// growing and reflowing as each fetch resolves. `bg-surface`/`.glass` flip in dark mode for free.

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-[--radius-panel] bg-surface ${className}`} />
}

// Dressed as a paper card so the loading state matches the real `.glass` panels it stands in for.
export function SkeletonCard({ className = '' }: { className?: string }) {
  return <div className={`glass animate-pulse rounded-[--radius-panel] ${className}`} />
}
