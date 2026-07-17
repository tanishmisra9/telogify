import { resolveTeamColor } from '@/lib/teamColors'

/** Just the team-colored vertical rule; height tracks the surrounding font size. */
export function TeamRule({ team, className }: { team: string | null | undefined; className?: string }) {
  return (
    <span
      aria-hidden
      className={`h-[1em] w-[3px] shrink-0 rounded-[2px] ${className ?? ''}`}
      style={{ backgroundColor: resolveTeamColor(team ?? null) }}
    />
  )
}

/** Team identity: a team-colored rule followed by the team name. Color + text only
 * (no trademarked logos), so it's release-safe and on-brand with the editorial layout.
 * Weight/color/width come from the caller via className. `label` overrides the displayed
 * text while `team` still drives the color (e.g. a power-unit manufacturer name shown in
 * its works team's color, as in the season deployment Teams/Power units toggle). */
export function TeamMark({
  team,
  label,
  className,
}: {
  team: string | null | undefined
  label?: string
  className?: string
}) {
  return (
    <span className={`inline-flex min-w-0 items-center gap-2 ${className ?? ''}`}>
      <TeamRule team={team} />
      <span className="truncate">{label ?? team ?? 'Unknown'}</span>
    </span>
  )
}
