# Sifty

An AI-assisted Windows maintenance CLI that **sifts the junk from the keep** —
clean junk, analyze disks, manage apps, apply updates, and organize files. The AI
runs **locally** via [Ollama], so nothing leaves your machine, and it only ever
sees file *metadata* (names, sizes, paths), never file contents.

## Safety first

Sifty can delete files and change system state, so it is built to be hard to
misuse:

- **Dry-run by default** — every destructive command previews what it would do.
  Real changes need an explicit `--apply`.
- **Recycle Bin, never permanent delete** — all removals go through one `trash()`
  function backed by Send2Trash.
- **Protected paths** — `C:\Windows`, `Program Files`, `ProgramData`, the drive
  root and your profile root are refused even with `--apply --yes`.
- **Audit log** — every applied deletion is recorded in
  `%APPDATA%\sifty\audit.log`.

## Install (development)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

This adds a `sifty` command (on PATH inside the venv at
`.\.venv\Scripts\sifty.exe`).

## Usage

```powershell
sifty doctor                 # check admin rights, winget, Ollama
sifty version

# Junk
sifty junk scan              # show reclaimable space per category
sifty junk clean             # preview removal (dry-run)
sifty junk clean --apply     # send junk to the Recycle Bin (asks first)

# Disk
sifty disk volumes           # used/free/total per volume
sifty disk analyze C:\Users  # biggest folders/files under a path
sifty disk duplicates D:\    # find duplicate files and wasted space

# Apps
sifty apps list --by-size    # installed apps, largest first
sifty apps startup           # programs that launch at startup
sifty apps uninstall "App"   # uninstall via winget (preview, then --apply)

# Updates
sifty update check           # list available updates (winget)
sifty update apply           # upgrade everything (asks first)

# Organize files
sifty organize preview C:\Users\you\Downloads --by type
sifty organize apply   C:\Users\you\Downloads --by date

# AI (requires Ollama running)
sifty ai status
sifty ai ask "what can I safely delete on my C drive?" --path C:\
```

Some operations (Windows temp, update cache, certain uninstalls) need an
**Administrator** terminal — `sifty doctor` tells you if you're elevated.

## AI setup (optional)

1. Install [Ollama] and start it.
2. Pull the configured model: `ollama pull qwen2.5:3b`.
3. `sifty ai status` should report "running".

Configure the host/model in `%APPDATA%\sifty\config.toml`:

```toml
[ai]
host = "http://localhost:11434"
model = "qwen2.5:3b"

[safety]
extra_protected_paths = ["D:\\Important"]

[junk]
include_downloads_installers = false
```

## Architecture

```text
src/sifty/
├── cli.py            # Typer entry point, wires command groups
├── config.py         # TOML config + %APPDATA% dir
├── safety.py         # ★ protected paths, dry-run guard, trash()
├── console.py        # shared Rich console + helpers
├── commands/         # junk, disk, apps, updates, organize, ai_group
└── ai/               # client.py (Ollama), advisor.py (prompts)
```

The command modules are the engine. A future GUI can call the same functions
(e.g. `junk.scan`, `disk.find_duplicates`) without a rewrite.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

The safety guardrails and the fragile winget parser are the most heavily tested.

[Ollama]: https://ollama.com
