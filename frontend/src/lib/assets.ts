// Static asset lookups. Team name -> /teams/<slug>.png, driver code -> /drivers/<CODE>.png.
// Callers fall back gracefully (img onError) when a file is missing.

export function teamSlug(team: string | null | undefined): string | null {
  if (!team) return null
  return team.toLowerCase().replace(/[^a-z0-9]/g, '')
}

export function teamLogo(team: string | null | undefined): string | null {
  const slug = teamSlug(team)
  return slug ? `/teams/${slug}.png` : null
}

export function driverPhoto(code: string): string {
  return `/drivers/${code}.png`
}
