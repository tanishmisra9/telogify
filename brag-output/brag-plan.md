# Brag Plan: Telogify

## What is this app?
An F1 telemetry engine that ingests a full race weekend and produces three quantified,
plain-language insights where every single number is traceable to official timing data.
The brag: it is architecturally incapable of making a number up.

## The angle
Everyone has an AI that talks about F1. Telogify has one that *can't lie*. The deterministic
backend computes every figure into a database; the agent only retrieves exact values and is
hard-gated against fabricating narrative. So the video's premise is quiet confidence:
"The result tells you who won. The number tells you why." No hype, just receipts.

## Hook (first 2-3 seconds)
The real hero line, on cream paper, in the app's own display serif-sans:
**"Every weekend, cut the noise."** — with *noise* slamming in red. Then the noise literally
clears.

## Key moments (the middle)
- The actual brutalist insight card sliding in: slot "01", a bold header, body copy with the
  numbers reddened exactly like the live app (`emphasize.tsx`): "Ferrari were **12 km/h** down
  through the DRS zones."
- The proof line the landing page really ships: "Every figure traced to official timing data.
  Nothing estimated." — with a number visibly tracing back to a data row.
- The differentiator beat: **"Zero fabricated numbers."** The guardrail is a hard gate; this is
  the one claim no competitor can make.

## Outro / punchline
The real closing line of the site: **"The result tells you who won. The number tells you why."**
then the Telogify wordmark with the Browse / Subscribe brutalist buttons.

## User flow worth showing
Weekend goes in → deterministic analysis computes every number → agent writes three traceable
insights. Centerpiece is the **insight card as it appears on the weekend page**, in the exact
component and voice — that is the product doing its thing.

## Tone
- Preset: polished
- Creative direction: quiet premium product film for a tool that refuses to bluff
- Interpretation: fewer scenes, longer holds, confidence through restraint. Motion is crisp
  and editorial, never busy. The claims are understated because they're real.

## Format: landscape — 1920x1080
## Duration: ~20 seconds

## Visual identity (from the project)
- Background: #FFFDD0 (cream paper), faint fractal-noise grain overlay
- Accent: #E10600 (F1 hot red), used only on the numbers and the word "noise"
- Text: warm near-black ink oklch(0.205 0.012 60)
- Display font: Instrument Sans (weight 500, tracking -0.01em)
- Body font: Space Grotesk; telemetry figures in mono, tabular-nums
- Signature move: editorial-brutalist paper card — 1.5px ink border + hard 4px offset shadow,
  2px corners. Mono uppercase "kicker" labels.

## Share copy (draft)
Built an F1 analyst that's architecturally incapable of making a number up. Every figure it
prints traces back to official timing data. Zero hallucinated stats. Telogify.

## Audio direction
- Role: warm, low, restrained bed — premium product film, not a hype reel
- Music: calm/confident instrumental, understated; none only if unavailable
- Music treatment: enter soft under the hook, sit low, gentle swell as the insight card lands,
  clean fade on the outro line
- Music cue guidance: target one strong cue on the insight-card arrival (~scene 3) and one on
  the "Zero fabricated numbers" beat; exact timestamps detected at composition time
- Audio-reactive treatment: subtle — a faint presence lift on the card shadow as it settles, no
  waveform bars
- SFX posture: sparse, motion-matched, professional restraint. A soft paper/print thunk when a
  card lands with its hard shadow; a light tick when a number reddens
- Audio-coupled moments: the number reddening (tick), the insight card landing (paper thunk),
  the wordmark set
- Restraint rule: no whooshes stacked on every cut, no risers, nothing that undercuts "quiet
  and precise"

## Storyboard

### Scene 1 — Hook: cut the noise — 3.0s
Cream paper with grain. Giant Instrument Sans "Every weekend, cut the noise." fills the frame,
"noise" red. A field of faint scattered marks (the noise) briefly clutters behind the text, then
clears as the line settles. Hold the settled line ~1.2s.
Sequential/interaction: none
Audio intent: soft entrance, establish calm confidence
Audio-coupled idea: subtle settle tick as "noise" reddens
Music: low warm bed enters
Transition mood: soft crossfade → Scene 2

### Scene 2 — The problem framing — 3.0s
Mono kicker "LATEST VERDICT". A minimal result strip: "P1" and a team-colored rule, stated flat.
Overline text: "The result tells you who won." Held, dry.
Sequential/interaction: none
Audio intent: hold tension, the setup before the payoff
Audio-coupled idea: none
Music: bed continues, quiet
Transition mood: soft crossfade → Scene 3

### Scene 3 — The insight card (centerpiece) — 5.0s
The real brutalist insight card slides in and lands with its hard 4px offset shadow: red slot
"01", header, then body copy typing/settling with numbers reddened: "Ferrari were 12 km/h down
through the DRS zones, and lost another 0.3 seconds a lap to degradation on the hards." Hold the
full card ~2.0s so it reads.
Sequential/interaction: yes — card lands, then the two numbers redden one after the other (~0.6s apart)
Audio intent: the payoff; gentle swell as the card settles
Audio-coupled idea: paper/print thunk on card land; light tick on each number reddening
Music: swell peak on card arrival
Transition mood: clean cut → Scene 4

### Scene 4 — The proof — 3.5s
Under the card, the real line fades up: "Every figure traced to official timing data. Nothing
estimated." One number from the card draws a thin line down to a mono data row to show the trace.
Hold ~1.5s.
Sequential/interaction: yes — trace line draws from number to source row
Audio intent: reassurance, the receipts
Audio-coupled idea: faint draw tick as the trace line completes
Music: bed resolves
Transition mood: soft crossfade → Scene 5

### Scene 5 — The differentiator — 2.5s
Near-empty cream frame. One line, centered, deadpan: **"Zero fabricated numbers."** with "Zero"
in red. Long confident hold.
Sequential/interaction: none
Audio intent: the mic-drop, understated
Audio-coupled idea: single soft accent as the line sets
Music: brief lift then settle
Transition mood: soft crossfade → Scene 6

### Scene 6 — Outro / wordmark — 3.0s
"The result tells you who won. The number tells you why." resolves to the **Telogify** wordmark,
with the two real brutalist buttons Browse / Subscribe beneath it.
Sequential/interaction: yes — the two buttons set in with their offset shadows
Audio intent: clean confident close
Audio-coupled idea: soft paper set on the wordmark; light thunk per button
Music: gentle final fade
Transition mood: final hold

**Music mood for this video:** polished / calm-confident instrumental
**Audio summary:** A low warm bed that stays out of the way, swelling once when the insight card
lands and once on "Zero fabricated numbers," with sparse motion-matched paper/print SFX and a
clean fade on the closing wordmark.
