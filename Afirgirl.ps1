# PowerShell 5 wrapper for Fit Launcher Downloads-tab queueing.
# Usage:
#   Afirgirl "pathfinder" "Hell is Us" "keeper"
function Afirgirl {
    [CmdletBinding()]
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]] $Games
    )
    $script = 'F:\study\Windows\Applications\Gaming\Launchers\FitLauncher\Automation\fit-download-list-terminal\tools\fit_download_list.py'
    if (-not (Test-Path -LiteralPath $script)) {
        throw "Fit download script not found: $script"
    }
    $py = Join-Path $env:WINDIR 'py.exe'
    if (-not (Test-Path -LiteralPath $py)) { $py = 'py.exe' }
    if (-not $Games -or $Games.Count -eq 0) {
        & $py -3 $script
        return
    }
    & $py -3 $script @Games
}
