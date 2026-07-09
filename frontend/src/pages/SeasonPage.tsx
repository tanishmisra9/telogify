import { Navigate, useParams } from 'react-router-dom'
import { BlurFade } from '@/components/BlurFade'
import { SeasonDeploymentChart } from '@/components/SeasonDeploymentChart'
import { SeasonTrendChart } from '@/components/SeasonTrendChart'
import { SectionTitle } from '@/components/SectionTitle'
import { TeamRule } from '@/components/TeamMark'
import { heatBg, rankAsc } from '@/lib/heat'
import { seasonSummary, type Trait } from '@/lib/seasonSummary'
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
    <span className="whitespace-nowrap rounded-full border border-border px-2 py-0.5 text-xs text-muted">
      {CONF_LABEL[confidence] ?? confidence}
    </span>
  )
}

// Re-anchor a column to its own leader: the best (smallest) team shows "leader", every other
// team shows its gap to that leader. Renders one <span> so the leader reads as the reference.
function gapCells(values: (number | null)[], fmtGap: (d: number) => string): (string | null)[] {
  const present = values.filter((v): v is number => v != null)
  if (present.length === 0) return values.map(() => null)
  const best = Math.min(...present)
  return values.map((v) => (v == null ? null : v === best ? 'leader' : fmtGap(v - best)))
}

const renderCell = (text: string | null) =>
  text == null ? '–' : text === 'leader' ? <span className="text-ink">leader</span> : text

const RANK_GRID = 'grid grid-cols-[2rem_1.6fr_1.3fr_1fr_1fr] items-center gap-x-4'
const HEAD = 'border-b border-border pb-2 text-sm font-semibold text-ink'

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
    <ol className={RANK_GRID}>
      <li className="contents" aria-hidden>
        <span className={HEAD} />
        <span className={HEAD}>Team</span>
        <span className={`${HEAD} text-center`}>Pace</span>
        <span className={`${HEAD} text-center`}>Top speed</span>
        <span className={`${HEAD} text-center`}>Tyre wear</span>
      </li>
      {rows.map((r, i) => {
        const b = i > 0 ? 'border-t border-border' : ''
        return (
          <li key={r.constructor} className="contents">
            <span className={`num py-3 text-sm text-muted ${b}`}>{r.overall_rank ?? '–'}</span>
            <span className={`flex items-center gap-2 py-3 font-medium text-ink ${b}`}>
              <TeamRule team={r.constructor} />
              {r.constructor}
              <ConfidenceChip confidence={r.confidence} />
            </span>
            <span className={`num py-3 text-center text-sm text-ink ${b}`} style={cell(r.overall_rank ?? n)}>
              {renderCell(paceCells[i])}
            </span>
            <span className={`num py-3 text-center text-sm text-ink ${b}`} style={cell(topRanks[i])}>
              {renderCell(topCells[i])}
            </span>
            <span className={`num py-3 text-center text-sm text-ink ${b}`} style={cell(degRanks[i])}>
              {renderCell(degCells[i])}
            </span>
          </li>
        )
      })}
    </ol>
  )
}

// What the car does best in the field, and where it falls short, up to 3 each. Plain typographic
// rows (no colored blocks), aligned to the ranking table's rhythm. A small up mark in the accent
// flags each strength, a down mark in muted flags each weakness.
const FORM_GRID = 'grid grid-cols-1 gap-x-8 gap-y-1 sm:grid-cols-[1.1fr_1.4fr_1.4fr]'

function TraitList({ traits, kind }: { traits: Trait[]; kind: 'up' | 'down' }) {
  if (traits.length === 0) return null
  const mark = kind === 'up' ? '▲' : '▼'
  const markColor = kind === 'up' ? 'text-accent' : 'text-muted'
  return (
    <ul className="flex flex-col gap-1">
      {traits.map((trait, i) => (
        <li key={i} className="flex items-baseline gap-2 text-sm">
          <span className={`text-[0.7em] ${markColor}`} aria-hidden>
            {mark}
          </span>
          <span className="text-ink">
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
    <div className="glass rounded-[--radius-panel] p-6">
      <ul className={FORM_GRID}>
        <li className="contents" aria-hidden>
          <span className={`${HEAD} hidden sm:block`}>Team</span>
          <span className={`${HEAD} hidden sm:block`}>Strengths</span>
          <span className={`${HEAD} hidden sm:block`}>Weaknesses</span>
        </li>
        {rows.map((r) => {
          const s = summary[r.constructor]
          return (
            <li
              key={r.constructor}
              className="contents [&>*]:border-border sm:[&>*]:border-t sm:[&>*]:py-3.5"
            >
              <span className="flex items-center gap-2 pt-5 font-medium text-ink sm:pt-3.5">
                <TeamRule team={r.constructor} />
                {r.constructor}
                <ConfidenceChip confidence={r.confidence} />
              </span>
              <span className="pt-1.5 sm:pt-3.5">
                <TraitList traits={s.strengths} kind="up" />
              </span>
              <span className="pb-1 pt-1.5 sm:pt-3.5">
                <TraitList traits={s.weaknesses} kind="down" />
              </span>
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
    <main className="mx-auto max-w-[1312px] px-6 py-16">
      <BlurFade>
        <p className="kicker text-accent">{year} season</p>
        <h1 className="mt-3 font-display text-6xl leading-[0.95] tracking-tight sm:text-8xl">Season Snapshot</h1>
        <p className="mt-4 max-w-3xl text-lg leading-relaxed text-muted">
          Every team's season so far, rolled up from the weekend pages. The ranking blends race pace and
          one-lap qualifying pace (weighted 60/40); the Gap by round chart tracks how each car's deficit
          shifted from race to race.
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
                Each column is anchored to the season's best team: the leader shows "leader" and every other
                team its gap to that leader. Pace is the 60/40 race and qualifying blend that drives the
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
