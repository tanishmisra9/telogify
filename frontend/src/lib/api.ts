import { useEffect, useState } from 'react'

const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export interface WeekendSummary {
  id: number
  year: number
  round: number
  event_name: string
  circuit_name: string
  country: string
}

export interface InsightItem {
  slot: number
  header: string
  explanation_web: string
}

// Strongest insight of the most recent analysed weekend (landing live-insight block).
export interface LatestInsight extends InsightItem {
  year: number
  round: number
  event_name: string
}

// Next upcoming race for the landing countdown; null when the season is over / FastF1 is down.
export interface NextRace {
  event_name: string
  round: number
  date_utc: string
  country?: string
  location?: string
}

export interface BoxStats {
  mean: number
  median: number
  q1: number
  q3: number
  whisker_low: number
  whisker_high: number
  outliers: number[]
  n_laps: number
  compounds: string[]
  pace_ceiling: number
}

export interface PaceRow {
  id: string
  label: string
  team: string | null
  gap_to_fastest_s: number
  stats: BoxStats
}

export interface PaceData {
  drivers: PaceRow[]
  constructors: PaceRow[]
  stop_counts: Record<string, number>
  stop_count_spread: number
  rank_metric?: 'mean' | 'median'
  excludes_lap_1?: boolean
}

export interface ResultRow {
  position: number | null
  driver: string
  constructor: string | null
  gap_label: string
  points: number
  strategy: string
}

export interface SessionInfo {
  session_type: string
  status: string | null
}

export interface SectorDominanceRow {
  sector: number
  constructor: string | null
  best_time_s: number
  margin_s: number | null
}

export interface SectorBestRow {
  driver: string
  constructor: string | null
  sector: number
  best_time_s: number
  session_type: string
}

export interface SectorsData {
  indicative: boolean
  drivers: SectorBestRow[]
  dominance: SectorDominanceRow[]
}

export interface TopSpeedRow {
  driver: string
  constructor: string | null
  max_speed_kmh: number
  max_speed_mph: number
  session_type: string
}

export interface TopSpeedsData {
  indicative: boolean
  drivers: TopSpeedRow[]
}

export type DragLabel = 'efficient, low drag' | 'draggy, high-downforce' | 'lacks efficiency' | 'balanced'

export interface CarCharacterRow {
  constructor: string
  driver: string
  lap_time_s: number
  top_speed_kmh: number
  min_speed_kmh: number
  full_throttle_pct: number
  fastest_corner_kmh: number | null
  drag_label: DragLabel
  is_top_speed_leader: boolean
  is_corner_speed_leader: boolean
  is_grip_leader: boolean
}

export interface QualiCharacterData {
  session_type: string | null
  rows: CarCharacterRow[]
  fastest_corner_number: number | null
  sector_dominance: SectorDominanceRow[]
}

export interface QualiTraceDriver {
  driver: string
  constructor: string | null
  lap_time_s: number | null
  is_pole: boolean
  speed_kmh: number[]
  throttle_pct: number[]
  delta_s: number[]
}

export interface QualiTraceCorner {
  number: number
  distance_m: number
}

export interface QualiTraceData {
  session_type: string | null
  grid_m: number[]
  corners: QualiTraceCorner[]
  drivers: QualiTraceDriver[]
}

export interface DegradationFit {
  constructor: string
  compound: string
  slope_s_per_lap: number
  intercept_s: number
  cost_at_reference_s: number
  n_laps: number
  flagged: boolean
}

export interface DegradationPoint {
  constructor: string
  compound: string
  tyre_age: number
  lap_time_s: number
}

export interface DegradationData {
  reference_age_laps: number | null
  points: DegradationPoint[]
  fits: DegradationFit[]
}

export interface MetricAgg {
  mean: number | null
  spread: number | null
  n: number
}

export interface TrendPoint {
  round: number
  value: number
}

export interface SeasonConstructorRow {
  constructor: string
  overall_rank: number | null
  pace_gap: MetricAgg
  quali_gap_pct: MetricAgg
  top_speed_deficit_kmh: number | null
  top_speed_deficit_mph: number | null
  sector_dominance_count: number
  tyre_deg_s_per_lap: number | null
  trend: { pace: TrendPoint[]; quali: TrendPoint[]; cumulative: TrendPoint[] }
  confidence: 'low' | 'med' | 'high'
}

export interface SeasonRound {
  round: number
  event_name: string
}

export interface SeasonSnapshot {
  year: number
  rounds: SeasonRound[]
  constructors: SeasonConstructorRow[]
}

/** {constructor: [[speed_kmh, longitudinal_accel_ms2], ...]}, pooled across the season. */
export type SeasonDeploymentScatter = Record<string, [number, number][]>

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status}`)
  return res.json() as Promise<T>
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${res.status}`)
  return res.json() as Promise<T>
}

export function useApi<T>(path: string) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    setLoading(true)
    apiGet<T>(path)
      .then((d) => alive && (setData(d), setError(null)))
      .catch((e) => alive && setError(String(e)))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [path])

  return { data, error, loading }
}
