import type { CarCharacterRow } from '@/lib/api'

// Deterministic template text over already-computed labels/flags, no model involved:
// one headline per team, picking its single most notable trait by priority so the
// summary reads like a front page, not a re-statement of every table cell.
export function summarizeCarCharacter(rows: CarCharacterRow[]): string[] {
  return rows.map((r, i) => {
    const who = `${r.constructor} (${r.driver})`
    // Rows are ranked by each driver's best clean lap, which is a telemetry sample, not
    // necessarily the official grid order (a lap can be clean but deleted for track
    // limits, etc.), so this never asserts a qualifying result like "pole".
    const isQuickest = i === 0

    if (isQuickest) {
      if (r.is_top_speed_leader || r.is_corner_speed_leader || r.drag_label === 'efficient, low drag') {
        return `${who}: quickest of the compared teams, competitive everywhere.`
      }
      return `${who}: quickest of the compared teams despite being ${r.drag_label}.`
    }
    if (r.is_top_speed_leader) return `${who}: best top speed.`
    if (r.is_corner_speed_leader) return `${who}: best downforce, quickest through the fastest corner.`
    if (r.drag_label === 'draggy, high-downforce') {
      return `${who}: slowest in a straight line, but strong through the corners.`
    }
    if (r.drag_label === 'lacks efficiency') {
      return `${who}: off the pace both in a straight line and through the corners.`
    }
    if (r.is_grip_leader) return `${who}: best grip in the slow corners.`
    return `${who}: no standout strength or weakness this session.`
  })
}
