# Sifty — Architecture

This document explains *why* Sifty is shaped the way it is. For day-to-day rules
see [CLAUDE.md](../CLAUDE.md); for usage see [README.md](../README.md).

## Design goals

1. **Safe by construction.** A maintenance tool that can delete files must make
   destruction the hard path, not the default. Mistakes should be recoverable.
2. **Testable without a real Windows victim.** Core logic runs against sandboxes,
   so we can iterate fast and prove safety on any machine.
3. **CLI now, GUI later, no rewrite.** Logic lives in plain functions; the CLI is
   a thin shell over them. A future GUI/TUI imports the same functions.
4. **Private AI.** The AI is local (Ollama) and sees only metadata. No file
   contents and nothing personal leave the machine.

## Layered structure

```text
            ┌─────────────────────────────────────────┐
   user →   │ cli.py (Typer)  — arg parsing, printing  │   thin
            ├─────────────────────────────────────────┤
            │ commands/*.py   — capability logic       │   testable core
            │   junk · disk · apps · updates · organize │
            ├──────────────────┬──────────────────────┤
            │ safety.py        │ console.py · config.py │   shared infra
            │ (the gatekeeper) │                        │
            ├──────────────────┴──────────────────────┤
            │ ai/  — advisory only, degrades to no-op   │   optional
            └─────────────────────────────────────────┘
```

Each `commands/*.py` module follows the same split:

- **Core functions** — pure-ish, return data (`scan() -> list[CategoryScan]`,
  `find_duplicates() -> dict`, `plan_organization() -> list[Move]`). These are
  what the tests and any future GUI call.
- **`*_cmd` Typer handlers** — parse options, call the core, render via Rich,
  handle the dry-run/confirm flow. Never contain business logic worth testing.

## The safety model (the heart of the system)

All destruction funnels through one function so there is a single place to audit
and a single place that can refuse. `safety.trash()`:

1. Calls `assert_safe()` → `is_protected()`.
2. If dry-run, returns without touching disk.
3. Otherwise sends the path to the Recycle Bin and appends to the audit log.

`is_protected()` uses **two tiers of roots** because "protect the whole drive"
and "protect the Windows directory" need different rules:

| Tier | Examples | Rule |
|---|---|---|
| Contents-protected | `C:\Windows`, `Program Files`, `Program Files (x86)`, `ProgramData`, plus user `extra_protected_paths` | Refuse the root, anything inside it, or any ancestor of it. |
| Self-protected | drive root (`C:\`), user profile root | Refuse only the root itself (or an ancestor). Contents are deletable — otherwise the whole disk is off-limits. |

Callers that legitimately need to delete inside a contents-protected root pass
`allow_subtrees` to vouch for a specific path (e.g. junk cleaning passes
`C:\Windows\Temp`). This keeps the broad denylist strict while permitting the few
known-safe carve-outs.

**Invariant:** the only deletion primitive in the codebase is `safety.trash()`.
Anything else (`os.remove`, `shutil.rmtree`, …) is a bug.

## Capability notes

- **junk** — categories are data (`JunkCategory`) built from the environment, each
  with `roots` and an `allow_subtrees` carve-out. Scanning measures sizes; cleaning
  trashes top-level entries. The Downloads-installers category is config-gated off
  by default (those files are often wanted).
- **disk** — `psutil` for volumes; size-then-SHA-256 two-pass for duplicates (hash
  only files that share a size, so most files are never hashed).
- **apps** — reads the registry Uninstall + Run keys via `winreg` (read-only, no
  admin needed) and the Startup folder; uninstalls shell out to `winget`.
- **updates** — `winget` has no stable machine output, so we parse its fixed-column
  table by header offsets. This is the most brittle code in the repo and is the
  reason `test_updates.py` exists.
- **organize** — plans `(src → dest)` moves and previews them; moves are reversible
  (into subfolders) so they don't go through the Recycle Bin, but still default to
  dry-run. `_unique_dest()` avoids clobbering.

## AI layer

`ai/client.py` wraps the Ollama HTTP API. `is_available()` is checked before every
use so a missing/stopped Ollama degrades to "no AI" rather than an error.
`ai/advisor.py` builds prompts from **metadata only** and is the sole place prompts
live. The AI never receives a deletion capability — commands act, the AI advises.

## Testing strategy

- `pyproject.toml` sets `pythonpath = ["src"]` so tests import `sifty` without an
  install step.
- Safety/junk tests `monkeypatch` the protected-root environment variables and
  `Path.home`, then build fixtures under `tmp_path`. This makes the
  Windows-specific path logic deterministic and runnable on any OS.
- `send2trash` is monkeypatched in tests so nothing is ever really deleted.
- The fragile winget parser is tested against a captured sample table.

## Extension points

- **New capability** → new `commands/<name>.py` with the core/handler split, wired
  in `cli.py`. (`/add-command-module` scaffolds this.)
- **New junk source** → a `JunkCategory` in `junk.py` with its `allow_subtrees`.
  (`/new-junk-category`.)
- **GUI** → import `commands.*` core functions; no logic needs to move.
- **Packaging** → PyInstaller single-file exe. (`/package-exe`.)
