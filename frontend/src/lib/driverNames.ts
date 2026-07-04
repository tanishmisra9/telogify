// Code -> full name for the current grid, sourced from FastF1's driver info (Abbreviation ->
// FullName). Stopgap: the backend stores only 3-letter codes, so the model can't expand a rookie
// it has never seen (e.g. "LIN"). The durable fix is ingesting FastF1's FullName server-side; until
// then this resolves display surfaces. Unknown codes fall back to the code itself (never invent).
const DRIVER_NAMES: Record<string, string> = {
  ALB: 'Alexander Albon',
  ALO: 'Fernando Alonso',
  ANT: 'Kimi Antonelli',
  BEA: 'Oliver Bearman',
  BOR: 'Gabriel Bortoleto',
  BOT: 'Valtteri Bottas',
  COL: 'Franco Colapinto',
  GAS: 'Pierre Gasly',
  HAD: 'Isack Hadjar',
  HAM: 'Lewis Hamilton',
  HUL: 'Nico Hulkenberg',
  LAW: 'Liam Lawson',
  LEC: 'Charles Leclerc',
  LIN: 'Arvid Lindblad',
  NOR: 'Lando Norris',
  OCO: 'Esteban Ocon',
  PER: 'Sergio Perez',
  PIA: 'Oscar Piastri',
  RUS: 'George Russell',
  SAI: 'Carlos Sainz',
  STR: 'Lance Stroll',
  VER: 'Max Verstappen',
}

export function driverName(code: string): string {
  return DRIVER_NAMES[code] ?? code
}

