# Telogify design system

Editorial-brutalist. The look of a printed timing sheet an analyst trusts: cream paper, hard
ink borders, one hot F1 red, oversized type doing the work. `src/index.css` (`@theme` +
`:root[data-theme='dark']`) is the single source of truth; change a token and every Tailwind
utility and SVG chart follows.

**Theme: cream by day, warm-espresso by night.** Scene: someone reading a verdict on a race
weekend, wanting the numbers to feel printed and certain. The default is a warm cream
(`--color-bg #fffdd0`) with warm near-black ink; a full dark mode (warm espresso, not cool
slate) flips every token under `:root[data-theme='dark']`, applied pre-paint from localStorage
by a script in `index.html` and toggled from `ThemeToggle` in the nav's **right-hand** group.

**Color strategy: restrained, one committed accent.** Cream/paper surfaces + warm near-black
ink + a single F1 red (`--color-accent` ~`#E10600`, `oklch(0.585 0.238 28)`). OKLCH throughout.
Team colors (hardcoded hex in `lib/teamColors.ts`) carry the data viz and are theme-independent.
Tokens: `bg` / `surface` / `glass`, `ink` / `muted` (both >=4.5:1 on bg), `accent` / `accent-ink`,
`border` (ink at 15% by day, 16% at night), and `shadow` (the offset color).

**To darken a token and have it work in both themes, mix toward `--color-shadow`** (dark in
both), never `--color-ink`, which is near-white at night and therefore *lightens* in dark mode.

**The signature: the hard printed-card offset.** `box-shadow: 4px 4px 0 var(--color-shadow)` —
a flat, un-blurred offset, not the newer flat-border variant. Near-sharp corners
(`--radius-panel: 2px`). Keep this on purpose; it is the one brutalist voice, not two.

**Type.** Display headers in **Instrument Sans** (`--font-display`, weight 500+); body/UI in
**Space Grotesk** (`--font-sans`); telemetry figures in **mono** (`--font-mono`:
`ui-monospace, "SF Mono", "JetBrains Mono", "Menlo"`) with `tabular-nums` so numbers read as
data. `h1-h3` are forced to `font-weight: 500`, `font-synthesis-weight: none`,
`letter-spacing: -0.01em`, `text-wrap: balance`; body `p` gets `text-wrap: pretty`.

**Display headings sit on a 0.9x ramp off Tailwind's scale**, not on the raw steps:
`text-[3.375rem]` = 0.9x `text-6xl`, `text-[4.05rem]` = 0.9x `text-7xl`, `text-[5.4rem]` =
0.9x `text-8xl`. When resizing a heading, match that factor rather than inventing a size.
Two constraints on top of the ramp, both learned by breaking them:
- **A `SectionTitle` (h2) must stay smaller than every page's h1.** It is `sm:text-[4.05rem]`,
  which clears SeasonPage's 72px h1 and WeekendPage's 86.4px. If any page h1 shrinks, re-check.
- **`Race weekends` / `Season at a glance` are `text-[3.375rem] sm:text-7xl` on purpose:** 0.9x
  on mobile, the raw step at `sm+`. `Season at a glance` appears twice (`SeasonView` and
  `SeasonRedirect`); restyle both.

## Primitives (utility classes in `index.css`)

- `.glass` — the paper card: solid surface, 1.5px ink border, the offset shadow, sharp corners.
  (Named for legacy reuse; it is not translucent.)
- `.lift` — hover raise (`translate(-2px,-2px)` + deepen the offset to `6px 6px 0`), fine-pointer
  only. Pair `.glass .lift` for an interactive card.
- `.kicker` — mono uppercase tracked label. Editorial signpost. **Use it as a named status
  marker** (`404`, `CONFIRMED`, `LINK EXPIRED`) or a form label, never as an eyebrow above every
  section: an eyebrow on every block is scaffolding, not voice.
- `.num` — mono tabular figures (`tabular-nums`, `tnum`). Size is applied ad hoc alongside it.

Undocumented for a long time but load-bearing, all in `index.css`:
- a fixed **paper-grain** overlay on `body::before` (opacity `0.035`, lifted to `0.06` at night)
  with `#root` at `z-index: 1` above it;
- `::selection` painted accent-on-accent-ink;
- a global `@media (prefers-reduced-motion: reduce)` kill switch that collapses every animation
  and transition to `0.01ms`.

## Forms and interactive controls

There were no form primitives in the codebase until the subscribe flow; these are the pattern.

| Element | Treatment |
|---|---|
| Text input | `w-full rounded-panel border-[1.5px] border-ink bg-surface px-4 py-3 text-ink outline-none transition-shadow placeholder:text-muted` |
| Input focus | `focus-visible:shadow-[3px_3px_0_var(--color-accent)]` — the signature offset in accent, rather than importing a generic ring |
| Button focus | `focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-4 focus-visible:ring-offset-bg` (matches `Nav.tsx`) |
| Primary action | `lift rounded-panel border-[1.5px] border-ink bg-accent px-6 py-2.5 font-display text-2xl text-accent-ink shadow-[4px_4px_0_var(--color-shadow)]` |
| Secondary action | as above with `bg-surface text-ink` |
| Disabled | `disabled:opacity-60` |
| Inline error | `<p role="alert" className="text-sm text-accent">` |
| Async status | wrap the swapping region in `aria-live="polite" aria-atomic="true"`, and move focus to the new heading when a form is replaced by its confirmation |

**Buttons are full width on mobile, auto on desktop** (`w-full sm:w-auto`), so the tap target
spans the column on a phone without stretching across a desktop measure.

**`components/StatusPage.tsx`** is the shared chassis for short terminal pages (404, verification
result, unsubscribe result): `min-h-[60vh]` + centred flex column so a three-line page reads as
deliberate rather than stranded at the top, then kicker / h1 / one supporting line / up to two
actions. `StatusLink` and `StatusButton` carry the two button variants above.

## Motion

Spring physics + blur-fade entrances via framer-motion's `LazyMotion` + slim `m` components
(`lib/motion.ts`: `blurFadeIn`/`blurFadeOut`/`spring`, plus `expandTransition`, `drawTransition`
for line draw-ins and `morphTransition` for tab-switch shape morphs). Three reveal primitives:
`BlurFade` (on mount), `ScrollReveal` (`whileInView`, once), and `LoadingSwap` (the
placeholder-to-content crossfade every async swap goes through). Ease-out, no bounce. Every
animation collapses to no movement under `prefers-reduced-motion`; reveals enhance already-visible
content and never gate visibility on a transition.

## Copy rules

- **No em dashes in UI copy or LLM output.** Use periods, colons, or commas. (Source files still
  contain them in comments; the rule is about what a reader sees.)
- Plain language, full driver and team names, plain ordinals. Never a figure a reader could act
  on while it is still loading.
- Error messages name what to do next, not what went wrong internally.

## Known issues

- Nothing outstanding. `rounded-[--radius-panel]` used to compile to invalid CSS under Tailwind
  v4 (24 usages shipping at 0px instead of 2px); it is now `rounded-panel` everywhere. If you add
  a token-driven utility, prefer the `@theme` name (`rounded-panel`) over the bare `[--var]`
  bracket form, which v4 no longer supports.
- `PRODUCT.md` in this directory is stale: it claims Recharts (every chart is hand-rolled SVG),
  "three surfaces" (there are six routes), and a subscribe tagline that no longer exists.
