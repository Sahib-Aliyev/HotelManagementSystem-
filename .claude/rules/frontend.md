---
paths:
  - "app/templates/**"
  - "app/static/**"
---

# Frontend rules

Loaded when a template or a static asset is opened. The invariant index in
`CLAUDE.md` names the headline rules in one line each; this is the full
version.

## Calling the API

- Frontend API calls always go through the `api()` helper in
  `app/static/js/app.js`; never call `fetch()` directly. The 401 handling and
  the error format are implemented only there.

## Frontend design system

The templates share one vocabulary of component classes instead of repeating
long utility strings. Reuse it rather than hand-rolling a new card or button.

- The classes live in the `<style type="text/tailwindcss">` block in
  `base.html`, inside `@layer components`, so the Tailwind CDN compiles them
  into its own sheet and a utility written on the element still wins over the
  component default. `.card`, `.card-hd`, `.card-bd`, `.card-ft`, `.card-lift`,
  `.btn` (+ `.btn-primary` / `.btn-accent` / `.btn-outline` / `.btn-ghost` /
  `.btn-danger` / `.btn-solid-danger`, sized with `.btn-sm` / `.btn-xs`),
  `.btn-icon`, `.input` (+ `.input-sm` / `.input-error`), `.field`, `.hint`,
  `.error-text`, `.badge`, `.chip` (+ `.chip-on`), `.tbl`, `.nav-link`
  (+ `.nav-link-on`), `.panel-title`, `.panel-sub`, `.eyebrow`, `.tile-icon`,
  `.stat-value`.
- `app/static/css/app.css` holds only what utilities cannot express: design
  tokens, tabular figures, the skeleton sheen, the `.stagger` cascade, the
  active-nav indicator, `.edge-top`, the focus ring, the skip link and print
  rules. **`@apply` does not work there** — that file is served as a static
  asset and Tailwind never sees it.
- `brand` is a single coherent indigo ramp and `accent` a full emerald ramp.
  Do not introduce a one-off hex; if a new tint is needed, add the step to the
  ramp in `base.html`.
- Status colours come from `badgeClass(status)` and `dotClass(status)` in
  `app.js`, which map a status to one of the shared tones. Add new statuses to
  `STATUS_TONES`, never to a template.
- Chart styling is centralised in `chartTheme()`, which also sets the Chart.js
  defaults (font, tooltip). Read colours from it instead of hard-coding them.
- `/static` is cache-busted with `?v={{ asset_version }}`, derived from the
  mtimes of `app.css` and `app.js` in `app/routers/web.py`. Any new static
  asset referenced from a template should carry the same query.
- **A popover inside a grid card has to leave the card.** The cards in
  `rooms.html` are ~155px wide at the two-column breakpoint and the menu is
  `w-44` (176px), so anchored inside the card it overflows the grid in every
  direction and is clipped by whichever ancestor scrolls. `cardMenu()` in
  `app.js` is the pattern: `<template x-teleport="body">` keeps the card's
  Alpine scope but moves the element out, and the menu is positioned with
  fixed coordinates measured off its button and clamped to the viewport. It
  follows the button while the page scrolls and closes once the button leaves
  the screen. Popovers anchored in the top bar need none of this — there the
  viewport edge is the only boundary.
- **Never drive a popover's position with `:style` while `x-show` controls it.**
  A style binding rewrites the whole inline `style` attribute, which wipes the
  `display: none` that `x-show` wrote — every menu on the page then stays
  rendered, invisible but real, parked at whatever coordinates it last had.
  Write positions imperatively (`el.style.left = …`), and leave `display` to
  `x-show`.
- **Listeners bound to a teleported element do not fire**, `.window`
  modifiers included. Put the close handlers (`@click.outside`,
  `@keydown.escape.window`, `@scroll.window`, `@resize.window`) on the wrapper
  that stays in the tree, which shares the same Alpine scope.
- **`x-transition` hands `display` to a completion callback.** In a background
  tab that callback never runs, so a transitioned `x-show` element can stay
  rendered. Fine for a drawer the user is looking at; not fine for a menu whose
  hidden state has to be reliable, which is why the room-card menu has no
  transition.
- **"Sleeps up to N" is a room, "N guest(s)" is a booking.** Capacity belongs to
  the room type, is shared by every room of that type and does not follow the
  booking — a Family Room sleeps up to 4 whether one guest or four are in it. It
  is also the ceiling a booking is validated against, so it cannot follow one.
  The party size belongs to the stay. Both numbers belong on a room card and
  they are stated together rather than in separate places where they read as
  rival answers to the same question: an occupied room says **"1 of 4 guests"**,
  an empty one **"Sleeps up to 4"**, and a "Next arrival" block names the party
  that is coming (`27 Aug · 1 guest`). Printing one
  in the other's words puts two different numbers for the same room on two
  screens — see `docs/history/review-2026-08-17.md`. `settings.html` and
  `new_reservation.html` already
  used "Sleeps"/"sleeps"; keep to it.
- **Anything counted in two units has to name the unit.** "In house" is five
  stays and nine people at the same time; "occupied" is five rooms. A bare
  number next to another bare number reads as a contradiction even when both are
  right, so the dashboard tile says *Guests in house* with `N stay(s)` under it,
  and the front-desk column says `N stay(s) · N guest(s)`. Same for arrivals and
  departures: those count stays, not people.
- **The sidebar is `lg:sticky lg:top-0 lg:h-screen`, not `lg:static`.** As a
  static flex child it stretched to the height of the page, so scrolling a long
  list carried the whole navigation off screen and left an empty column behind.
  It keeps `left: auto` from `lg` up — a sticky flex child has no reason to
  offset horizontally — and animates only `width` and `transform`, because
  `transition-all` on a full-height sticky layer animates far more than the
  collapse and is a repaint hazard.
- **A `<template x-if>` inside an `<svg>` silently breaks Alpine** — SVG is
  foreign content, so the element has no `.content` and Alpine throws on
  `cloneNode`. Bind the shape instead (`<path :d="…">`), as the toast host does.

## Lifted from the audits

- `openInvoicePdf()` POSTs to issue the invoice before opening the PDF, and
  opens the tab inside the click so pop-up blocking does not eat it — never
  link a GET at `/pdf` → `docs/history/review-2026-08-17.md`
- `fmt.overdueLabel` labels how many days overdue a stay or an arrival is, on
  the dashboard, the front desk, the rooms board and the reservations list →
  `docs/history/review-2026-08-17.md`
