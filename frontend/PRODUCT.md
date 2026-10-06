# Telogify (frontend)

F1 telemetry intelligence. A race weekend goes in; three quantified, telemetry-grounded insights
come out, shown on the web and emailed as a digest. The insights are the product, everything else
is substrate. Surfaces, deliberately minimal:

1. **Landing** (`/`) and **Weekends** (`/weekends`): processed race weekends, each linking to its page.
2. **Race weekend page** (`/weekends/:year/:round`), the hero: the insights at the top (telemetry
   numbers emphasised), then practice, qualifying (including "The fight to pole"), sprint and race
   sections with hand-rolled SVG charts (pace spread, tyre degradation) and the finishing order.
3. **Season** (`/season[/:year]`): constructor ranking, gap-by-round trend, power-unit deployment.
4. **Subscribe** (`/subscribe`): double opt-in email signup for the digest, with `/subscribe/verify`
   and `/unsubscribe` confirmation pages.

register: product (the design serves the data; insights are the product)

Audience: F1 fans and analysts reading weekend takeaways on a laptop, focused, data-forward.
The numbers are the point; the UI gets out of their way.

Constraints: team identity is color plus text only (no trademarked F1 logos or driver photos; the
app is headed for public release). Every figure shown traces to a deterministic backend number,
never one the UI or an LLM invented. See `DESIGN.md` for the visual system.
