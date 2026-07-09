# Product

## Register

product

## Users

F1 fans who love the sport but aren't engineers: they want to understand WHY a car's weekend
went the way it did, beyond what the results table and broadcast already told them. They arrive
after a race weekend to read 3 telemetry-grounded insights, browse pace/tyre/qualifying charts for
a specific weekend, or check the season-wide constructor ranking.

## Product Purpose

Telogify ingests a full FastF1 race weekend and produces 3 quantified, telemetry-grounded insights
per weekend, shown on a web page and emailed as a digest. Every number is computed deterministically
by the backend and traced to a real telemetry/timing source; nothing is invented. The insights are
the product; the charts (pace spread, qualifying car character, tyre degradation, top speeds,
finishing order) are supporting evidence a reader can drill into.

## Brand Personality

Editorial, precise, unshowy. Reads like a well-typeset data journalism piece, not a SaaS dashboard:
confident typographic hierarchy (serif display + grotesk body + mono figures), paper-card panels
with a hard ink border and offset shadow rather than soft shadows or glassmorphism, team colors as
the only strong color signal (everything else is cream/espresso neutral).

## Anti-references

Generic SaaS analytics dashboards (gradient hero metrics, glass-blur cards, tiny uppercase eyebrows
on every section, rounded pill everything). No trademarked F1 logos or driver photos (color + text
only). No engineering jargon in prose aimed at fans.

## Design Principles

- Every number reads as data: color-emphasized figures, monospace for telemetry, exact units.
- Panels are paper, not glass: an ink border and a hard offset shadow, not a blur.
- Team color is the one strong color signal in any chart; everything else stays neutral.
- Never mislead: a chart's visual weight (bar height, line boldness) must match what the
  underlying number actually supports.
- Both light (cream) and dark (espresso) themes are first-class, flipped by one set of CSS tokens.

## Accessibility & Inclusion

Standard WCAG AA contrast on the cream/espresso token pairs. Tooltips are keyboard-focusable
(instant on focus, ~500ms hover delay on pointer) so hint text isn't mouse-only.
