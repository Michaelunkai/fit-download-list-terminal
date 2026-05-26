# Afirgirl / Fit Launcher Automation — Complete Requested Behavior Specification

This document captures every requested outcome for the `Afirgirl` / `afitgirl` terminal function and the Fit Launcher automation project. It is intentionally written as a full requirement checklist so no part of the request is lost.

## Project location

- Windows project path: `F:\study\Windows\Applications\Gaming\Launchers\FitLauncher\Automation\fit-download-list-terminal`
- WSL project path: `/mnt/f/study/Windows/Applications/Gaming/Launchers/FitLauncher/Automation/fit-download-list-terminal`
- Main PowerShell command file in repo: `Afirgirl.ps1`
- Main Python queue automation: `tools/fit_download_list.py`
- Live Windows PowerShell 5 profile function location: `C:\Users\micha\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1`
- Fit Launcher executable: `F:\backup\windowsapps\installed\Fit Launcher\Fit Launcher.exe`
- Auto-install bridge script: `F:\study\projects\games\DownloadNAutoInstall\windows\fit-launcher\automation\auto-install\path-bridge\scripts\FitLauncherPathBridge.ps1`

## Exact user-facing command model

The user wants to type one command in a Windows PowerShell 5 terminal:

```powershell
Afirgirl "pathfinder" "Hell is Us" "until then" "goodnight universe" "keeper" "Legacy of Kain" "the long dark" "among trees" "Echoes of The End" "REPLACED: Supporter" "tides of tommorow" "forever ago" "i am the beast" "goodnight universe" "Against the Storm" "They Are Billions" "Thronefall" " still wakes the Deep" "the saboteur" "remember me" "killer is dead" "wanted: dead" "gungrave g.o.r.e" "the wonderful 101" "the thechnomaster" "bound by flame" "the council"
```

The function must also support any future command of the same form with any number of quoted or unquoted game names.

## Complete requested outcomes

### 1. Permanent terminal function behavior

The function must permanently exist as a Windows PowerShell 5 command named:

- `Afirgirl`
- `afitgirl` where applicable/aliased by PowerShell case-insensitive lookup

The function must be available from a normal Windows PowerShell 5 terminal without requiring the user to manually import project files.

The function must be hardened in the original/live function location, not only in a test copy.

The function must keep working after reopening PowerShell because it is installed in the active PowerShell 5 profile.

### 2. Immediate application start/restart

Whenever the function is run, it must immediately prepare Fit Launcher for the queue action.

The requested behavior is:

- Start Fit Launcher if it is not already running.
- Restart or refresh Fit Launcher when necessary for a clean queue session.
- Use the real application executable: `F:\backup\windowsapps\installed\Fit Launcher\Fit Launcher.exe`.
- Use as little delay as possible before beginning queue work.
- Avoid slow manual steps.
- Avoid leaving old broken Fit Launcher state blocking the new run.
- Prefer fast, automated interaction over user-visible manual clicking.

### 3. Accept many games in one line

The user must be able to type many game names in a single terminal line.

Required parsing behavior:

- Preserve quoted game names with spaces.
- Treat each quoted item as one intended game query.
- Support duplicate entries without breaking the run.
- Support mixed capitalization.
- Support leading/trailing spaces, such as `" still wakes the Deep"`, by trimming where needed.
- Support punctuation, such as `REPLACED: Supporter`, `wanted: dead`, and `gungrave g.o.r.e`.
- Support misspellings/near names where the app catalog can still resolve them, such as `tides of tommorow`, `i am the beast`, and `the thechnomaster`.
- Do not freeze or corrupt the whole command because one title is misspelled or unavailable.

### 4. Fast add-to-download-list behavior

After receiving the one-liner, the function must add every resolvable game to Fit Launcher’s download list as fast as possible.

Required queue behavior:

- Queue is enabled by default.
- Saved-list/catalog lookup happens automatically.
- Scraping/metadata resolution happens when needed.
- Each game is processed independently.
- A failed game must not stop later games from being processed.
- Unavailable games are skipped immediately or as quickly as safely possible.
- Bad torrents/magnets are skipped after a short bounded metadata timeout.
- The terminal must show real progress/results, not fake success.
- If a game cannot be added, the output must say why where possible.

### 5. No terminal hang or stuck state

The function must never leave the terminal permanently stuck at output like:

```text
Downloads-tab queue results
```

Required anti-hang behavior:

- Run the risky queue step as a managed child process.
- Enforce a bounded queue timeout.
- Kill/stop the child process if it exceeds the timeout.
- Return control to the PowerShell prompt.
- Report a real failure instead of printing fake OK.
- Continue to preserve PowerShell profile and unrelated functions.

### 6. Immediate maximum-speed download policy

Immediately before and after queue work, the function must enforce maximum available Fit Launcher/aria2 download settings.

Requested maximum-speed targets:

- Start downloads immediately after games are added.
- Use the maximum possible speed that the machine/network/trackers/seeds allow.
- Remove speed caps.
- Avoid artificial throttling.
- Keep downloads active while there are queued items.
- When one of the five active downloads stops, finishes, or reaches 100%, aria2 should automatically promote another waiting transfer so the active target returns to five where enough queued transfers remain.
- Rehydrate or activate Fit Launcher manager jobs into aria2 when needed.

Configured policy targets that must be enforced:

- Concurrent downloads: `5` (keep exactly five active download slots whenever at least five queueable unfinished transfers exist)
- Max connections per server: `16`
- Split: `16`
- Max peers: `1000`
- Download speed cap: unlimited / `0`
- Upload/seed ratio and seed time: set so seeding does not delay completion behavior
- Continue/resume downloads: enabled where supported
- Daemon/background download mode: enabled where supported

### 7. Minimum 30 MB/s download request

The user requested that from start to end, as long as downloading is happening, downloads should be nothing less than 30 MB/s.

The intended automation requirement is:

- Do everything under local control to maximize download speed.
- Never intentionally throttle below 30 MB/s.
- Detect/report real live speed when checking downloads.
- Prefer active real downloads, not idle/stalled fake states.
- If speed is below 30 MB/s because of external factors, keep max-speed settings enforced and do not pretend the speed is guaranteed.

Important technical reality that must be preserved in implementation notes:

- The local function can enforce unlimited/max settings.
- The local function cannot physically guarantee 30 MB/s for every torrent/game because real speed depends on seeds, peers, trackers, network path, ISP, disk speed, Fit Launcher internals, and dead/slow torrents.
- Therefore the permanent achievable behavior is: no local cap, maximum configured concurrency/connections, active downloads started, and real speed reporting.

### 8. Real-time download truthfulness

The function must show real download state, not misleading output.

Required behavior:

- Report true queue success/failure.
- Report missing Downloads-tab verification as a failure or skip, not success.
- Report metadata timeouts.
- Report unavailable catalog misses.
- Report active aria2/download state when checked.
- Do not say a game was queued if it was not actually visible/confirmed.
- Do not hide errors that affect a specific title.

### 9. Immediate automatic installation

Every game that reaches 100% download completion must immediately start automatic installation.

Required auto-install behavior:

- `auto_install=true` must be enforced.
- Target automatic installation concurrency is `4` via persisted install-concurrency markers and the running auto-install bridge where Fit Launcher supports it.
- The PathBridge daemon must be running.
- The bridge must be checked before and after queue work.
- Completed downloads must be handed off automatically to the installer path bridge.
- The install handoff must require no manual clicking from the user where automation supports it.
- Installation must continue start-to-finish automatically as far as the Fit Launcher installer/bridge supports.

### 10. Zero-delay installation request

The requested ideal is zero delay between 100% download completion and install start.

The implementation requirement is:

- Minimize delay aggressively.
- Keep the daemon already running so completion events are caught quickly.
- Avoid waiting for a later manual command.
- Avoid requiring a separate user action after download completion.
- Do not intentionally insert sleeps or slow polling where avoidable.

Important technical reality:

- True physical zero delay cannot be guaranteed because the app, file system, Windows scheduling, process startup, antivirus, installer unpacking, and bridge polling/event timing are external.
- The permanent achievable behavior is immediate/automatic handoff with the bridge already active and no deliberate delay.

### 11. Fully automatic install from start to finish

The user requested completely automatic installation from start to finish with no flaws, errors, or stuck states.

The automation must aim to:

- Start install automatically for completed downloads.
- Use existing setup paths/proxy targets correctly.
- Avoid blocking on stale paths.
- Repair/verify bridge state where possible.
- Keep install automation unattended where the installer supports it.
- Surface installer or bridge failures truthfully if they happen.

Important technical reality:

- Some third-party installers can fail, require admin permission, show unexpected prompts, be blocked by antivirus, have corrupt files, or require user choices.
- The automation can enforce and monitor the start/handoff path, but cannot honestly promise every installer from every game will never fail for external reasons.

### 12. Permanent behavior for future commands

The requested behavior must be permanent for future `Afirgirl` runs.

Required permanent changes:

- Patch the active Windows PowerShell 5 profile function.
- Patch the repo copy so the project documents and preserves the hardened version.
- Keep the old fragile behavior from overriding the new function.
- Preserve unrelated PowerShell profile code.
- Keep backups before profile edits.
- Verify the PowerShell profile parser after edits.
- Verify fresh dot-source/load after edits.
- Verify function count so unrelated functions were not removed.
- Commit and push repo changes when project files are updated.

### 13. Any number of games

The function must scale to any number of game arguments as far as practical.

Required behavior:

- Do not hard-code only the tested list.
- Process arguments as an array/list.
- Do not stop the entire run because one game fails.
- Use per-game bounded timeout for metadata resolution.
- Continue to the next game after a miss, timeout, or unavailable title.
- Keep terminal responsive even for long lists.

### 14. Any game name

The user requested support for any games searched in the one-liner.

Required behavior:

- Attempt to resolve every provided query against Fit Launcher/local catalog/search pipeline.
- Add every game that is actually available and queueable.
- Skip games not available in the app.
- Skip dead/unresolvable torrents quickly.
- Continue after skips.
- Report exactly which titles were added, skipped, missing, or blocked.

Important technical reality:

- The function cannot add games that do not exist in the Fit Launcher catalog.
- The function cannot add torrents whose metadata/magnet cannot be resolved.
- The correct behavior for those is fast skip + continue.

### 15. The exact requested test set

The specific one-liner test includes these user-provided search strings:

1. `pathfinder`
2. `Hell is Us`
3. `until then`
4. `goodnight universe`
5. `keeper`
6. `Legacy of Kain`
7. `the long dark`
8. `among trees`
9. `Echoes of The End`
10. `REPLACED: Supporter`
11. `tides of tommorow`
12. `forever ago`
13. `i am the beast`
14. `goodnight universe`
15. `Against the Storm`
16. `They Are Billions`
17. `Thronefall`
18. ` still wakes the Deep`
19. `the saboteur`
20. `remember me`
21. `killer is dead`
22. `wanted: dead`
23. `gungrave g.o.r.e`
24. `the wonderful 101`
25. `the thechnomaster`
26. `bound by flame`
27. `the council`

### 16. Expected handling for the test set

The function must attempt all 27 inputs.

For catalog matches and queueable torrents:

- Save/add to Fit Launcher list.
- Queue in Downloads tab.
- Start/resume download.
- Keep max-speed policy enforced.
- Enable auto-install handoff.

For unavailable titles:

- Skip quickly.
- Continue to the next title.
- Do not fail the whole one-liner.

For metadata timeouts/dead magnets:

- Stop waiting after the configured metadata timeout.
- Mark that title as skipped/failed because metadata could not resolve.
- Continue to the next title.
- Return terminal control at the end.

### 17. Verification requirements

After changes, verification should include:

- PowerShell 5 parser check on the active profile.
- Fresh Windows PowerShell 5 dot-source/load check.
- Function preservation recount.
- Python compile/syntax check for `tools/fit_download_list.py`.
- Bridge PowerShell parser check.
- Confirm `auto_install=true`.
- Confirm PathBridge daemon is running.
- Confirm max-speed settings are enforced.
- Run the exact one-liner or a safe equivalent.
- Confirm the terminal returned to PowerShell.
- Confirm queue/add results were real, not fake.
- Confirm unavailable games were skipped and did not block later games.
- Confirm aria2/download jobs were active where available.
- Commit and push repository documentation/code changes.

### 18. Non-negotiable safety requirements

The function must not:

- Delete unrelated files.
- Rewrite the entire PowerShell profile unnecessarily.
- Remove unrelated profile functions.
- Break unrelated aliases or commands.
- Store secrets in the repository.
- Hang the terminal indefinitely.
- Claim success for unavailable games.
- Claim impossible speed/install guarantees without real verification.

### 19. User-visible output requirements

The user wants concise real terminal output that proves progress.

Output should include:

- Max-speed enforcement started/completed.
- Auto-install bridge enforcement started/completed.
- Exact games being processed.
- Added/queued games.
- Skipped unavailable games.
- Metadata timeout games.
- Real queue failure if any.
- Real download state/speed when checked.
- Final return to PowerShell prompt.

Output should avoid:

- Fake OK messages.
- Endless repeated status spam.
- Blocking forever on one bad title.
- Leaving the user uncertain whether the command finished.

### 20. Definition of success

The project/function satisfies the request when all locally controllable requirements are true:

- `Afirgirl` exists permanently in Windows PowerShell 5.
- The one-line multi-game syntax works.
- Fit Launcher starts/refreshes automatically.
- Every provided title is attempted.
- Every available and queueable game is added/queued.
- Unavailable games are skipped quickly.
- Bad metadata/magnets are skipped quickly.
- Later games still run after earlier failures.
- Downloads are started/resumed where possible.
- Local speed limits are removed and max-speed settings are enforced.
- Download state is reported truthfully.
- `auto_install=true` is enforced.
- PathBridge is running for automatic install handoff.
- The terminal returns to the prompt.
- The repo contains the updated scripts and this requirement document.
- The live bridge prevents concurrent JSON writes from corrupting Fit Launcher config while the daemon and one-shot repair run together.
- The repo is committed and pushed.

## Practical limits that must be stated honestly

The user requested absolute guarantees such as:

- Any game.
- No download below 30 MB/s.
- Zero install delay.
- No flaws or errors ever.
- No stuck state from any reason whatsoever.

The implementation must try to achieve the maximum possible local automation, but these absolute guarantees depend partly on external systems and cannot be honestly promised for all games/torrents/installers.

The correct permanent behavior is therefore:

- Enforce maximum local speed settings.
- Start/resume downloads immediately where possible.
- Keep the auto-install bridge active.
- Skip unavailable/dead games quickly.
- Report real failures.
- Never let one bad game permanently hang the terminal.
- Keep improving the project when a new real blocker is discovered.
