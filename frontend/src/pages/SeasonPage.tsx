import { Navigate, useParams } from 'react-router-dom'
import { BlurFade } from '@/components/BlurFade'
import { SeasonDeploymentChart } from '@/components/SeasonDeploymentChart'
import { SeasonTrendChart } from '@/components/SeasonTrendChart'
import { SectionTitle } from '@/components/SectionTitle'
import { TeamRule } from '@/components/TeamMark'
import { heatBg, rankAsc } from '@/lib/heat'
import { seasonSummary, type Trait } from '@/lib/seasonSummary'
import { teamColorWithAlpha } from '@/lib/teamColors'
import {
  useApi,
  type SeasonConstructorRow,
  type SeasonDeploymentScatter,
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

// Re-anchor a column to its own best: the best (smallest) team shows "best", every other
// team shows its gap to that best. Renders one <span> so "best" reads as the reference.
function gapCells(values: (number | null)[], fmtGap: (d: number) => string): (string | null)[] {
  const present = values.filter((v): v is number => v != null)
  if (present.length === 0) return values.map(() => null)
  const best = Math.min(...present)
  return values.map((v) => (v == null ? null : v === best ? 'best' : fmtGap(v - best)))
}

const renderCell = (text: string | null) =>
  text == null ? '–' : text === 'best' ? <span className="font-semibold text-ink">best</span> : text

// No grid gap: cells touch and use matching horizontal padding instead, so each row's
// border-top reads as one continuous line rather than breaking at every column boundary
// (same recipe as Results.tsx).
const RANK_GRID = 'grid grid-cols-[1.9fr_1fr_1fr_1fr] items-center'
const HEAD = 'border-b border-border px-2 pb-2 text-sm font-semibold text-ink'

function RankingTable({ rows }: { rows: SeasonConstructorRow[] }) {
  const topRanks = rankAsc(rows.map((r) => r.top_speed_deficit_kmh))
  const degRanks = rankAsc(rows.map((r) => r.tyre_deg_s_per_lap))
  const n = rows.length

  // One bare delta per column (no sign, no unit-doubling): the leader reads "leader", the rest
  // their gap to it. Pace shows race pace only; the 60/40 blend still drives the order + shading.
  const paceCells = gapCells(rows.map((r) => r.pace_gap.mean), (d) => `+${d.toFixed(3)}s`)
  const topCells = gapCells(rows.map((r) => r.top_speed_deficit_kmh), (d) => `-${Math.round(d)} km/h`)
  const degCells = gapCells(rows.map((r) => r.tyre_deg_s_per_lap), (d) => `${d.toFixed(3)}s/lap`)

  const cell = (rank: number) => ({ backgroundColor: heatBg(rank, n) })

  return (
    // Same recipe as Results.tsx: the "Team" cell's rank + rule + name + confidence chip can't
    // shrink below its content width, so on a narrow viewport the grid needs its own scroll
    // container instead of forcing the whole page wider.
    <div className="overflow-x-auto">
      <ol className={`${RANK_GRID} min-w-[480px]`}>
        <li className="contents" aria-hidden>
          <span className={HEAD}>Team</span>
          <span className={`${HEAD} text-center`}>Pace</span>
          <span className={`${HEAD} text-center`}>Top speed</span>
          <span className={`${HEAD} text-center`}>Tyre wear</span>
        </li>
        {rows.map((r, i) => {
          const b = i > 0 ? 'border-t border-border' : ''
          // Rank + team merge into one washed pill instead of two separately-washed cells; the
          // metric cells already use heatBg to shade by rank, so they keep their own wash.
          const wash = { backgroundColor: teamColorWithAlpha(r.constructor, 0.09) }
          return (
            <li key={r.constructor} className="contents">
              <span className={`flex items-center gap-2 px-2 py-3 font-medium text-ink ${b}`} style={wash}>
                <span className="num w-5 shrink-0 text-sm text-muted">{r.overall_rank ?? '–'}</span>
                <TeamRule team={r.constructor} />
                {r.constructor}
                <ConfidenceChip confidence={r.confidence} />
              </span>
              <span className={`num px-2 py-3 text-center text-sm text-ink ${b}`} style={cell(r.overall_rank ?? n)}>
                {renderCell(paceCells[i])}
              </span>
              <span className={`num px-2 py-3 text-center text-sm text-ink ${b}`} style={cell(topRanks[i])}>
                {renderCell(topCells[i])}
              </span>
              <span className={`num px-2 py-3 text-center text-sm text-ink ${b}`} style={cell(degRanks[i])}>
                {renderCell(degCells[i])}
              </span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}

// A team's car is the subject; strengths and weaknesses are its supporting detail, not table
// columns of equal weight. Each team gets a real heading (name at display size, own row) with
// its two trait lists indented underneath, so the list reads as a sequence of short editorial
// entries instead of a spreadsheet.
function TraitList({ traits, kind }: { traits: Trait[]; kind: 'up' | 'down' }) {
  if (traits.length === 0) {
    // A genuinely poor car legitimately has zero real strengths (seasonSummary.ts won't dress
    // one up); say so instead of leaving the cell blank, which reads as broken rather than honest.
    return <p className="text-sm text-muted">{kind === 'up' ? 'No standout strength yet' : '–'}</p>
  }
  const mark = kind === 'up' ? '▲' : '▼'
  const markColor = kind === 'up' ? 'text-accent' : 'text-muted'
  return (
    <ul className="flex flex-col gap-2">
      {traits.map((trait, i) => (
        <li key={i} className="flex items-center gap-3 text-sm">
          <span className={`shrink-0 text-[0.7em] ${markColor}`} aria-hidden>
            {mark}
          </span>
          <span className="min-w-0 flex-1 text-ink">
            {trait.text}
            {trait.detail && <span className="num ml-1.5 text-muted">{trait.detail}</span>}
          </span>
        </li>
      ))}
    </ul>
  )
}

function FormGuide({ rows }: { rows: SeasonConstructorRow[] }) {
  const summary = seasonSummary(rows)
  return (
    <div className="glass rounded-[--radius-panel] p-6 sm:p-8">
      <ul>
        {rows.map((r, i) => {
          const s = summary[r.constructor]
          return (
            <li key={r.constructor} className={`py-7 ${i > 0 ? 'border-t border-border' : ''}`}>
              <div
                className="inline-flex items-center gap-2.5 rounded-[--radius-panel] px-3 py-1.5"
                style={{ backgroundColor: teamColorWithAlpha(r.constructor, 0.09) }}
              >
                <TeamRule team={r.constructor} className="h-[1.1em]" />
                <h3 className="font-display text-xl font-semibold tracking-tight text-ink sm:text-2xl">
                  {r.constructor}
                </h3>
                <ConfidenceChip confidence={r.confidence} />
              </div>
              <div className="mt-4 grid gap-x-8 gap-y-4 sm:grid-cols-2 sm:pl-[22px]">
                <div>
                  <p className="kicker mb-2.5 text-accent">Strengths</p>
                  <TraitList traits={s.strengths} kind="up" />
                </div>
                <div>
                  <p className="kicker mb-2.5 text-muted">Weaknesses</p>
                  <TraitList traits={s.weaknesses} kind="down" />
                </div>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function SeasonView({ year }: { year: number }) {
  const season = useApi<SeasonSnapshot>(`/season/${year}`)
  const deployment = useApi<SeasonDeploymentScatter>(`/season/${year}/deployment`)
  const rows = season.data?.constructors ?? []

  return (
    <main className="mx-auto max-w-[1312px] px-6 py-16 sm:py-24">
      <BlurFade>
        {/* Same heading-row shape as Weekends.tsx (h1 + kicker badge, one border-b-2 divider)
            so the two pages' titles land at the same position and size when switching between
            the WEEKENDS/SEASON nav links, instead of the season year stacking above as its own
            line and pushing the heading down. */}
        <div className="flex flex-col gap-1 border-b-2 border-ink pb-3 sm:flex-row sm:items-end sm:justify-between sm:gap-4">
          <h1 className="font-display text-6xl leading-[0.95] tracking-tight sm:text-7xl">Season at a glance</h1>
          <span className="kicker whitespace-nowrap text-muted">{year} season</span>
        </div>
        <p className="mt-4 max-w-3xl text-lg leading-relaxed text-muted">
          Every team's season so far, rolled up from the weekend pages.
        </p>
      </BlurFade>

      <section className="mt-16">
        <SectionTitle>Ranking</SectionTitle>
        {season.loading && <p className="text-sm text-muted">Loading...</p>}
        {season.error && <p className="text-sm text-muted">No season data for {year}.</p>}
        {rows.length > 0 && (
          <BlurFade>
            <div className="glass rounded-[--radius-panel] p-6">
              <RankingTable rows={rows} />
              <p className="mt-4 text-xs text-muted">
                Each column is anchored to the season's best team: it shows "best" and every other
                team its gap to it. Pace is the 60/40 race and qualifying blend that drives the
                order. Tyre wear is measured on the compound the field ran most, so it reflects the car and
                not its tyre choice. Cells shade toward the accent as a team ranks higher on that metric. A
                "partial data" or "low data" tag marks a team seen in too few rounds to read at full confidence.
              </p>
            </div>
          </BlurFade>
        )}
      </section>

      {rows.length > 0 && (
        <>
          <section className="mt-20">
            <SectionTitle>Gap by round</SectionTitle>
            <BlurFade>
              <SeasonTrendChart rows={rows} rounds={season.data!.rounds} />
            </BlurFade>
          </section>

          <section className="mt-20">
            <SectionTitle>Where each car wins and loses</SectionTitle>
            <BlurFade>
              <FormGuide rows={rows} />
            </BlurFade>
            <p className="mt-4 text-xs text-muted">
              Up to three real strengths and three weaknesses per car, each ranked against every other team
              with the real season-average figure. Even a front-runner shows where it gives a little away.
            </p>
          </section>

          {deployment.data && Object.keys(deployment.data).length > 0 && (
            <section className="mt-20">
              <SectionTitle>Deployment</SectionTitle>
              <BlurFade>
                <SeasonDeploymentChart scatter={deployment.data} />
              </BlurFade>
            </section>
          )}
        </>
      )}
    </main>
  )
}

function SeasonRedirect() {
  const weekends = useApi<WeekendSummary[]>('/weekends')
  if (weekends.loading) {
    return (
      <main className="py-16">
        <div className="mx-auto max-w-5xl px-6 text-sm text-muted">Loading...</div>
      </main>
    )
  }
  if (weekends.error) {
    return (
      <main className="py-16">
        <div className="mx-auto max-w-5xl px-6 text-sm text-muted">API offline.</div>
      </main>
    )
  }
  const years = (weekends.data ?? []).map((w) => w.year)
  if (years.length === 0) {
    return (
      <main className="py-16">
        <div className="mx-auto max-w-5xl px-6 text-sm text-muted">No seasons ingested yet.</div>
      </main>
    )
  }
  return <Navigate to={`/season/${Math.max(...years)}`} replace />
}

export function SeasonPage() {
  const { year } = useParams()
  if (!year) return <SeasonRedirect />
  return <SeasonView year={Number(year)} />
}
