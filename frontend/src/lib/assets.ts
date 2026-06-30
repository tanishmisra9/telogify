// Team name -> /teams/<slug>.png. Callers fall back gracefully (img onError) when missing.

export function teamSlug(team: string | null | undefined): string | null {
  if (!team) return null
  return team.toLowerCase().replace(/[^a-z0-9]/g, '')
}

export function teamLogo(team: string | null | undefined): string | null {
  const slug = teamSlug(team)
  return slug ? `/teams/${slug}.png` : null
}
