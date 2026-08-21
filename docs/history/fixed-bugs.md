<a id="fixed-bugs-for-the-record"></a>

# Fixed bugs (for the record)

The first defects, found by using the app rather than auditing it. Index:
`docs/history/README.md`.

- ~~The manager rate override did not work on walk-in reservations~~ —
  `nightly_rate` was added to `QuickBookingCreate` and moved into the `common`
  object in `new_reservation.html`. Regression test:
  `tests/test_reservations.py::test_walk_in_honours_a_nightly_rate_override`.
- ~~The rooms page could lose current guests once there were more than 100
  reservations~~ — an `order=asc` option was added to the reservation search;
  `rooms.html` now sends separate, naturally bounded queries for "occupied"
  (bounded by room count) and "upcoming" (bounded by `date_from` plus ascending
  order).
- ~~The `next` parameter on login was an open-redirect risk~~ — only relative
  paths starting with `/` (and not `//`) are accepted now.
- ~~Toast notifications never drew an icon~~ — the icon was chosen with three
  `<template x-if>` elements nested inside the `<svg>`. SVG is foreign content
  to the HTML parser, so those templates have no `.content` and Alpine threw
  `Cannot read properties of undefined (reading 'cloneNode')` on every page
  load. The host now binds `<path :d="iconPath(t.type)">`.
- ~~The settings page advertised an 8-character password policy~~ — the real
  rule in `app/schemas/auth.py` is 10 characters plus upper case, lower case
  and a digit, so a valid-looking password was rejected by the server. The page
  now shows a live checklist mirroring `_strong_enough()`.
- ~~Editing the CSS or JS did not reach the browser~~ — `/static` is served
  with a long cache and the templates linked the files without a version, so a
  stale `app.css` could persist. Both now carry `?v={{ asset_version }}`.
