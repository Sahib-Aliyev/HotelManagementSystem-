# Templates and static assets

Server-rendered Jinja2 with Alpine.js components inline in `<script>` blocks;
`base.html` holds the shared component vocabulary and `partials/` the macros.

- The rules for this directory live in `.claude/rules/frontend.md` (design
  system, popovers, Alpine pitfalls). Read it before restyling anything.
- Why a rule exists: `docs/history/` — the room-card menu and the sidebar each
  took three passes, recorded in `docs/history/review-2026-08-17.md`.
- Moving these components into `app/static/js/pages/*.js` is what unblocks a
  strict CSP; see `docs/todo/003-frontend-js-out-of-templates.md`.
