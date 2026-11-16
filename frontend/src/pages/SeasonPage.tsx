import { Navigate, useParams } from 'react-router-dom'
import { BackHomeButton } from '@/components/BackHomeButton'
import { BackToTopButton } from '@/components/BackToTopButton'
import { BlurFade } from '@/components/BlurFade'
import { Insight } from '@/components/Insight'
import { LoadingSwap } from '@/components/LoadingSwap'
import { SeasonDeploymentChart } from '@/components/SeasonDeploymentChart'
import { SeasonTrendChart } from '@/components/SeasonTrendChart'
import { SectionNav, type NavSection } from '@/components/SectionNav'
import { CollapsibleSection } from '@/components/SectionTitle'
import { SeasonStartSection } from '@/components/SeasonStartChart'
import { SkeletonCard } from '@/components/Skeleton'
import { RankingTable, type RankingRow } from '@/components/RankingTable'
import { SectionLede, SubTitle } from '@/components/SectionLede'
import { deploymentInsights } from '@/lib/deploymentInsights'
import { resolveTeamColor, teamColorWithAlpha } from '@/lib/teamColors'
import { useIsMobile } from '@/lib/useIsMobile'
import {
  useApi,
  type SeasonDeployment,
  type SeasonDeploymentInsightItem,
  type SeasonStartData,
  type SeasonSnapshot,
  type WeekendSummary,
} from '@/lib/api'

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
  const raceStart = useApi<SeasonStartData>(`/season/${year}/race-start`)
  const rows = season.data?.constructors ?? []
  // The ranking's own blend (overall_gap_s, the same one that sets overall_rank); the arrow is the cumulative
  // form, which is that blend computed per round.
  const paceRankingRows: RankingRow[] = rows.map((r) => ({
    key: r.constructor,
    colorTeam: r.constructor,
    label: r.constructor,
    rank: r.overall_rank,
    gap: r.overall_gap_s,
    formPlaces: r.form?.cumulative?.form_places ?? null,
    confidence: r.confidence,
  }))
  const hasRaceStart = !!raceStart.data && Object.keys(raceStart.data.views).length > 0
  const hasDeployment = !!deployment.data && Object.keys(deployment.data.scatter).length > 0
  const deploymentPanelItems = deployment.data ? deploymentPanels(deployment.data) : []
  const deploymentMaxGap = Math.max(0, ...(deployment.data?.ranking ?? []).map((r) => r.gap ?? 0))
  // Quarter m/s² ticks, since the gaps are a fraction of an m/s².
  const deploymentTicks = Array.from({ length: Math.floor(deploymentMaxGap * 4) + 1 }, (_, i) => i / 4)
  const deploymentRankingRows: RankingRow[] = (deployment.data?.ranking ?? []).map((r) => ({
    key: r.pu,
    colorTeam: r.works_team,
    label: r.pu,
    rank: r.rank,
    gap: r.gap,
    formPlaces: r.form_places,
  }))

  const navSections: NavSection[] = [
    rows.length > 0 ? { id: 'ranking', label: 'Pace ranking' } : null,
    rows.length > 0 && hasRaceStart ? { id: 'race-starts', label: 'Race start ranking' } : null,
    rows.length > 0 && hasDeployment ? { id: 'deployment', label: 'Deployment ranking' } : null,
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
        <CollapsibleSection title="Pace ranking" delay={0.08}>
          {/* Lede first: what is ranked and what the arrow means is read BEFORE the table. LoadingSwap
              reserves the real footprint while loading (heights measured from the rendered panels). Its
              breakpoint is sm: (640px), matching RankingTable's own column-width swap. */}
          <SectionLede>
            Teams ranked on a 60/40 blend of race and qualifying pace, with recent rounds counting a little
            more. The leader shows "leader"; every other team shows how far behind it is, in seconds a lap.
            The arrow is places gained or lost on recent form versus the whole season.
          </SectionLede>
          <LoadingSwap
            loading={season.loading}
            delay={0.08}
            placeholder={<SkeletonCard className="min-h-[880px] sm:min-h-[681px]" />}
          >
            {season.error ? (
              <p className="text-sm text-muted">No season data for {year}.</p>
            ) : rows.length > 0 ? (
              <div className="glass rounded-panel p-6">
                <RankingTable
                  rows={paceRankingRows}
                  fmtGap={(d) => `+${d.toFixed(3)}s`}
                  tickLabel={(t) => (t === 0 ? '0' : `+${t}s`)}
                />
                <p className="mt-4 text-sm text-muted">
                  Each bar is that same blend rescaled to seconds, so the order and the bars can never disagree.
                  A "partial data" or "low data" tag marks a team seen in too few rounds to read at full confidence.
                </p>
              </div>
            ) : null}
          </LoadingSwap>

          {/* Always rendered (not gated on rows.length) so the swap stays in place instead of popping in. */}
          {(season.loading || rows.length > 0) && (
            <div id="gap-by-round" className="scroll-mt-24">
              <SubTitle lede="The same ranking round by round: how far each team was from the round's fastest. A line near the top ran at the front; a line dropping away lost ground.">
                Gap by round
              </SubTitle>
              {/* Measured on the real card: 967px at 1280, 1291px at 390 (the legend stacks). */}
              <LoadingSwap
                loading={season.loading}
                delay={0.16}
                placeholder={<SkeletonCard className="min-h-[1291px] md:min-h-[967px]" />}
              >
                <SeasonTrendChart rows={rows} rounds={season.data?.rounds ?? []} />
              </LoadingSwap>
            </div>
          )}
        </CollapsibleSection>
      </section>

      {(season.loading || rows.length > 0) && (
        <>
          {(raceStart.loading || hasRaceStart) && (
            <section id="race-starts" className="mt-20 scroll-mt-24">
              <CollapsibleSection title="Race start ranking" delay={0.24}>
                <LoadingSwap
                  loading={raceStart.loading}
                  delay={0.24}
                  // The whole section body (lede, tabs, ranking table, subheading, chart), measured: 1986px at 1280, 2479px at 390.
                  placeholder={<SkeletonCard className="min-h-[2479px] md:min-h-[1986px]" />}
                >
                  {raceStart.data && <SeasonStartSection data={raceStart.data} />}
                </LoadingSwap>
              </CollapsibleSection>
            </section>
          )}

          {(deployment.loading || hasDeployment) && (
            <section id="deployment" className="mt-20 scroll-mt-24">
              <CollapsibleSection title="Deployment ranking" delay={0.32}>
                <LoadingSwap
                  loading={deployment.loading}
                  delay={0.32}
                  placeholder={
                    <>
                      {/* 5 placeholders, one per PU_GROUPS entry (backend/telogify/analysis/
                          season_deployment.py) -- Mercedes, Ferrari, Red Bull, Honda, Audi -- not 3,
                          so the reserved height matches what actually renders below. Measured
                          225-266px per panel across mobile (collapsed) and desktop (open) alike --
                          closer together than assumed, so one value covers both. */}
                      {/* Lede + ranking table + the "Deployment curve" subheading, measured as the difference between
                          the old placeholder total and the real body: 3073px at 1280, 2233px at 390 in all. */}
                      <SkeletonCard className="mb-8 min-h-[755px] md:min-h-[585px]" />
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
                  <SectionLede>
                    Power units ranked on how hard they accelerate at full throttle, averaging the 250 to 290 km/h
                    band and everything faster, pooled across the season. The bar is the gap to the best package in
                    m/s². The arrow is places gained or lost on recent rounds versus the whole season.
                  </SectionLede>
                  {deploymentRankingRows.length > 0 && (
                    <div className="glass mb-8 rounded-panel p-6">
                      <RankingTable
                        rows={deploymentRankingRows}
                        fmtGap={(d) => `+${d.toFixed(2)}`}
                        ticks={deploymentTicks}
                        tickLabel={(t) => (t === 0 ? '0' : `+${t}`)}
                        nameHeader="Power unit"
                      />
                      <p className="mt-4 text-sm text-muted">
                        Figures are m/s² behind the best package. Each round is compared with that round&apos;s best,
                        so the arrow is not thrown by tracks where the top speed band was never reached.
                      </p>
                    </div>
                  )}
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
                  <SubTitle lede="Median acceleration at each speed, one line per team or power unit. A line dropping toward zero at high speed is consistent with electrical deployment running out (clipping); lower acceleration at low-to-mid speed is consistent with energy being harvested there. Hover a dot for its speed band and sample count.">
                    Deployment curve
                  </SubTitle>
                  <BlurFade delay={0.06 * deploymentPanelItems.length}>
                    <SeasonDeploymentChart
                      scatter={deployment.data?.scatter ?? {}}
                      puGroups={deployment.data?.pu_groups ?? []}
                      ranking={deployment.data?.ranking}
                    />
                  </BlurFade>
                </LoadingSwap>
              </CollapsibleSection>
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
    return <Navigate to={`/trends/${Math.max(...years)}`} replace />
  }

  // Nothing at all while the year lookup is in flight. The nav's "Trends" link points at bare
  // /trends, so this component is on the critical path of every visit, and it always redirects to
  // /trends/<latest year> the instant /weekends resolves -- so anything painted here mounts, plays
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
