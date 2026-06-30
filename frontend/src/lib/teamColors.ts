// F1 TeamName -> color, matched against the `constructor` field in our /pace payload.
// Ported from the Telesis project (covers 2018+ naming variants).
export const TEAM_COLORS: Record<string, string> = {
  'Red Bull Racing': '#3671C6',
  Ferrari: '#E8002D',
  Mercedes: '#27F4D2',
  McLaren: '#FF8000',
  'Aston Martin': '#229971',
  Alpine: '#0093CC',
  Williams: '#64C4FF',
  RB: '#6692FF',
  AlphaTauri: '#6692FF',
  'Scuderia AlphaTauri': '#6692FF',
  'Kick Sauber': '#52E252',
  'Alfa Romeo': '#52E252',
  'Haas F1 Team': '#B6BABD',
  'Racing Bulls': '#6692FF',
  'Toro Rosso': '#469BFF',
  Renault: '#FFF500',
  'Racing Point': '#F596C8',
  'Force India': '#F596C8',
  Sauber: '#52E252',
  'Williams Racing': '#64C4FF',
  Audi: '#F50537',
  Cadillac: '#E8A33D',
}

const FALLBACK_COLOR = 'var(--color-muted)'

export function resolveTeamColor(teamName: string | null): string {
  return (teamName && TEAM_COLORS[teamName]) || FALLBACK_COLOR
}

/** Fill with reduced opacity for box surfaces. */
export function teamColorWithAlpha(teamName: string | null, alpha: number): string {
  const hex = resolveTeamColor(teamName)
  if (!hex.startsWith('#') || hex.length < 7) {
    return hex
  }
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}
