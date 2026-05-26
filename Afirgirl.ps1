# PowerShell 5 hardened wrapper for Fit Launcher Downloads-tab queueing.
# Usage: afitgirl "pathfinder" "Hell is Us" "keeper"
# Queue-first by default; use -SavedOnly to avoid downloader side effects.

function Invoke-FitLauncherDownloadRepair {
    [CmdletBinding()]
    param(
        [switch] $OnceOnly
    )

    $bridgeScript = 'F:\study\projects\games\DownloadNAutoInstall\windows\fit-launcher\automation\auto-install\path-bridge\scripts\FitLauncherPathBridge.ps1'
    $ps5 = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    if (-not (Test-Path -LiteralPath $bridgeScript -PathType Leaf)) {
        throw "Missing Fit Launcher auto-install bridge script: $bridgeScript"
    }
    if (-not (Test-Path -LiteralPath $ps5 -PathType Leaf)) {
        throw "Windows PowerShell 5 missing: $ps5"
    }

    $daemon = @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*FitLauncherPathBridge.ps1*' -and $_.CommandLine -like '*-Daemon*' })
    if ($daemon.Count -eq 0) {
        Start-Process -FilePath $ps5 -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',$bridgeScript,'-Daemon') -WindowStyle Hidden | Out-Null
        Start-Sleep -Seconds 2
    }

    if ($OnceOnly) {
        & $ps5 -NoProfile -ExecutionPolicy Bypass -File $bridgeScript -Once
    } else {
        & $ps5 -NoProfile -ExecutionPolicy Bypass -File $bridgeScript
    }
    $code = if ($null -ne $global:LASTEXITCODE) { [int]$global:LASTEXITCODE } else { 0 }
    if ($code -ne 0) {
        throw "Fit Launcher speed/auto-install bridge failed with exit code $code"
    }
}

function ConvertTo-AfitgirlCommandLineArgument {
    param([AllowNull()][string] $Value)
    if ($null -eq $Value) { return '""' }
    if ($Value -notmatch '[\s"]') { return $Value }
    $escaped = $Value -replace '\\(?=")','\\' -replace '"','\"'
    return '"' + $escaped + '"'
}

function Invoke-AfitgirlPythonProcess {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string] $FilePath,
        [Parameter(Mandatory=$true)][string[]] $Arguments,
        [Parameter(Mandatory=$true)][string] $WorkingDirectory,
        [int] $TimeoutSeconds = 900
    )

    $outFile = Join-Path $env:TEMP ("afitgirl_stdout_{0}.log" -f ([guid]::NewGuid().ToString('N')))
    $errFile = Join-Path $env:TEMP ("afitgirl_stderr_{0}.log" -f ([guid]::NewGuid().ToString('N')))
    $argText = (($Arguments | ForEach-Object { ConvertTo-AfitgirlCommandLineArgument $_ }) -join ' ')
    $proc = Start-Process -FilePath $FilePath -ArgumentList $argText -WorkingDirectory $WorkingDirectory -NoNewWindow -RedirectStandardOutput $outFile -RedirectStandardError $errFile -PassThru
    try {
        if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
            try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
            if (Test-Path -LiteralPath $outFile) { Get-Content -LiteralPath $outFile -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ } }
            if (Test-Path -LiteralPath $errFile) { Get-Content -LiteralPath $errFile -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ } }
            throw "afitgirl queue command timed out after $TimeoutSeconds seconds; returned control to PowerShell and reran speed/auto-install repair."
        }
        $stdout = if (Test-Path -LiteralPath $outFile) { Get-Content -LiteralPath $outFile -ErrorAction SilentlyContinue } else { @() }
        $stderr = if (Test-Path -LiteralPath $errFile) { Get-Content -LiteralPath $errFile -ErrorAction SilentlyContinue } else { @() }
        $stdout | ForEach-Object { Write-Host $_ }
        $stderr | ForEach-Object { Write-Host $_ }
        $code = [int]$proc.ExitCode
        if ($code -eq 0 -and (($stderr -join "`n") -match 'fit_download_list\.py: error:|Traceback|RuntimeError|failed with exit code')) {
            $code = 4
        }
        $global:LASTEXITCODE = $code
        return $code
    }
    finally {
        Remove-Item -LiteralPath $outFile,$errFile -Force -ErrorAction SilentlyContinue
    }
}

function afitgirl {
    [CmdletBinding()]
    param(
        [Parameter(Position=0, ValueFromRemainingArguments=$true)]
        [string[]] $Games,
        [switch] $SavedOnly,
        [switch] $Queue,
        [switch] $Launch,
        [switch] $VerifyOnly,
        [switch] $NoScrape,
        [ValidateSet('smart','all','first')]
        [string] $Mode = 'smart',
        [int] $QueueTimeoutSeconds = 1800,
        [int] $MetadataTimeoutSeconds = 8
    )

    $ErrorActionPreference = 'Stop'
    if (-not $Games -or $Games.Count -eq 0) {
        Write-Host 'Usage: afitgirl "GAME 1" "GAME 2" "GAME 3" [-SavedOnly] [-Launch] [-VerifyOnly] [-NoScrape] [-Mode smart|all|first] [-QueueTimeoutSeconds 1800] [-MetadataTimeoutSeconds 8]'
        Write-Host 'Default behavior queues to Fit Launcher Downloads, maximizes aria2 speed, keeps the anti-stall daemon running, enforces auto-install, and returns to PowerShell on timeout instead of hanging.'
        $global:LASTEXITCODE = 2
        return
    }

    $repo = 'F:\study\Windows\Applications\Gaming\Launchers\FitLauncher\Automation\fit-download-list-terminal'
    $script = Join-Path $repo 'tools\fit_download_list.py'
    $db = 'C:\Users\micha\AppData\Roaming\com.fitlauncher.carrotrub\sitemaps\search.db'
    $downloadList = 'C:\Users\micha\AppData\Roaming\com.fitlauncher.carrotrub\library\collections\games_to_download.json'
    $fitLauncher = 'F:\backup\windowsapps\installed\Fit Launcher\Fit Launcher.exe'

    foreach ($required in @($repo,$script,$db,$downloadList,$fitLauncher)) {
        if (-not (Test-Path -LiteralPath $required)) { throw "Missing required Fit Launcher path: $required" }
    }

    $py = Get-Command py.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $py) { throw 'py.exe was not found. Install/repair Windows Python launcher first.' }

    Write-Host '[afitgirl] enforcing max-speed downloads + immediate auto-install bridge before queue update'
    Invoke-FitLauncherDownloadRepair -OnceOnly

    $cli = @('-3', $script, '--db', $db, '--download-list', $downloadList, '--fit-launcher', $fitLauncher, '--mode', $Mode, '--metadata-timeout-ms', ([string]([Math]::Max(1000, $MetadataTimeoutSeconds * 1000))))
    if ($VerifyOnly) { $cli += '--verify-only' }
    if ($NoScrape) { $cli += '--no-scrape' }
    if ($SavedOnly) { $cli += '--no-queue' }
    if ($Launch) { $cli += '--launch' }
    $line = (($Games | ForEach-Object { '"' + (($_ -replace '"','\"')) + '"' }) -join ' ')
    $cli += @('--line', $line)

    Write-Host ("[afitgirl] Games: {0}" -f (($Games | ForEach-Object { '"' + $_ + '"' }) -join ' '))
    Write-Host ("[afitgirl] Mode={0}; Queue={1}; SavedOnly={2}; Launch={3}; VerifyOnly={4}; NoScrape={5}" -f $Mode,(-not [bool]$SavedOnly),([bool]$SavedOnly),([bool]$Launch),([bool]$VerifyOnly),([bool]$NoScrape))
    Push-Location -LiteralPath $repo
    try {
        $code = Invoke-AfitgirlPythonProcess -FilePath $py.Source -Arguments $cli -WorkingDirectory $repo -TimeoutSeconds $QueueTimeoutSeconds
        Write-Host '[afitgirl] rechecking max-speed policy, anti-stall resume, and auto-install handoff after queue update'
        Invoke-FitLauncherDownloadRepair -OnceOnly
        if ($code -ne 0) { throw "fit_download_list.py failed with exit code $code" }
        Write-Host '[afitgirl] OK: queued/saved games are protected by max-speed aria2 settings and the auto-install daemon.'
        $global:LASTEXITCODE = 0
    }
    finally {
        Pop-Location
    }
}

Set-Alias -Name Afirgirl -Value afitgirl -Scope Global
