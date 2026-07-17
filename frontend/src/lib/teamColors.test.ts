import { describe, it, expect } from 'vitest'
import {
  manufacturerAccentColor,
  teamCode,
  resolveTeamColor,
  teamColorWithAlpha,
  teamShortName,
  teammateShade,
} from './teamColors'

describe('teamShortName', () => {
  it('shortens the officially-long names', () => {
    expect(teamShortName('Red Bull Racing')).toBe('Red Bull')
    expect(teamShortName('Haas F1 Team')).toBe('Haas')
  })
  it('codes the two names that overlap under the pace-chart axis labels', () => {
    expect(teamShortName('Aston Martin')).toBe('AM')
    expect(teamShortName('Racing Bulls')).toBe('RB')
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

describe('teammateShade', () => {
  it('darkens light team colors (Mercedes cyan)', () => {
    // #27F4D2 halved toward black
    expect(teammateShade('Mercedes')).toBe('rgb(20, 122, 105)')
  })
  it('lightens dark team colors (Ferrari red)', () => {
    // #E8002D halved toward white
    expect(teammateShade('Ferrari')).toBe('rgb(244, 128, 150)')
  })
  it('passes the fallback var through untouched', () => {
    expect(teammateShade(null)).toBe('var(--color-muted)')
  })
})

describe('manufacturerAccentColor', () => {
  it('mixes the resolved team hex toward the theme ink token', () => {
    // The actual lightening/darkening happens in the browser (--color-ink flips per theme);
    // this only pins that the mix targets the right hex and the right CSS variable.
    expect(manufacturerAccentColor('Ferrari')).toBe('color-mix(in oklch, #E8002D 55%, var(--color-ink) 45%)')
    expect(manufacturerAccentColor('Mercedes')).toBe('color-mix(in oklch, #27F4D2 55%, var(--color-ink) 45%)')
  })
  it('falls back for an unknown team', () => {
    expect(manufacturerAccentColor(null)).toBe('color-mix(in oklch, var(--color-muted) 55%, var(--color-ink) 45%)')
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
