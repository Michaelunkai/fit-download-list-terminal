$ErrorActionPreference='Continue'
Set-Location 'F:\study\Windows\Applications\Gaming\Launchers\FitLauncher\Automation\fit-download-list-terminal'
@'
"pathfinder" "Hell is Us" "until then" "goodnight universe" "keeper" "Legacy of Kain"
'@ | py -3 .\tools\fit_download_list.py --launch
exit $LASTEXITCODE
