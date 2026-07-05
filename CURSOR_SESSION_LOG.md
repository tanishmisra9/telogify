# Cursor Hardening Session Log

**Branch:** `cursor-hardening` (local only, not pushed)  
**Started:** 2026-07-05  
**Baseline:** backend 196 passed, frontend build + 21 tests green  

## Current status (Round 5)

| Suite | Count |
|-------|-------|
| Backend pytest | **233** passed (+37 from baseline) |
| Frontend vitest | **29** passed (+8 from baseline) |
| Commits on branch | **15** (hardening work + session log) |

## Why the first pass stopped

Round 1 finished subagents A–E and I treated "diminishing returns" as a stop signal. That was premature for a 3–4 hour session. **Round 2+ resumed** the same bounded rules: offline tests, a11y, docstrings only.

## Commits

| Commit | Area | Summary |
|--------|------|---------|
| `aee8ec3` | B | Guardrail pinning: retirement, DRS, doubled-constructor, ≥31 km/h |
| `25ff988` | C | Ingest: throttle>100, race-control retirement/forced-off/dedupe |
| `dbca25c` | A | race_pace, miner caps, clip boundaries |
| `21a43c3` | D | Tooltip focusCapture, chart toggles, nav aria-current |
| `0bbe479` | E | deployment.py representative-lap docstring |
| `a02d912` / `5cabe67` | log | Session log |
| `4267259` | B | Grid, leadership, career framing guardrail tests |
| `1617a24` | serialize | strip_em_dashes dedicated tests |
| `6909c71` | A/C | segment default window, race_pace two-lap, race_control empty msg |
| `5183136` | D/C | qualiInsights tests, landing/countdown/subscribe a11y |
| `d7a31de` | B/A | parse_insights edges, classify_speed boundaries |
| `6f2f7e8` | D | drivers + emphasize frontend tests |
| `91a2b3b` | A/D | DTW length mismatch, weekends list aria-labels |
| `3c1e574` | E/A | points_for_session docstring, gap label + heat tie tests |
| *(pending)* | A/B | pick_fastest_corner MIN_LOSS boundary, corner delta sign, guardrail negatives |

## Subagent coverage (cumulative)

### A — Analysis tests
- race_pace: compound tags, two-lap median, mean
- miner_caps: corner/straight MAX boundaries, negative delta subject
- deployment: clip MIN_DROP / MIN_CLIP_M boundaries
- fingerprints: DTW unequal-length sequences
- quali_character analysis: MIN_CORNER_LOSS_KMH boundary
- attribution: classify_speed at LOW/MID thresholds

### B — Guardrails (pin only, no semantic edits)
- Grid rows, leadership, start-lap, career framing
- Retirement causes, DRS, doubled-constructor, ≥31 km/h backstop
- Negative tests: collision allowed, plain ordinals, 30 km/h not flagged

### C — Ingest helpers
- full_throttle_fraction drops throttle>100
- race_control: retirement, forced_off, dedupe, empty messages
- segment: default CORNER_HALF_WINDOW_M

### D — Frontend hygiene + a11y
- qualiInsights, drivers, emphasize, heat unit tests
- Tooltip focusCapture; chart aria-pressed/labels; nav/footer/home labels
- Landing CTAs, countdown aria-live, subscribe role=alert
- Weekends list per-row aria-label

### E — Docstrings
- ingest/deployment.py: representative lap (not clean lap)
- ingest/results.py: points_for_session sprint vs race
- qualiInsights.ts: representative lap comment

## Still off-limits / skipped

- `agent/prompts.py`, guardrail regex/threshold edits, ingest numeric constants, pace ranking
- API spend (`run-weekend`, `send-digest`, live FastF1)
- Headless screenshots not re-run this round (unchanged a11y-only diffs)

## Human review

- None blocking. Optional: run screenshot recipe after merge if you want visual confirmation of a11y-only frontend diffs.
