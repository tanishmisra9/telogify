import type { ReactNode } from 'react'

// Wrap measurement-like tokens (12 km/h, 7 mph, 0.35 s, 95%, 330.5) so telemetry numbers
// read as data. One capturing group, so split() alternates text / match.
const NUM_RE = /(\d[\d.,]*(?:\s?(?:km\/h|mph|°C|%|s|km|m))?)/g

export function emphasize(text: string): ReactNode[] {
  return text.split(NUM_RE).map((part, i) =>
    i % 2 === 1 ? (
      <span key={i} className="num text-accent">
        {part}
      </span>
    ) : (
      <span key={i}>{part}</span>
    ),
  )
}
