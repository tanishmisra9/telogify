// Turns one real traced example (GET /insights/traced) into the pieces the How-it-works walkthrough shows. Pure.
import type { TracedExample } from '@/lib/api'

// The sentence of the published prose that carries the figure, split around it so the figure can be coloured.
// Falls back to the whole text, uncoloured, when the exact figure text isn't found (never a guessed highlight).
export function quoteParts(ex: Pick<TracedExample, 'explanation_web' | 'traced_with_unit'>): {
  before: string
  figure: string
  after: string
} {
  const sentences = ex.explanation_web.split(/(?<=[.!?])\s+(?=[A-Z])/)
  const sentence = sentences.find((s) => s.includes(ex.traced_with_unit)) ?? ex.explanation_web
  const at = sentence.indexOf(ex.traced_with_unit)
  if (at === -1) return { before: sentence, figure: '', after: '' }
  return {
    before: sentence.slice(0, at),
    figure: ex.traced_with_unit,
    after: sentence.slice(at + ex.traced_with_unit.length),
  }
}

const json = (v: unknown) => JSON.stringify(v)

// `{{x}}` marks the traced figure (accent) in CodeBlock; "key": is dimmed by it.
const hot = (s: string) => `{{${s}}}`

/** Step 3: the value as stored, written before the agent runs. */
export function storedLines(ex: TracedExample): string[] {
  const ident = Object.entries(ex.row).find(([k, v]) => k !== ex.key && typeof v === 'string')
  return ['{', ...(ident ? [`  ${json(ident[0])}: ${json(ident[1])},`] : []), `  ${json(ex.key)}: ${ex.raw}`, '}']
}

/** Step 5: the logged tool call and the one row of its return the number came from. */
export function toolCallLines(ex: TracedExample): string[] {
  const entries = Object.entries(ex.row)
  return [
    `${ex.tool}(${json(ex.args)})`,
    '[',
    '  ...',
    '  {',
    ...entries.map(([k, v], i) => {
      const val = k === ex.key ? hot(ex.raw) : json(v)
      return `    ${json(k)}: ${val}${i < entries.length - 1 ? ',' : ''}`
    }),
    '  },',
    '  ...',
    ']',
  ]
}

/** Step 6: the gate's check, prose figure against the logged value. */
export function gateLines(ex: TracedExample): string[] {
  return [`prose:  ${hot(ex.traced)}`, `logged: ${hot(ex.raw)}  (${ex.key})`, 'result: match (to the prose rounding)']
}

// A stable id for the shuffle bag: one figure of one published insight.
export const exampleId = (ex: Pick<TracedExample, 'year' | 'round' | 'header' | 'traced'>): string =>
  `${ex.year}-${ex.round}-${ex.header}-${ex.traced}`
