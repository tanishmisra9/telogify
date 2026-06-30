import { useParams } from 'react-router-dom'

export function WeekendPage() {
  const { year, round } = useParams()
  // Filled in M18: 3 insights + pace plots + finishing order.
  return (
    <main className="mx-auto max-w-5xl px-6 py-16">
      <p className="num text-sm text-muted">
        {year} · R{round}
      </p>
    </main>
  )
}
