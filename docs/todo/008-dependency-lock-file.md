# 008 — A lock file with hashes

**Kind** dependency · **Size** hours · **Depends on** nothing

## What is wrong

`requirements.txt` pins direct dependencies but not transitive ones, so two
installs a month apart can produce different trees and neither is recorded. There
is no hash pinning either, so an install trusts whatever the index serves.

## Fix

`uv` or `pip-tools` to compile a lock file with hashes from
`requirements.txt`, then install from the lock in CI and in the Dockerfile.

Already done, do not redo: `pip-audit` runs on every push
(`.github/workflows/ci.yml`), advisory rather than blocking, so a new CVE in a
pinned dependency is visible without failing an unrelated change. Consider
Dependabot on top of the lock file rather than instead of it.

## Done when

CI and `Dockerfile` install from the lock file, `pip-audit` still runs, and a
fresh clone produces byte-identical installed versions.
