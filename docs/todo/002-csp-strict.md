# 002 — A strict CSP: drop `unsafe-inline` and `unsafe-eval`

**Kind** security · **Size** days · **Depends on** 003

## What is wrong

The CSP in `app/main.py` still allows both. Tailwind, Alpine.js and Chart.js load
from CDNs, and Tailwind's browser build compiles styles at runtime, which needs
`eval`. Those two concessions eat most of the CSP's value against XSS.

There is a second exposure in the same place: if any of the three CDNs were
compromised today, every session in the hotel could be stolen. Vendoring removes
that dependency completely.

## Fix

Vendor all three libraries into `app/static/vendor/`, then tighten the header.

- Tailwind needs a build step — the CLI-compiled stylesheet, not the CDN build.
- Alpine needs its **CSP build** (`@alpinejs/csp`); Alpine attributes such as
  `x-data` do not violate CSP, but evaluating expressions does. Without the CSP
  build this item stays half-finished.
- Then `script-src 'self'` (drop the CDN domains) and `style-src 'self'` — clean
  up any inline `style=` attributes first.

Two moves come with it:

- The shared component classes live in a `<style type="text/tailwindcss">` block
  in `base.html` which the CDN compiles at runtime. With a build step that block
  becomes a real `@layer components` section in the compiled stylesheet. It is a
  copy-paste move, not a rewrite, but it is easy to forget.
- 003 has to land first: `unsafe-inline` cannot leave `script-src` while ~1,400
  lines of Alpine components sit inside `<script>` tags in the templates.

The design-system rules that govern those classes are in
`.claude/rules/frontend.md`; do not restate them here or move them into the
stylesheet's comments.

## Done when

No CSP violations in the browser console on any page, and `tests/test_security.py`
asserts the response header carries no `unsafe-*`.
