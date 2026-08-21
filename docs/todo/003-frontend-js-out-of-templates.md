# 003 — Move the Alpine components out of the templates

**Kind** refactor · **Size** days · **Depends on** nothing

## What is wrong

Roughly 1,400 lines of Alpine components live inside `<script>` tags across ten
templates: unlinted, untyped, untested, and invisible to `ruff` or any other
tool. The last three UI defects were all in that code, and none of them could
have been caught by anything but opening the page.

## Fix

Move each component to `app/static/js/pages/<page>.js` and reference it from the
template. No build step is needed for this — it is a move, not a rewrite.

Two consequences make it worth doing on its own:

- It is what unblocks 002. `unsafe-inline` cannot leave `script-src` while the
  components are in the HTML.
- The components become lintable and testable for the first time.

`app/templates/CLAUDE.md` points at this file as the reason that directory is
the way it is; update it when the move happens. Everything about how the
frontend is written — the `api()` helper, the component vocabulary, the popover
rules — is in `.claude/rules/frontend.md` and moves with the code unchanged.

## Done when

No `<script>` block in `app/templates/**` contains an Alpine component, every
page still works (the front desk, the rooms board and the booking wizard are the
ones with real logic), and the extracted files are covered by whatever linting
the project runs on JavaScript by then.
