# Agent instructions

This project builds, tests and runs on a remote target through `perch`
(`perch --help`), never locally.

- **Never build or run this project's code locally.** Only the target can
  compile and run it - use `perch build` / `perch test` / `perch run` /
  `perch exec <cmd>`.
- **This workspace is the source of truth.** The target's copy is derived
  and disposable - the mirror deletes, so a file removed here is removed
  there too on the next sync.
- **Target-side output that matters comes back with `perch pull`.**
  Anything generated on the target and not pulled (or listed under
  `[artifacts]` in `.perch.toml`) is lost on the next sync.
