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

export interface PaceStint {
  driver: string
  constructor: string | null
  stint_number: number
  compound: string | null
  lap_start: number | null
  lap_times: number[]
}

export interface ResultRow {
  position: number | null
  driver: string
  constructor: string | null
  gap_to_leader: number | null
  status: string | null
}

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
