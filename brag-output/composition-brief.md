# Hyperframes Composition Brief: Telogify

## Objective
Create a short, polished launch-style brag video for Telogify — an F1 telemetry engine whose
whole point is that it cannot fabricate a number.

## Output
- Composition directory: `brag-output/composition/`
- Rendered video: `brag-output/brag.mp4`
- Format: landscape — 1920x1080
- Duration: ~20 seconds

## Source Material
- Project root: /Users/tanishmisra/Code/Telogify
- Primary files read: frontend/index.html, frontend/src/index.css, frontend/src/pages/Landing.tsx,
  frontend/src/components/Insight.tsx
- Product name: Telogify
- Tagline / strongest claim: "Every weekend, cut the noise." / "The result tells you who won.
  The number tells you why."
- Key UI to recreate: the editorial-brutalist **insight card** (paper card, 1.5px ink border,
  hard 4px offset shadow, red slot number, reddened telemetry figures) exactly as it appears on
  the weekend page.
- Copy that must appear verbatim:
  - "Every weekend, cut the noise."
  - "The result tells you who won. The number tells you why."
  - "Every figure traced to official timing data. Nothing estimated."
  - "Zero fabricated numbers."

## Creative Direction
- Tone preset: polished
- Creative direction: quiet premium product film for a tool that refuses to bluff
- Interpretation: fewer scenes, longer holds, confidence through restraint. Crisp editorial
  motion, never busy. Real claims delivered flat.
- Angle: Everyone has an AI that talks about F1; Telogify has one that can't lie. The deterministic
  backend computes every figure; the agent only retrieves exact values and is hard-gated against
  fabrication. The video is quiet confidence, no hype, just receipts.
- Hook: "Every weekend, cut the noise." on cream paper, "noise" slamming red, a faint field of
  noise marks clearing as the line settles.
- Outro / punchline: "The result tells you who won. The number tells you why." resolving to the
  Telogify wordmark with the real Browse / Subscribe brutalist buttons.
- Avoid: generic SaaS language, abstract filler visuals, redesigning the brand.

## Visual Identity
- Background: #FFFDD0 cream paper (dark espresso oklch(0.192 0.009 55) NOT used — keep light theme)
- Text: warm near-black ink oklch(0.205 0.012 60)
- Accent: #E10600 F1 red (only on numbers and the word "noise"/"Zero")
- Display font: Instrument Sans (weight 500, letter-spacing -0.01em) — load from Google Fonts;
  fall back to a strong grotesque if unavailable
- Body font: Space Grotesk; telemetry figures in monospace, tabular-nums
- Visual references: editorial-brutalist paper card (`.glass`: solid surface, 1.5px ink border,
  4px 4px 0 hard offset shadow, 2px corners); mono uppercase kicker labels; faint fractal-noise
  paper grain overlay at ~0.035 opacity.

## Storyboard
Use `brag-output/brag-plan.md` as the creative contract.

Scene summary:
1. Hook — 3.0s — "Every weekend, cut the noise." fills frame, "noise" red, noise field clears.
2. Problem framing — 3.0s — kicker "LATEST VERDICT", flat result strip, "The result tells you who won."
3. Insight card (centerpiece) — 5.0s — real brutalist card lands with hard shadow; slot "01",
   header, body with two numbers reddening in sequence: "12 km/h" then "0.3 seconds a lap".
4. The proof — 3.5s — "Every figure traced to official timing data. Nothing estimated." with a
   thin trace line drawn from a number to a mono source row.
5. Differentiator — 2.5s — "Zero fabricated numbers." ("Zero" red), long confident hold.
6. Outro — 3.0s — "The result tells you who won. The number tells you why." → Telogify wordmark +
   Browse / Subscribe buttons.

## Audio
- Audio role: warm, low, restrained bed — premium product film
- Audio arc: soft entrance under the hook, sits low, gentle swell as the insight card lands, brief
  lift on "Zero fabricated numbers," clean fade on the outro.
- Music: happy-beats-business-moves-vol-12-by-ende-dot-app.mp3 (steady/clean, polished tone)
- Music treatment: volume ~0.28, fade under the final wordmark
- Music cue guidance: bundled preset for vol-12 if present at
  assets/music/cues/happy-beats-business-moves-vol-12-by-ende-dot-app.music-cues.json; else run
  `npx hyperframes beats`. Lock one strong cue on the insight-card land (scene 3) and one on
  "Zero fabricated numbers" (scene 5).
- Audio-reactive treatment: subtle — faint presence lift on the insight-card shadow as it settles;
  no waveform/equalizer visuals.
- Audio-coupled moments:
  - Scene 1 — soft settle tick as "noise" reddens
  - Scene 3 — paper/print thunk on card land; light tick on each number reddening (sequential)
  - Scene 4 — faint draw tick as the trace line completes
  - Scene 6 — soft paper set on wordmark; light thunk per button
- SFX selection guidance: polished/minimal. `interface/drop_001` for gentle reveals,
  `impact/impactWood_light_*` or `impact/impactSoft_medium_*` for the card land, a very soft accent
  for the "Zero" line. All at 0.5–0.7 volume. Nothing aggressive.
- SFX analysis guidance: consult sfx-analysis.md; prefer low HF-risk files for the repeated number ticks.
- Exact SFX choice: Hyperframes selects filenames/timestamps/density from the implemented animation.
- Audio files: copy chosen music + SFX into brag-output/composition/assets/.

## Hyperframes Instructions
Use `/hyperframes-core` for the authoring contract and `/hyperframes-cli` for the dev loop.
Requirements:
- Show the real insight card UI and verbatim copy above.
- Keep all text readable (respect reading-time floors; hold the hook and card copy).
- 15–25s total.
- Include the music/SFX layer; treat audio notes as guidance, choose SFX after the animation exists.
- 1–3 strong-cue locks; snap the two sequential number ticks to the beat grid within tolerance.
- One subtle audio-reactive element (card presence), or document extraction failure.
- Local asset paths only (relative to composition/), never absolute.
- Lint + validate before render.
