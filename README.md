# Fit Download List Terminal

A small terminal app for adding one or many typed game names to the Fit Launcher download list used by:

`F:\backup\windowsapps\installed\Fit Launcher\Fit Launcher.exe`

It reads Fit Launcher's local search database, finds matching games, appends them to `games_to_download.json`, creates a timestamped backup, and verifies that every requested game/query is present afterward.

## What it does

- Accepts a single line containing as many game names as you want.
- Preserves quoted names with spaces, for example: `"Hell is Us" "goodnight universe"`.
- Searches Fit Launcher's local database at:
  - `C:\Users\micha\AppData\Roaming\com.fitlauncher.carrotrub\sitemaps\search.db`
- Updates the official download-list collection:
  - `C:\Users\micha\AppData\Roaming\com.fitlauncher.carrotrub\library\collections\games_to_download.json`
- Makes a backup before writing, named like:
  - `games_to_download.backup-YYYYMMDD-HHMMSS.json`
- Skips duplicates instead of adding the same title twice.
- Can launch Fit Launcher after updating with `--launch`.

## Prerequisites

- Windows with Python 3 installed.
- Existing Fit Launcher data folder for `com.fitlauncher.carrotrub`.
- Fit Launcher has already built/refreshed its search database (`search.db`).
- Run from a normal Windows terminal/PowerShell. WSL can inspect the files, but this script is intended for Windows paths and environment variables.

No third-party Python packages are required.

## Install / setup

Clone or download this repository, then open PowerShell in the repo folder:

```powershell
cd "F:\study\Windows\Applications\Gaming\Launchers\FitLauncher\Automation\fit-download-list-terminal"
python --version
```

If `python` is not found, install Python from Microsoft Store or python.org, or replace `python` with `py -3`.

## Usage

### Interactive mode

```powershell
python .\tools\fit_download_list.py
```

Then type one line, for example:

```text
"pathfinder" "Hell is Us" "until then" "goodnight universe" "keeper" "Legacy of Kain"
```

### One command

```powershell
python .\tools\fit_download_list.py --line '"pathfinder" "Hell is Us" "until then" "goodnight universe" "keeper" "Legacy of Kain"'
```

### Update and launch Fit Launcher

```powershell
python .\tools\fit_download_list.py --launch --line '"Hell is Us" "keeper"'
```

### Verification only

```powershell
python .\tools\fit_download_list.py --verify-only --line '"Hell is Us" "keeper"'
```

## Matching behavior

Default mode is `--mode smart`:

- If a typed game has one exact normalized title match, only that exact title is added.
- If no exact title exists, all title matches are added.

Examples from the verification run:

- `keeper` adds the exact game `Keeper`.
- `pathfinder` has no exact single title, so it adds all matching Pathfinder entries.
- `Legacy of Kain` has several matching entries, so it adds all matching Legacy of Kain entries.

Other modes:

- `--mode all`: add every matching title.
- `--mode first`: add only the shortest/first matching title.

## Inputs and outputs

Input:

- One typed line of game names.
- Local Fit Launcher `search.db`.

Output:

- Updated `games_to_download.json` in Fit Launcher's data folder.
- Timestamped backup next to that JSON file.
- Terminal summary showing each added/already-present title and final verification.

## Important files

- `tools/fit_download_list.py` — main script/app entry point.
- `README.md` — setup and usage guide.
- `.gitignore` — ignores caches, logs, local backups, and build outputs.
- `artifacts/inspection/` — non-secret inspection scripts/logs used while building this project.

## Troubleshooting

- **Search DB not found**: open Fit Launcher once and let it refresh the catalog, then retry.
- **Game not found**: search for a shorter phrase, or use `--mode all` to see/add all partial matches.
- **Fit Launcher is already open and does not show new entries**: close and reopen Fit Launcher, or use `--launch` after updating.
- **Permission error**: close Fit Launcher and any editor holding `games_to_download.json`, then rerun the command.
- **Wrong user profile**: pass explicit paths:

```powershell
python .\tools\fit_download_list.py --db "C:\Users\micha\AppData\Roaming\com.fitlauncher.carrotrub\sitemaps\search.db" --download-list "C:\Users\micha\AppData\Roaming\com.fitlauncher.carrotrub\library\collections\games_to_download.json" --line '"keeper"'
```
