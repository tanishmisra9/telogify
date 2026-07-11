import type { ReactNode } from 'react'

// Wrap measurement-like tokens so the number AND its metric read as one red unit:
// ordinals stay whole ("11th", "22nd"), and spelled-out or symbol units are kept intact
// ("3.994 seconds", "329 km/h", "95%"), never split into "3.994 s" + "econds".
// Longer units precede shorter ones so "seconds" wins over "s", "metres" over "m".
const METRIC_UNIT = /seconds?|sec|metres?|meters?|km\/h|kph|mph|m\/s²|m|s|%/i

/** Non-breaking space between a number and its unit so headings do not break "0.058" / "s". */
export function bindMetricSpaces(text: string): string {
  const re = new RegExp(`(~?\\d[\\d.,]*)\\s+(${METRIC_UNIT.source})(?=\\b)`, 'gi')
  return text.replace(re, '$1\u00a0$2')
}

// The trailing (?![a-zA-Z]) stops the bare "s"/"m" unit alternatives from swallowing the first
// letter of the next word ("lap 7, served" must not match "7, s" out of "served").
const NUM_RE = /(\d[\d.,]*(?:st|nd|rd|th|\s?(?:seconds?|metres?|meters?|km\/h|mph|m\/s²|°C|%|km|m|s)(?![a-zA-Z]))?)/g

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
