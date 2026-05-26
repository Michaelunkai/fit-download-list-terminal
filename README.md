# Fit Download List Terminal

A small terminal app for adding one or many typed game names to Fit Launcher's real Downloads tab used by:

`F:\backup\windowsapps\installed\Fit Launcher\Fit Launcher.exe`

It reads Fit Launcher's local search database, finds matching games, appends them to `games_to_download.json`, then calls Fit Launcher's own Tauri `dm_add_torrent_job` command so the games appear in the real Downloads tab. It also creates timestamped backups and verifies both saved-list and Downloads-manager state.

## What it does

- Accepts a single line containing as many game names as you want.
- Preserves quoted names with spaces, for example: `"Hell is Us" "goodnight universe"`.
- If the line contains instructions before the game list, only the final trailing quoted block is treated as games, for example: `please add these "GAME 1" "GAME 2" "GAME 3"` uses only `GAME 1`, `GAME 2`, and `GAME 3`.
- Searches Fit Launcher's local database at:
  - `C:\Users\micha\AppData\Roaming\com.fitlauncher.carrotrub\sitemaps\search.db`
- Updates the official download-list collection:
  - `C:\Users\micha\AppData\Roaming\com.fitlauncher.carrotrub\library\collections\games_to_download.json`
- Queues torrent jobs through Fit Launcher's real Downloads manager using WebView2/Tauri commands (`list_torrent_files`, then `dm_add_torrent_job`).
- Makes a backup before writing, named like:
  - `games_to_download.backup-YYYYMMDD-HHMMSS.json`
- Skips duplicates instead of adding the same title twice.
- Automatically restarts Fit Launcher with a local WebView2 debug port when needed so the real manager command can be called.
- Can launch Fit Launcher after updating with `--launch`.

## Prerequisites

- Windows with Python 3 installed.
- Existing Fit Launcher data folder for `com.fitlauncher.carrotrub`.
- Fit Launcher has already built/refreshed its search database (`search.db`).
- Run from a normal Windows terminal/PowerShell. WSL can inspect the files, but this script is intended for Windows paths and environment variables.
- Python package `websocket-client` for the default real-Downloads-tab backend.

Install the only third-party dependency if missing:

```powershell
py -3 -m pip install websocket-client
```

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


### Permanent PowerShell 5 command: Afirgirl

The repository includes `Afirgirl.ps1`, installed into the Windows PowerShell 5 profile as:

```powershell
Afirgirl "pathfinder" "Hell is Us" "keeper"
```

PowerShell passes each quoted title safely as one argument, so names with spaces work. The function calls `tools\fit_download_list.py`, opens Fit Launcher with WebView2 debugging when needed, adds queueable matches through the real Fit Launcher Downloads manager, saves state with `dm_save_now`, and verifies the Downloads tab. Existing visible downloads are detected and skipped instead of restarted or deleted.

Notes:

- `tides of tommorow` is typo-corrected to `Tides of Tomorrow`.
- `i am the beast` is typo-corrected to `I Am Your Beast`.
- `forever ago` is not currently present in the local Fit Launcher/FitGirl search catalog, so it is reported as no catalog match.
- The old `Pathfinder Kingmaker` FitGirl entry exposes a legacy magnet that Fit Launcher WebView cannot resolve reliably; the script keeps it in the saved list and continues queueing the other Pathfinder entries instead of blocking the whole run.

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
- Real Fit Launcher Downloads-manager torrent jobs.
- Timestamped backup next to the JSON file.
- Terminal summary showing each added/already-present title, each queued Downloads-manager job, and final verification.

## Important files

- `tools/fit_download_list.py` — main script/app entry point.
- `README.md` — setup and usage guide.
- `.gitignore` — ignores caches, logs, local backups, and build outputs.
- `artifacts/inspection/` — non-secret inspection scripts/logs used while building this project.

## Troubleshooting

- **Search DB not found**: open Fit Launcher once and let it refresh the catalog, then retry.
- **Game not found**: search for a shorter phrase, or use `--mode all` to see/add all partial matches.
- **Fit Launcher is already open and does not show new entries**: rerun without `--no-restart-debug`; the script restarts Fit Launcher with a local WebView2 debug port and calls the real manager command.
- **`websocket-client` missing**: run `py -3 -m pip install websocket-client`.
- **A torrent says metadata timeout**: Fit Launcher could not obtain the torrent file list from the magnet. Retry later, or use a fuller magnet/link if FitGirl only exposes a bare info-hash magnet.
- **Permission error**: close Fit Launcher and any editor holding `games_to_download.json`, then rerun the command.
- **Wrong user profile**: pass explicit paths:

```powershell
python .\tools\fit_download_list.py --db "C:\Users\micha\AppData\Roaming\com.fitlauncher.carrotrub\sitemaps\search.db" --download-list "C:\Users\micha\AppData\Roaming\com.fitlauncher.carrotrub\library\collections\games_to_download.json" --line '"keeper"'
```
