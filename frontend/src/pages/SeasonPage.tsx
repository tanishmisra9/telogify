import { useReducedMotion, m } from 'framer-motion'
import { Navigate, useParams } from 'react-router-dom'
import { BackHomeButton } from '@/components/BackHomeButton'
import { BackToTopButton } from '@/components/BackToTopButton'
import { BlurFade } from '@/components/BlurFade'
import { Insight } from '@/components/Insight'
import { LoadingSwap } from '@/components/LoadingSwap'
import { SeasonDeploymentChart } from '@/components/SeasonDeploymentChart'
import { SeasonTrendChart } from '@/components/SeasonTrendChart'
import { SectionNav, type NavSection } from '@/components/SectionNav'
import { SectionTitle } from '@/components/SectionTitle'
import { SkeletonCard } from '@/components/Skeleton'
import { TeamRule } from '@/components/TeamMark'
import { deploymentInsights } from '@/lib/deploymentInsights'
import { axisTicks, barFractions, gapCells } from '@/lib/gapLadder'
import { resolveTeamColor, teamColorWithAlpha, teamShortName } from '@/lib/teamColors'
import { useIsMobile } from '@/lib/useIsMobile'
import {
  useApi,
  type SeasonConstructorRow,
  type SeasonDeployment,
  type SeasonDeploymentInsightItem,
  type SeasonSnapshot,
  type WeekendSummary,
} from '@/lib/api'

const CONF_LABEL: Record<string, string> = { low: 'low data', med: 'partial data' }

function ConfidenceChip({ confidence }: { confidence: string }) {
  if (confidence === 'high') return null
  return (
    <span className="whitespace-nowrap rounded-[--radius-panel] border border-border px-2 py-0.5 text-xs text-muted">
      {CONF_LABEL[confidence] ?? confidence}
    </span>
  )
}

// gapCells' sentinel string stays "best" (lib/gapLadder.ts + its tests); only the displayed
// label changes here.
const renderGap = (text: string | null) =>
  text == null ? '–' : text === 'best' ? <span className="font-sans font-semibold text-ink">leader</span> : text

// Fixed column widths shared by the header and every row so the axis ticks land directly above
// the bars they describe, and so a team's bar always starts at the same x position regardless
// of its name length -- the zero rule reads as one continuous line down the panel. One row shape
// at every width (team name and bar stay on the same line on mobile too); only the widths shrink
// -- the team name truncates rather than wrapping to a second line.
const RANK_W = 'w-6 sm:w-9'
const TEAM_W = 'w-24 sm:w-44'
const FIGURE_W = 'w-14 sm:w-24'

function RankingTable({ rows }: { rows: SeasonConstructorRow[] }) {
  const reduce = useReducedMotion()

  // Pace only: the row order still comes from the locked 60/40 race+qualifying blend
  // (r.overall_rank, set server-side), but the bar and figure show race pace alone, in seconds
  // behind the season's best -- see the footnote below.
  const paceValues = rows.map((r) => r.pace_gap.mean)
  const present = paceValues.filter((v): v is number => v != null)
  const maxGap = present.length > 0 ? Math.max(...present) - Math.min(...present) : 0
  const ticks = axisTicks(maxGap)
  const tickMax = ticks[ticks.length - 1] || 1 // guards a flat field (every gap 0, ticks = [0])

  const paceCells = gapCells(paceValues, (d) => `+${d.toFixed(3)}s`)
  const fractions = barFractions(paceValues)

  return (
    <div>
      {/* Header mirrors each row's 4 columns (rank / team / track / figure) so its axis ticks
          sit directly above the bars. Desktop only -- "Team" doesn't fit the mobile column
          widths below, and the per-row figure already carries the exact number, so a squeezed
          mobile header would add clutter without adding information. The figure column's own
          label ("Race pace") was removed -- the bars already read as pace, a caption calling out
          one column was redundant; the trailing spacer stays so the tick axis above still lines
          up with the track column, not the row's full width. */}
      <div className="hidden items-center gap-3 border-b border-border pb-2 sm:flex">
        <span className={`${RANK_W} shrink-0`} aria-hidden />
        <span className={`${TEAM_W} shrink-0 text-lg font-semibold text-ink`}>Team</span>
        <span className="relative h-4 flex-1">
          {ticks.map((t, i) => (
            <span
              key={t}
              className="absolute top-0 whitespace-nowrap text-xs text-muted"
              style={{
                left: `${(t / tickMax) * 100}%`,
                transform:
                  i === 0 ? 'translateX(0)' : i === ticks.length - 1 ? 'translateX(-100%)' : 'translateX(-50%)',
              }}
            >
              {t === 0 ? '0' : `+${t}s`}
            </span>
          ))}
        </span>
        <span className={`${FIGURE_W} shrink-0`} aria-hidden />
      </div>

      <ol>
        {rows.map((r, i) => {
          const b = i > 0 ? 'border-t border-border' : ''
          const fraction = fractions[i]
          const figure = renderGap(paceCells[i])

          // Confidence chip only fits on wider rows: its own text ("partial data") is close to
          // the entire mobile team column's width, so it would crowd out the name it's meant to
          // annotate. Every team is "high" confidence at time of writing; when a thin-data team
          // does show a chip, the desktop-only reveal is the tradeoff for keeping mobile scannable.
          // Mobile uses the same short names as the pace-chart axis ("Red Bull Racing" -> "Red
          // Bull", "Racing Bulls" -> "RB") instead of truncating the full name with an ellipsis
          // -- a real name that fits beats a clipped one. truncate stays as a safety net; every
          // short name already fits TEAM_W without needing it. Aston Martin gets its own
          // one-word short name ("Aston") instead of teamShortName's "AM" -- there was room for
          // more than 2 letters, just not the full "Aston Martin".
          const mobileName = r.constructor === 'Aston Martin' ? 'Aston' : teamShortName(r.constructor)
          const team = (
            <span className="flex min-w-0 items-center gap-2">
              <TeamRule team={r.constructor} />
              <span className="truncate font-medium text-ink">
                <span className="hidden sm:inline">{r.constructor}</span>
                <span className="sm:hidden">{mobileName}</span>
              </span>
              <span className="hidden shrink-0 sm:inline-flex">
                <ConfidenceChip confidence={r.confidence} />
              </span>
            </span>
          )

          // The zero rule (border-l) marks every row's baseline -- the season's best -- as one
          // continuous vertical line. The bar itself grows rightward from it in team color; a
          // team with no pace data (fraction null) shows the rule with no fill, not a fabricated
          // zero-length bar that would misread as tied for best. On the leader's own row
          // (fraction === 0) there's no bar next to the rule to give it color, so it reads as a
          // bare gray sliver -- thicken it and color it with that team's own color there only;
          // every other row's rule stays the plain neutral baseline.
          const isLeaderRow = fraction === 0
          const track = (
            <span
              className="relative h-[1.375rem] flex-1 border-l-[1.5px] border-ink/25"
              style={isLeaderRow ? { borderLeftWidth: '2px', borderLeftColor: resolveTeamColor(r.constructor) } : undefined}
            >
              {fraction != null && (
                <m.span
                  className={`absolute inset-y-0 left-0 block rounded-r-[1px] ${fraction > 0 ? 'min-w-[3px]' : ''}`}
                  style={{
                    width: `${fraction * 100}%`,
                    backgroundColor: teamColorWithAlpha(r.constructor, 0.55),
                    transformOrigin: 'left',
                  }}
                  initial={reduce ? false : { scaleX: 0 }}
                  animate={{ scaleX: 1 }}
                  transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1], delay: reduce ? 0 : i * 0.03 }}
                />
              )}
            </span>
          )

          // One row shape at every width: team name and bar always share a line, columns aligned
          // to the header above on sm+. Narrower fixed widths (RANK_W/TEAM_W/FIGURE_W) do the
          // work below sm -- the team name truncates into the space it's given rather than the
          // row wrapping to a second line.
          return (
            <li key={r.constructor} className={`flex items-center gap-2 py-3 sm:gap-3 ${b}`}>
              <span className={`num ${RANK_W} shrink-0 text-sm text-muted`}>{r.overall_rank ?? '–'}</span>
              <span className={`${TEAM_W} shrink-0`}>{team}</span>
              {track}
              <span className={`num ${FIGURE_W} shrink-0 text-right text-sm text-ink`}>{figure}</span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}

// The LLM-written verdicts (telogify run-season-deployment) are the primary read, already in
// rank order. Until that's been run for this year, fall back to a deterministic read of the
// same scatter (lib/deploymentInsights.ts) so the section is never blank.
function deploymentPanels(deployment: SeasonDeployment): SeasonDeploymentInsightItem[] {
  if (deployment.insights.length > 0) return deployment.insights
  return deploymentInsights(deployment.scatter, deployment.pu_groups).map((v, i) => ({
    slot: i + 1,
    header: v.header,
    explanation_web: v.explanation_web,
    pu: v.pu,
    works_team: v.works_team,
    teams: v.teams,
  }))
}

function SeasonView({ year }: { year: number }) {
  const isMobile = useIsMobile()
  const season = useApi<SeasonSnapshot>(`/season/${year}`)
  const deployment = useApi<SeasonDeployment>(`/season/${year}/deployment`)
  const rows = season.data?.constructors ?? []
  const hasDeployment = !!deployment.data && Object.keys(deployment.data.scatter).length > 0
  const deploymentPanelItems = deployment.data ? deploymentPanels(deployment.data) : []

  const navSections: NavSection[] = [
    rows.length > 0 ? { id: 'ranking', label: 'Ranking' } : null,
    rows.length > 0 ? { id: 'gap-by-round', label: 'Gap by round' } : null,
    rows.length > 0 && hasDeployment ? { id: 'deployment', label: 'Deployment' } : null,
  ].filter((s): s is NavSection => s !== null)

  return (
    <main className="mx-auto max-w-[1312px] px-6 py-16 sm:py-24">
      <SectionNav sections={navSections} />
      <BlurFade>
        <div className="mb-6">
          <BackHomeButton />
        </div>
        {/* Same heading-row shape as Weekends.tsx (h1 + kicker badge, one border-b-2 divider)
            so the two pages' titles land at the same position and size when switching between
            the WEEKENDS/SEASON nav links, instead of the season year stacking above as its own
            line and pushing the heading down. */}
        <div className="flex flex-col gap-3 border-b-2 border-ink pb-3 sm:flex-row sm:items-end sm:justify-between sm:gap-4">
          {/* Split on purpose, matching Weekends' heading: mobile keeps the 0.9x display-ramp size
              (text-[3.375rem]) because the narrower column needs it, while sm+ is back on the raw
              text-7xl it was before the 0.9x pass -- the reduction was only ever wanted on mobile. */}
          <h1 className="font-display text-[3.375rem] leading-[0.95] tracking-tight sm:text-7xl">Season at a glance</h1>
          <span className="kicker whitespace-nowrap text-muted">{year} season</span>
        </div>
        <p className="mt-4 max-w-3xl text-lg leading-relaxed text-muted">
          Every team's season so far, rolled up from the weekend pages.
        </p>
      </BlurFade>

      <section id="ranking" className="mt-16 scroll-mt-24">
        <SectionTitle delay={0.08}>Ranking</SectionTitle>
        {/* LoadingSwap reserves the table's real footprint while loading and crossfades the
            skeleton into the resolved content in place, instead of the page suddenly growing
            underneath a one-line "Loading…" string. Heights measured from the real rendered
            panel (673px desktop / 744px mobile at an 11-constructor field), not estimated.
            Breakpoint is sm: (640px), matching RankingTable's own column-width swap (RANK_W /
            TEAM_W / FIGURE_W) -- md: (768px) would leave a 640-768px dead zone where the real
            content has already widened to its desktop columns but the skeleton hasn't. */}
        <LoadingSwap
          loading={season.loading}
          delay={0.08}
          placeholder={<SkeletonCard className="min-h-[744px] sm:min-h-[673px]" />}
        >
          {season.error ? (
            <p className="text-sm text-muted">No season data for {year}.</p>
          ) : rows.length > 0 ? (
            <div className="glass rounded-[--radius-panel] p-6">
              <RankingTable rows={rows} />
              <p className="mt-4 text-sm text-muted">
                Ranked on the season's blend of race and qualifying pace (60/40). Each bar is
                race pace alone: the season's best team shows "leader", every other team its gap
                to it in seconds. A "partial data" or "low data" tag marks a team seen in too
                few rounds to read at full confidence.
              </p>
            </div>
          ) : null}
        </LoadingSwap>
      </section>

      {/* Always rendered (not gated on rows.length): keeps the same skeleton-then-content
          swap as the Ranking table above, instead of these sections popping into existence
          all at once the moment the season fetch resolves and shoving the footer down. */}
      {(season.loading || rows.length > 0) && (
        <>
          <section id="gap-by-round" className="mt-20 scroll-mt-24">
            <SectionTitle delay={0.16}>Gap by round</SectionTitle>
            {/* Measured 927px desktop / 947px mobile -- close enough to use one value. */}
            <LoadingSwap
              loading={season.loading}
              delay={0.16}
              placeholder={<SkeletonCard className="min-h-[950px]" />}
            >
              <SeasonTrendChart rows={rows} rounds={season.data?.rounds ?? []} />
            </LoadingSwap>
          </section>

          {(deployment.loading || hasDeployment) && (
            <section id="deployment" className="mt-20 scroll-mt-24">
              <SectionTitle delay={0.24}>Deployment</SectionTitle>
              <LoadingSwap
                loading={deployment.loading}
                delay={0.24}
                placeholder={
                  <>
                    {/* 5 placeholders, one per PU_GROUPS entry (backend/telogify/analysis/
                        season_deployment.py) -- Mercedes, Ferrari, Red Bull, Honda, Audi -- not 3,
                        so the reserved height matches what actually renders below. Measured
                        225-266px per panel across mobile (collapsed) and desktop (open) alike --
                        closer together than assumed, so one value covers both. */}
                    <div className="mb-8 grid gap-4">
                      {[0, 1, 2, 3, 4].map((i) => (
                        <SkeletonCard key={i} className="min-h-[270px]" />
                      ))}
                    </div>
                    {/* Matches SeasonDeploymentChart's own root: desktop-only (`hidden … md:block`),
                        so mobile doesn't reserve height for a chart that never renders there.
                        Measured 1009px desktop. */}
                    <SkeletonCard className="hidden min-h-[1010px] md:block" />
                  </>
                }
              >
                {deploymentPanelItems.length > 0 && (
                  // Full section width (matching the Ranking table above), not the narrower
                  // max-w-5xl WeekendPage uses for its 3-insight hero column: on this denser,
                  // multi-section page a narrower block just left-aligns with dead space beside
                  // it. showSlot stays on: the rank digit is the panels' own ordering (1 = best
                  // package this season), which the kicker's manufacturer name doesn't convey.
                  <div className="mb-8">
                    <div className="grid gap-4">
                      {deploymentPanelItems.map((item, i) => {
                        // ponytail: Mercedes' cyan (#27F4D2) reads as too bright/light for text
                        // at full strength here; every other team's color was confirmed fine as
                        // is, so this is a one-off calibration knob, not a general formula.
                        const teamColor =
                          item.works_team === 'Mercedes'
                            ? `color-mix(in oklch, ${resolveTeamColor(item.works_team)} 92%, var(--color-ink) 8%)`
                            : resolveTeamColor(item.works_team)
                        return (
                        <BlurFade key={item.pu} delay={0.06 * i}>
                          <Insight
                            item={item}
                            collapsible
                            defaultOpen={!isMobile}
                            // Two-tone: the manufacturer name carries the full team color, same
                            // as the rank number (can't be a uniform accent-red once panels are
                            // team-tinted); the customer-team list stays neutral rather than
                            // picking one of several team colors. block sm:inline on the customer
                            // span: forces its own line on mobile (crammed onto one line with a
                            // longer manufacturer name otherwise), stays inline at sm+ as before.
                            // Comma-separated, no bullets -- the color/weight contrast between
                            // the bold manufacturer name and this muted list is separator enough.
                            kicker={
                              <span className="font-semibold" style={{ color: teamColor }}>{item.pu} power</span>
                            }
                            contextLabel={`${year} season deployment`}
                            // Stronger than the 0.09 row-wash precedent (Ranking table, legends):
                            // those are dense stacks of many small rows where a strong tint would
                            // overwhelm; these are five spacious hero panels where the team color
                            // is the whole point, so it can carry more of the surface. The big
                            // rank number in full-strength team color is the second, bolder signal.
                            tintColor={teamColorWithAlpha(item.works_team, 0.09)}
                            accentColor={teamColor}
                          />
                        </BlurFade>
                        )
                      })}
                    </div>
                  </div>
                )}
                <BlurFade delay={0.06 * deploymentPanelItems.length}>
                  <SeasonDeploymentChart scatter={deployment.data?.scatter ?? {}} puGroups={deployment.data?.pu_groups ?? []} />
                </BlurFade>
              </LoadingSwap>
            </section>
          )}
        </>
      )}

      <BackToTopButton />
    </main>
  )
}

function SeasonRedirect() {
  const weekends = useApi<WeekendSummary[]>('/weekends')
  const years = (weekends.data ?? []).map((w) => w.year)

  if (weekends.data && years.length > 0) {
    return <Navigate to={`/season/${Math.max(...years)}`} replace />
  }

  // Nothing at all while the year lookup is in flight. The nav's "Season" link points at bare
  // /season, so this component is on the critical path of every visit, and it always redirects to
  // /season/<latest year> the instant /weekends resolves -- so anything painted here mounts, plays
  // its reveal, and is torn down again a few hundred ms later. That showed up as the header
  // blur-fading in, vanishing to a blank frame, then blur-fading in a second time from SeasonView
  // (visibly a different header: this one has no year badge and no Ranking section below it).
  // Only the terminal states below are worth painting, because those are the ones that never
  // redirect and so are the only ones a reader is left looking at.
  if (weekends.loading) return null

  return (
    <main className="mx-auto max-w-[1312px] px-6 py-16 sm:py-24">
      <BlurFade>
        <div className="mb-6">
          <BackHomeButton />
        </div>
        <div className="flex flex-col gap-3 border-b-2 border-ink pb-3 sm:flex-row sm:items-end sm:justify-between sm:gap-4">
          {/* Split on purpose, matching Weekends' heading: mobile keeps the 0.9x display-ramp size
              (text-[3.375rem]) because the narrower column needs it, while sm+ is back on the raw
              text-7xl it was before the 0.9x pass -- the reduction was only ever wanted on mobile. */}
          <h1 className="font-display text-[3.375rem] leading-[0.95] tracking-tight sm:text-7xl">Season at a glance</h1>
        </div>
        <p className="mt-4 max-w-3xl text-lg leading-relaxed text-muted">
          Every team's season so far, rolled up from the weekend pages.
        </p>
      </BlurFade>

      {weekends.error && <p className="mt-8 text-muted">API offline.</p>}
      {weekends.data && years.length === 0 && <p className="mt-8 text-muted">No seasons ingested yet.</p>}
    </main>
  )
}

export function SeasonPage() {
  const { year } = useParams()
  if (!year) return <SeasonRedirect />
  return <SeasonView year={Number(year)} />
}
