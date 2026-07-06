// FIA 3-letter code -> driver name. Codes are assigned per driver and stay stable across team
// moves, so this doesn't go stale when the grid reshuffles; only genuinely new drivers need
// adding. Unknown codes fall back to the code itself, so a missing entry is never a wrong name.
const DRIVER_NAMES: Record<string, string> = {
  VER: 'Max Verstappen',
  RUS: 'George Russell',
  ANT: 'Kimi Antonelli',
  NOR: 'Lando Norris',
  PIA: 'Oscar Piastri',
  LEC: 'Charles Leclerc',
  HAM: 'Lewis Hamilton',
  ALO: 'Fernando Alonso',
  STR: 'Lance Stroll',
  GAS: 'Pierre Gasly',
  OCO: 'Esteban Ocon',
  ALB: 'Alexander Albon',
  SAI: 'Carlos Sainz',
  COL: 'Franco Colapinto',
  HAD: 'Isack Hadjar',
  LAW: 'Liam Lawson',
  HUL: 'Nico Hulkenberg',
  BOR: 'Gabriel Bortoleto',
  BEA: 'Oliver Bearman',
  BOT: 'Valtteri Bottas',
  PER: 'Sergio Perez',
  LIN: 'Arvid Lindblad',
}

export function driverName(code: string | null | undefined): string {
  if (!code) return ''
  return DRIVER_NAMES[code] ?? code
}
