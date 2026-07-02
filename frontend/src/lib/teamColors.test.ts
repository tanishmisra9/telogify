import { describe, it, expect } from 'vitest'
import { teamCode, resolveTeamColor, teamColorWithAlpha, teamShortName } from './teamColors'

describe('teamShortName', () => {
  it('shortens the officially-long names', () => {
    expect(teamShortName('Red Bull Racing')).toBe('Red Bull')
    expect(teamShortName('Haas F1 Team')).toBe('Haas')
  })
  it('passes short names through and handles null', () => {
    expect(teamShortName('Ferrari')).toBe('Ferrari')
    expect(teamShortName(null)).toBe('Unknown')
  })
})

describe('teamCode', () => {
  it('maps known teams', () => {
    expect(teamCode('Aston Martin')).toBe('AM')
    expect(teamCode('Haas F1 Team')).toBe('HAAS')
  })
  it('falls back to the first three letters uppercased', () => {
    expect(teamCode('Some New Team')).toBe('SOM')
    expect(teamCode(null)).toBe('?')
  })
})

describe('resolveTeamColor', () => {
  it('returns the hex for a known team', () => {
    expect(resolveTeamColor('Ferrari')).toBe('#E8002D')
  })
  it('falls back for unknown or null', () => {
    expect(resolveTeamColor('Nope')).toBe('var(--color-muted)')
    expect(resolveTeamColor(null)).toBe('var(--color-muted)')
  })
})

describe('teamColorWithAlpha', () => {
  it('builds rgba from a hex team color', () => {
    expect(teamColorWithAlpha('Ferrari', 0.5)).toBe('rgba(232, 0, 45, 0.5)')
  })
  it('returns the fallback var untouched when there is no hex', () => {
    expect(teamColorWithAlpha(null, 0.5)).toBe('var(--color-muted)')
  })
})
