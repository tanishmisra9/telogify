# Telogify design system

**Theme: dark.** Scene: an analyst checking weekend insights on a laptop, focused, glare
reduced, data and chart lines forward. Dark is forced by that scene, and it keeps the
single amber accent and Recharts lines vivid without the warm-near-white AI default.

**Color strategy: restrained.** Tinted near-black surfaces + one amber accent held under
~10% of the surface. OKLCH throughout. Glass (backdrop blur) is used purposefully on the
insight panels and nav, never as a decorative default.

Tokens (see `src/index.css` `@theme`):
- `bg` near-black, slight cool tint; `surface` one step up; `glass` translucent + blur
- `ink` near-white body (>= 4.5:1 on bg); `muted` secondary (still >= 4.5:1)
- `accent` amber; `accent-ink` dark text for on-amber
- `border` hairline white at 8%

**Type: sans + mono on a contrast axis.** System sans (SF on Apple) for UI and prose;
mono with `tabular-nums` for emphasised telemetry numbers, so the figures read as data.

**Motion.** Spring physics + blur-fade entrances (Framer Motion), ease-out, no bounce.
Every animation has a `prefers-reduced-motion` crossfade/instant fallback (see
`src/lib/motion.ts` and the `BlurFade` primitive).
