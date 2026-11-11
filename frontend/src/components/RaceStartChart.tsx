import { useMemo, useState } from 'react'
import { m, useReducedMotion } from 'framer-motion'
import { ChartTabs } from '@/components/ChartTabs'
import { TeamRule } from '@/components/TeamMark'
import { Tooltip } from '@/components/Tooltip'
import { driverName } from '@/lib/drivers'
import {
  aggregateRows,
  axisMax,
  fmtSeconds,
  rowTotal,
  secondTicks,
  segmentFractions,
  sortRows,
  type StartSort,
  type StartView,
} from '@/lib/raceStart'
import { teamColorWithAlpha, resolveTeamColor, teamShortName } from '@/lib/teamColors'
import type { RaceStartData } from '@/lib/api'

// Column widths shared by the header axis and every row so tick marks sit directly above the
// bars. Narrower below sm: the driver column drops the full name and keeps the 3-letter code.
const RANK_W = 'w-5 sm:w-7'
const DRIVER_W = 'w-[3.25rem] sm:w-52'
// Team and power-unit names are longer than a 3-letter code, so phones get a wider name column.
const GROUP_W = 'w-[5rem] sm:w-52'
const FIGURE_W = 'w-[4.25rem] sm:w-[5.5rem]'
const SPEED_W = 'w-[5.5rem]'

// What each row needs, whatever the view: a driver, a team or a power unit.
interface LadderRow {
  key: string
  name: string // wide screens
  short: string // phones
  colorTeam: string | null
  n: number | null // cars pooled (group views only)
  compound: string | null
  t_0_100_s: number
  t_100_200_s: number | null
  t_0_200_s: number | null
  v_75m_kmh: number | null
}

export function RaceStartChart({ data }: { data: RaceStartData }) {
  const reduce = useReducedMotion()
  const [view, setView] = useState<StartView>('drivers')
  const [sortBy, setSortBy] = useState<StartSort>('total')
  const toKmh = data.to_kmh === 100 ? 100 : 200
  const distance = data.speed_distance_m ?? 75
  const puGroups = data.pu_groups ?? []
  // A 100-only round has just one leg to sort on, so the sort control is hidden and total applies.
  const canSort = toKmh === 200
  const effectiveSort: StartSort = canSort ? sortBy : 'total'

  const rows: LadderRow[] = useMemo(() => {
    const built = ((): LadderRow[] => {
    if (view === 'drivers') {
      return data.rows.map((r) => ({
        key: r.driver,
        name: driverName(r.driver),
        short: r.driver,
        colorTeam: r.constructor,
        n: null,
        compound: r.compound,
        t_0_100_s: r.t_0_100_s,
        t_100_200_s: r.t_100_200_s,
        t_0_200_s: r.t_0_200_s,
        v_75m_kmh: r.v_75m_kmh,
      }))
    }
    return aggregateRows(data.rows, view, puGroups, toKmh).map((g) => ({
      key: g.key,
      name: g.label,
      short: view === 'teams' ? teamShortName(g.label) : g.label,
      colorTeam: g.colorTeam,
      n: g.n,
      compound: null,
      t_0_100_s: g.t_0_100_s,
      t_100_200_s: g.t_100_200_s,
      t_0_200_s: g.t_0_200_s,
      v_75m_kmh: g.v_75m_kmh,
    }))
    })()
    return sortRows(built, effectiveSort, toKmh)
  }, [data.rows, view, puGroups, toKmh, effectiveSort])

  const grouped = view !== 'drivers'
  const hasSpeed = rows.some((r) => r.v_75m_kmh != null)
  const max = axisMax(rows, toKmh)
  const ticks = secondTicks(max)
  const nameW = grouped ? GROUP_W : DRIVER_W

  return (
    <div className="glass w-full rounded-panel p-5">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-[2.025rem] font-semibold tracking-tight sm:text-[2.7rem]">
          Race start
        </h2>
        <div className="flex flex-col items-start gap-1 sm:items-end">
          <ChartTabs
            ariaLabel="Group race starts by driver, team or power unit"
            active={view}
            onChange={setView}
            tabs={[
              { value: 'drivers', label: 'Drivers', hint: 'Every car' },
              { value: 'teams', label: 'Teams', hint: 'Median of each team’s cars' },
              ...(puGroups.length > 0
                ? [{ value: 'pu' as const, label: 'Power units', hint: 'Median of every car a power unit supplies' }]
                : []),
            ]}
          />
          {canSort && (
            <ChartTabs
              ariaLabel="Sort race starts by"
              active={sortBy}
              onChange={setSortBy}
              tabs={[
                { value: 'total', label: 'Full', hint: 'Fastest time from the start to 200 km/h' },
                { value: 'first', label: 'First phase', hint: 'Fastest time from the start to 100 km/h' },
                { value: 'second', label: 'Second phase', hint: 'Fastest time from 100 to 200 km/h' },
              ]}
            />
          )}
        </div>
      </div>
      <p className="mb-4 text-sm text-muted">
        {toKmh === 200 ? 'Seconds from the start to 100 and 200 km/h' : 'Seconds from the start to 100 km/h'}
        {hasSpeed ? `, and speed after ${distance} metres` : ''}.{' '}
        {canSort
          ? `Ranked by the ${sortBy === 'total' ? 'full run' : sortBy === 'first' ? 'first phase' : 'second phase'}, fastest first.`
          : 'Fastest first.'}
        {grouped ? (
          ` Each row is the median of ${view === 'teams' ? 'its team’s' : 'its power unit’s'} cars.`
        ) : (
          /* The tyre letter only shows from sm up (no room beside the 3-letter code on a phone), so
             the caption only mentions it there too. */
          <span className="hidden sm:inline"> The letter after each name is the tyre they started on.</span>
        )}
      </p>

      <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-muted">
        <span className="inline-flex items-center gap-2">
          <span aria-hidden className="h-2.5 w-5 rounded-[1px] bg-ink" />
          {toKmh === 200 ? 'First phase: 0 to 100 km/h' : '0 to 100 km/h'}
        </span>
        {toKmh === 200 && (
          <span className="inline-flex items-center gap-2">
            <span aria-hidden className="h-2.5 w-5 rounded-[1px] bg-ink/45" />
            Second phase: 100 to 200 km/h
          </span>
        )}
      </div>

      {/* Axis ticks line up with the bar track below; hidden on phones where the per-row figure
          already carries the exact time and the track is too narrow for tick labels to breathe. */}
      <div className="hidden items-center gap-3 border-b border-border pb-2 sm:flex">
        <span className={`${RANK_W} shrink-0`} aria-hidden />
        <span className={`${nameW} shrink-0`} aria-hidden />
        <span className="relative h-4 flex-1" aria-hidden>
          {ticks.map((t, i) => (
            <span
              key={t}
              className="absolute top-0 whitespace-nowrap text-xs text-muted"
              style={{
                left: `${(t / (max || 1)) * 100}%`,
                transform: i === 0 ? 'translateX(0)' : 'translateX(-50%)',
              }}
            >
              {t === 0 ? '0' : `${t}s`}
            </span>
          ))}
        </span>
        <span className={`${FIGURE_W} shrink-0`} aria-hidden />
        {hasSpeed && (
          <span className={`${SPEED_W} shrink-0 text-right text-xs text-muted`}>after {distance} m</span>
        )}
      </div>

      <ol>
        {rows.map((r, i) => {
          const { first, second } = segmentFractions(r, max)
          const delay = reduce ? 0 : i * 0.03
          const color = resolveTeamColor(r.colorTeam)
          const speed = r.v_75m_kmh != null ? `${Math.round(r.v_75m_kmh)} km/h` : null
          return (
            <li
              key={r.key}
              className={`flex items-center gap-2 py-2.5 sm:gap-3 ${i > 0 ? 'border-t border-border' : ''}`}
            >
              <span className={`num ${RANK_W} shrink-0 text-sm text-muted`}>{i + 1}</span>
              <span className={`${nameW} flex min-w-0 shrink-0 items-center gap-2`}>
                <TeamRule team={r.colorTeam} />
                <span className={`truncate text-ink ${grouped ? 'text-sm sm:text-base' : ''}`}>
                  {/* Full name on wider screens, the short form (3-letter code / short team name) on phones. */}
                  <span className="font-display font-semibold sm:hidden">{r.short}</span>
                  <span className="hidden font-display font-semibold sm:inline">{r.name}</span>
                </span>
                {r.n != null && (
                  <span className="hidden shrink-0 text-xs text-muted sm:inline">
                    {r.n} {r.n === 1 ? 'car' : 'cars'}
                  </span>
                )}
                {r.compound && (
                  <span
                    className="hidden shrink-0 text-xs text-muted sm:inline"
                    title="Starting tyre"
                    aria-label={`Started on ${r.compound}`}
                  >
                    {r.compound}
                  </span>
                )}
              </span>
              {/* Zero rule marks the shared baseline as one continuous line down the column; the
                  segments grow from it in absolute seconds. Each segment is hoverable (tap on a
                  phone) and says what it covers; the same numbers are in the sr-only text. */}
              <span className="relative h-[1.375rem] flex-1 border-l-[1.5px] border-ink/25">
                <span className="sr-only">
                  {`0 to 100 km/h: ${fmtSeconds(r.t_0_100_s)} s`}
                  {r.t_100_200_s != null && `. 100 to 200 km/h: ${fmtSeconds(r.t_100_200_s)} s`}
                </span>
                <span className="absolute inset-y-0 left-0" style={{ width: `${first * 100}%` }}>
                  <Tooltip
                    className="relative flex h-full w-full"
                    label={`0 to 100 km/h: ${fmtSeconds(r.t_0_100_s)} s`}
                  >
                    <m.span
                      className="block h-full w-full rounded-l-[1px]"
                      style={{ backgroundColor: color, transformOrigin: 'left' }}
                      initial={reduce ? false : { scaleX: 0 }}
                      whileInView={{ scaleX: 1 }}
                      viewport={{ once: true }}
                      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1], delay }}
                    />
                  </Tooltip>
                </span>
                {second > 0 && r.t_100_200_s != null && (
                  <span
                    className="absolute inset-y-0"
                    style={{ left: `${first * 100}%`, width: `${second * 100}%` }}
                  >
                    <Tooltip
                      className="relative flex h-full w-full"
                      label={`100 to 200 km/h: ${fmtSeconds(r.t_100_200_s)} s`}
                    >
                      <m.span
                        className="block h-full w-full rounded-r-[1px]"
                        style={{ backgroundColor: teamColorWithAlpha(r.colorTeam, 0.5), transformOrigin: 'left' }}
                        initial={reduce ? false : { scaleX: 0 }}
                        whileInView={{ scaleX: 1 }}
                        viewport={{ once: true }}
                        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1], delay: delay + 0.05 }}
                      />
                    </Tooltip>
                  </span>
                )}
              </span>
              <span className={`${FIGURE_W} shrink-0 text-right leading-tight`}>
                <span className="num block text-sm font-semibold text-ink">
                  {fmtSeconds(rowTotal(r, toKmh))}s
                </span>
                {/* Phones only: the one extra number that fits is the km/h figure; on wider screens
                    it has its own column. */}
                {speed && <span className="num block whitespace-nowrap text-xs text-muted sm:hidden">{speed}</span>}
              </span>
              {hasSpeed && (
                <span className={`num hidden ${SPEED_W} shrink-0 text-right text-sm text-ink sm:block`}>
                  {speed ?? <span className="text-muted">-</span>}
                </span>
              )}
            </li>
          )
        })}
      </ol>

      <p className="mt-4 text-sm text-muted">
        Times run from one shared instant for the whole field: when the median car left the grid. A
        slower reaction than that costs time, a quicker one gains it.
        {hasSpeed &&
          ` Speed after ${distance} metres is measured from each car's own launch, so it leaves
          reaction out and every car is compared over the same distance whatever its grid slot.`}{' '}
        Taken from lap one speed traces.{' '}
        {toKmh === 100 && 'Too few cars reach 200 km/h before the first braking zone here, so only 0 to 100 is shown. '}
        Pit-lane starters, and cars that lifted before the distance was covered or never reached the
        speed, are left out. Times past about 6 seconds can include lifting behind traffic.
        {view === 'pu' &&
          ' A power unit pools every team it supplied, so customer cars differ in chassis, grid slot and traffic: a gap is not purely the engine.'}
        {grouped && ' Teams and power units are ranked on the median of their cars, so a few cars can move a row.'}
      </p>
    </div>
  )
}
