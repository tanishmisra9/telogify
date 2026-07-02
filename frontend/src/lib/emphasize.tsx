import type { ReactNode } from 'react'

// Wrap measurement-like tokens so the number AND its metric read as one red unit:
// ordinals stay whole ("11th", "22nd"), and spelled-out or symbol units are kept intact
// ("3.994 seconds", "329 km/h", "95%"), never split into "3.994 s" + "econds".
// One capturing group, so split() alternates text / match. Longer units precede shorter
// ones in the alternation so "seconds" wins over "s" and "km/h" over "km"/"m".
const NUM_RE = /(\d[\d.,]*(?:st|nd|rd|th|\s?(?:seconds?|km\/h|mph|°C|%|km|m|s))?)/g

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
