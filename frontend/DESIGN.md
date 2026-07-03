# Telogify design system

Editorial-brutalist. The look of a printed timing sheet an analyst trusts: cream paper, hard
ink borders, one hot F1 red, oversized type doing the work. `src/index.css` (`@theme` +
`:root[data-theme='dark']`) is the single source of truth; change a token and every Tailwind
utility and SVG chart follows.

**Theme: cream by day, warm-espresso by night.** Scene: someone reading a verdict on a race
weekend, wanting the numbers to feel printed and certain. The default is a warm cream
(`--color-bg #fffdd0`) with warm near-black ink; a full dark mode (warm espresso, not cool
slate) flips every token under `:root[data-theme='dark']`, applied pre-paint from localStorage
and toggled top-left in the nav.

**Color strategy: restrained, one committed accent.** Cream/paper surfaces + warm near-black
ink + a single F1 red (`--color-accent` ~`#E10600`, `oklch(0.585 0.238 28)`). OKLCH throughout.
Team colors (hardcoded hex in `lib/teamColors.ts`) carry the data viz and are theme-independent.
Tokens: `bg` / `surface` / `glass`, `ink` / `muted` (both ≥4.5:1 on bg), `accent` / `accent-ink`,
`border` (ink at 15%), and `shadow` (the offset color).

**The signature: the hard printed-card offset.** `box-shadow: 4px 4px 0 var(--color-shadow)` —
a flat, un-blurred offset, not the newer flat-border variant. Near-sharp corners
(`--radius-panel: 2px`). Keep this on purpose; it is the one brutalist voice, not two.

**Type.** Display headers in **Instrument Sans** (`--font-display`, weight 500+); body/UI in
**Space Grotesk** (`--font-sans`); telemetry figures in **mono** (`--font-mono`) with
`tabular-nums` so numbers read as data. `h1–h3` are forced to `font-weight: 500`,
`font-synthesis-weight: none`, `letter-spacing: -0.01em`, `text-wrap: balance`.

**Primitives (utility classes in `index.css`):**
- `.glass` — the paper card: solid surface, 1.5px ink border, the offset shadow, sharp corners.
  (Named for legacy reuse; it is not translucent.)
- `.lift` — hover raise (`translate(-2px,-2px)` + deepen the offset to `6px 6px 0`), fine-pointer
  only. Pair `.glass .lift` for an interactive card.
- `.kicker` — mono uppercase tracked label. Editorial signpost; use sparingly, never as an
  eyebrow above every section.
- `.num` — mono tabular figures (`tabular-nums`, `tnum`). The only numeral primitive; size is
  applied ad hoc alongside it for oversized readouts (e.g. the landing countdown).

**Motion.** Spring physics + blur-fade entrances via Motion's `LazyMotion` + slim `m`
components (`lib/motion.ts` `blurFadeIn`/`spring`, the `BlurFade` primitive), ease-out, no
bounce. Every animation collapses to no movement under `prefers-reduced-motion`; reveals
enhance already-visible content, never gate visibility on a transition.

**Copy rule.** No em dashes anywhere (code, UI, LLM output). Use periods, colons, or commas.
