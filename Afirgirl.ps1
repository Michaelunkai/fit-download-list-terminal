# PowerShell 5 hardened wrapper for Fit Launcher Downloads-tab queueing.
# Synced from active Microsoft.PowerShell_profile.ps1.

#   afitgirl "pathfinder" "Hell is Us" "keeper"
#   afitgirl -SavedOnly "keeper"
#
# This wrapper intentionally enforces Fit Launcher's max-speed + auto-install
# bridge before and after queueing so newly completed downloads are picked up
# immediately by the installer daemon.
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
        $outFile = Join-Path $env:TEMP ("fitlauncher_bridge_once_stdout_{0}.log" -f ([guid]::NewGuid().ToString('N')))
        $errFile = Join-Path $env:TEMP ("fitlauncher_bridge_once_stderr_{0}.log" -f ([guid]::NewGuid().ToString('N')))
        $proc = Start-Process -FilePath $ps5 -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$bridgeScript,'-Once') -RedirectStandardOutput $outFile -RedirectStandardError $errFile -NoNewWindow -PassThru
        try {
            if (-not $proc.WaitForExit(90000)) {
                try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
                if (Test-Path -LiteralPath $outFile) { Get-Content -LiteralPath $outFile -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ } }
                if (Test-Path -LiteralPath $errFile) { Get-Content -LiteralPath $errFile -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ } }
                throw 'Fit Launcher speed/auto-install bridge -Once exceeded 90 seconds; killed only the one-shot repair process so PowerShell returns instead of hanging. The background daemon remains active.'
            }
            if (Test-Path -LiteralPath $outFile) { Get-Content -LiteralPath $outFile -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ } }
            if (Test-Path -LiteralPath $errFile) { Get-Content -LiteralPath $errFile -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ } }
            $code = [int]$proc.ExitCode
        }
        finally {
            Remove-Item -LiteralPath $outFile,$errFile -Force -ErrorAction SilentlyContinue
        }
    } else {
        & $ps5 -NoProfile -ExecutionPolicy Bypass -File $bridgeScript
        $code = if ($null -ne $global:LASTEXITCODE) { [int]$global:LASTEXITCODE } else { 0 }
    }
    if ($code -ne 0) {
        throw "Fit Launcher speed/auto-install bridge failed with exit code $code"
    }
}

function Invoke-AfitgirlAria2Rpc {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string] $Method,
        $Params = @(),
        [int] $TimeoutSec = 3
    )

    $configPath = Join-Path $env:APPDATA 'com.fitlauncher.carrotrub\config.json'
    $port = 6899
    $token = $null
    if (Test-Path -LiteralPath $configPath -PathType Leaf) {
        try {
            $cfg = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
            if ($cfg.rpc -and $cfg.rpc.port) { $port = [int]$cfg.rpc.port }
            if ($cfg.rpc -and $cfg.rpc.token) { $token = '' + $cfg.rpc.token }
        } catch {}
    }
    $p = @($Params)
    if ($token) { $p = @('token:' + $token) + $p }
    $body = @{ jsonrpc = '2.0'; id = ('afitgirl-' + [guid]::NewGuid().ToString('N')); method = $Method; params = $p } | ConvertTo-Json -Depth 64
    Invoke-RestMethod -Uri ("http://127.0.0.1:{0}/jsonrpc" -f $port) -Method Post -ContentType 'application/json' -Body $body -TimeoutSec $TimeoutSec
}

function Restart-AfitgirlAria2MaxSpeed {
    [CmdletBinding()]
    param([string] $Reason = 'afitgirl max-speed restart')

    $root = Join-Path $env:APPDATA 'com.fitlauncher.carrotrub'
    $sessionPath = Join-Path $root 'aria2.session'
    $logPath = Join-Path $root 'logs\aria2.log'
    $aria2Exe = 'F:\backup\windowsapps\installed\Fit Launcher\aria2c.exe'
    $bridgeScript = 'F:\study\projects\games\DownloadNAutoInstall\windows\fit-launcher\automation\auto-install\path-bridge\scripts\FitLauncherPathBridge.ps1'
    $ps5 = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $completeHook = Join-Path $root 'fitgirl-complete-hook.cmd'
    if (-not (Test-Path -LiteralPath $root -PathType Container)) { New-Item -ItemType Directory -Force -Path $root | Out-Null }
    if (-not (Test-Path -LiteralPath (Split-Path -Parent $logPath) -PathType Container)) { New-Item -ItemType Directory -Force -Path (Split-Path -Parent $logPath) | Out-Null }
    if (-not (Test-Path -LiteralPath $aria2Exe -PathType Leaf)) { throw "aria2c missing: $aria2Exe" }
    if (Test-Path -LiteralPath $bridgeScript -PathType Leaf) {
        try { Set-Content -LiteralPath $completeHook -Encoding ASCII -Force -Value ('@echo off' + "`r`n" + '"' + $ps5 + '" -NoProfile -ExecutionPolicy Bypass -File "' + $bridgeScript + '" -Once >NUL 2>NUL') } catch {}
    }
    try { [void](Invoke-AfitgirlAria2Rpc -Method 'aria2.saveSession' -Params @() -TimeoutSec 2) } catch {}
    Get-Process -Name aria2c -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 700
    $args = @(
        '--enable-rpc','--rpc-listen-all=false','--rpc-listen-port=6899','--dir=F:\Downloads',
        '--input-file',$sessionPath,'--save-session',$sessionPath,'--save-session-interval=10','--auto-save-interval=10',
        '--continue=true','--allow-overwrite=true','--auto-file-renaming=false','--file-allocation=none','--disk-cache=128M',
        '--max-concurrent-downloads=5','--max-connection-per-server=16','--split=16','--min-split-size=1M',
        '--connect-timeout=8','--timeout=20','--max-tries=0','--retry-wait=2','--listen-port=6881',
        '--bt-max-peers=1000','--bt-request-peer-speed-limit=1K','--enable-dht=true','--enable-peer-exchange=true','--bt-enable-lpd=true',
        '--bt-save-metadata=true','--bt-load-saved-metadata=true','--bt-remove-unselected-file=true','--seed-ratio=0','--seed-time=0',
        '--max-overall-download-limit=0','--max-download-limit=0','--max-overall-upload-limit=0','--max-upload-limit=0',
        '--log',$logPath,'--log-level=warn'
    )
    if (Test-Path -LiteralPath $completeHook -PathType Leaf) { $args += @('--on-download-complete',$completeHook) }
    Start-Process -FilePath $aria2Exe -ArgumentList $args -WindowStyle Hidden | Out-Null
    Start-Sleep -Seconds 2
    Write-Host ("[afitgirl] restarted aria2 max-speed worker: {0}" -f $Reason)
}

function Invoke-AfitgirlDownloadPolicy {
    [CmdletBinding()]
    param(
        [int] $MinimumActive = 5,
        [int] $MinimumTotalSpeedMBps = 30,
        [switch] $Quiet
    )

    $desiredActive = [Math]::Max(5, $MinimumActive)
    $root = Join-Path $env:APPDATA 'com.fitlauncher.carrotrub'
    $configPath = Join-Path $root 'config.json'
    $installConfig = Join-Path $root 'fitgirlConfig\settings\installation\installation.json'

    try {
        if (Test-Path -LiteralPath $configPath -PathType Leaf) {
            $cfg = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
            foreach ($section in @('general','limits','network','bittorrent','rpc')) {
                if ($cfg.PSObject.Properties.Name -notcontains $section -or $null -eq $cfg.$section) {
                    Add-Member -InputObject $cfg -MemberType NoteProperty -Name $section -Value ([pscustomobject]@{})
                }
            }
            $pairs = @(
                @($cfg.general,'concurrent_downloads',$desiredActive),
                @($cfg.general,'folder_exclusion',$true),
                @($cfg.general,'folder_exclusion_cleanup',$false),
                @($cfg.network,'max-connection-per-server',16),
                @($cfg.network,'split',16),
                @($cfg.network,'min-split-size',1048576),
                @($cfg.bittorrent,'enable-dht',$true),
                @($cfg.bittorrent,'max-peers',1000),
                @($cfg.bittorrent,'seed-ratio',0),
                @($cfg.bittorrent,'seed-time',0),
                @($cfg.rpc,'start_daemon',$true),
                @($cfg.rpc,'port',6899)
            )
            foreach ($pair in $pairs) {
                $o = $pair[0]; $n = $pair[1]; $v = $pair[2]
                if ($o.PSObject.Properties.Name -notcontains $n) { Add-Member -InputObject $o -MemberType NoteProperty -Name $n -Value $v } else { $o.$n = $v }
            }
            foreach ($cap in @('max-overall-download','max-overall-upload','max-download','max-upload')) {
                if ($cfg.limits.PSObject.Properties.Name -notcontains $cap) { Add-Member -InputObject $cfg.limits -MemberType NoteProperty -Name $cap -Value $null } else { $cfg.limits.$cap = $null }
            }
            Set-Content -LiteralPath $configPath -Value ($cfg | ConvertTo-Json -Depth 64) -Encoding UTF8 -Force
        }
        if (Test-Path -LiteralPath $installConfig -PathType Leaf) {
            $icfg = Get-Content -LiteralPath $installConfig -Raw | ConvertFrom-Json
            foreach ($pair in @(@('auto_install',$true),@('auto_clean',$false),@('two_gb_limit',$false),@('directx_install',$false),@('microsoftcpp_install',$false),@('max_parallel_installations',4),@('concurrent_installations',4))) {
                $n = $pair[0]; $v = $pair[1]
                if ($icfg.PSObject.Properties.Name -notcontains $n) { Add-Member -InputObject $icfg -MemberType NoteProperty -Name $n -Value $v } else { $icfg.$n = $v }
            }
            Set-Content -LiteralPath $installConfig -Value ($icfg | ConvertTo-Json -Depth 64) -Encoding UTF8 -Force
        }
    } catch {
        if (-not $Quiet) { Write-Host ("[afitgirl] config repair warning: {0}" -f $_.Exception.Message) }
    }

    $opts = @{
        'max-concurrent-downloads' = ('' + $desiredActive)
        'max-connection-per-server' = '16'
        'split' = '16'
        'min-split-size' = '1M'
        'bt-max-peers' = '1000'
        'max-overall-download-limit' = '0'
        'max-download-limit' = '0'
        'max-overall-upload-limit' = '0'
        'max-upload-limit' = '0'
        'lowest-speed-limit' = '0'
        'bt-request-peer-speed-limit' = '1K'
        'continue' = 'true'
        'enable-dht' = 'true'
        'enable-peer-exchange' = 'true'
        'bt-enable-lpd' = 'true'
        'bt-save-metadata' = 'true'
        'bt-load-saved-metadata' = 'true'
        'seed-ratio' = '0'
        'seed-time' = '0'
        'file-allocation' = 'none'
        'disk-cache' = '128M'
        'connect-timeout' = '8'
        'timeout' = '20'
        'max-tries' = '0'
        'retry-wait' = '2'
    }

    $active = @(); $waiting = @(); $stopped = @(); $speedBytes = 0L; $rpcOk = $false
    $ariaProc = Get-CimInstance Win32_Process -Filter "Name='aria2c.exe'" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (($null -eq $ariaProc) -or (('' + $ariaProc.CommandLine) -match '--max-connection-per-server=5|--bt-max-peers=60|--max-concurrent-downloads=2')) {
        Restart-AfitgirlAria2MaxSpeed -Reason 'missing/low-cap aria2 startup arguments'
    }
    try {
        [void](Invoke-AfitgirlAria2Rpc -Method 'aria2.changeGlobalOption' -Params @($opts) -TimeoutSec 3)
        [void](Invoke-AfitgirlAria2Rpc -Method 'aria2.unpauseAll' -Params @() -TimeoutSec 2)
        $active = @((Invoke-AfitgirlAria2Rpc -Method 'aria2.tellActive' -Params @() -TimeoutSec 3).result)
        $waiting = @((Invoke-AfitgirlAria2Rpc -Method 'aria2.tellWaiting' -Params @(0,1000) -TimeoutSec 3).result)
        $stopped = @((Invoke-AfitgirlAria2Rpc -Method 'aria2.tellStopped' -Params @(0,1000) -TimeoutSec 3).result)
        foreach ($item in @($active + $waiting)) {
            if ($item -and $item.gid) {
                try { [void](Invoke-AfitgirlAria2Rpc -Method 'aria2.changeOption' -Params @(('' + $item.gid), $opts) -TimeoutSec 2) } catch {}
                try { [void](Invoke-AfitgirlAria2Rpc -Method 'aria2.unpause' -Params @(('' + $item.gid)) -TimeoutSec 2) } catch {}
            }
        }
        $active = @((Invoke-AfitgirlAria2Rpc -Method 'aria2.tellActive' -Params @() -TimeoutSec 3).result)
        foreach ($item in $active) { if ($item -and $item.downloadSpeed) { try { $speedBytes += [int64]$item.downloadSpeed } catch {} } }
        $rpcOk = $true
    } catch {
        $firstError = $_.Exception.Message
        try {
            Restart-AfitgirlAria2MaxSpeed -Reason ("RPC stalled: {0}" -f $firstError)
            [void](Invoke-AfitgirlAria2Rpc -Method 'aria2.changeGlobalOption' -Params @($opts) -TimeoutSec 5)
            [void](Invoke-AfitgirlAria2Rpc -Method 'aria2.unpauseAll' -Params @() -TimeoutSec 3)
            $active = @((Invoke-AfitgirlAria2Rpc -Method 'aria2.tellActive' -Params @() -TimeoutSec 5).result)
            $waiting = @((Invoke-AfitgirlAria2Rpc -Method 'aria2.tellWaiting' -Params @(0,1000) -TimeoutSec 5).result)
            $stopped = @((Invoke-AfitgirlAria2Rpc -Method 'aria2.tellStopped' -Params @(0,1000) -TimeoutSec 5).result)
            foreach ($item in @($active + $waiting)) {
                if ($item -and $item.gid) {
                    try { [void](Invoke-AfitgirlAria2Rpc -Method 'aria2.changeOption' -Params @(('' + $item.gid), $opts) -TimeoutSec 3) } catch {}
                    try { [void](Invoke-AfitgirlAria2Rpc -Method 'aria2.unpause' -Params @(('' + $item.gid)) -TimeoutSec 3) } catch {}
                }
            }
            $active = @((Invoke-AfitgirlAria2Rpc -Method 'aria2.tellActive' -Params @() -TimeoutSec 5).result)
            $speedBytes = 0L
            foreach ($item in $active) { if ($item -and $item.downloadSpeed) { try { $speedBytes += [int64]$item.downloadSpeed } catch {} } }
            $rpcOk = $true
        } catch {
            if (-not $Quiet) { Write-Host ("[afitgirl] aria2 live policy warning: {0}; restart retry: {1}" -f $firstError,$_.Exception.Message) }
        }
    }

    $speedMB = [Math]::Round(($speedBytes / 1MB), 2)
    $status = if ($rpcOk -and $speedMB -ge $MinimumTotalSpeedMBps) { 'OK' } elseif ($rpcOk) { 'BELOW_TARGET_EXTERNAL_OR_STARTING' } else { 'RPC_PENDING' }
    if (-not $Quiet) {
        Write-Host ("[afitgirl] live download policy: active={0}; waiting={1}; stopped={2}; speed={3} MB/s; target>={4} MB/s; status={5}; min-active-target={6}" -f @($active).Count,@($waiting).Count,@($stopped).Count,$speedMB,$MinimumTotalSpeedMBps,$status,$desiredActive)
    }
    [pscustomobject]@{ Active = @($active).Count; Waiting = @($waiting).Count; Stopped = @($stopped).Count; SpeedMBps = $speedMB; TargetMBps = $MinimumTotalSpeedMBps; Status = $status; MinimumActiveTarget = $desiredActive }
}

function Start-AfitgirlMinuteMonitor {
    [CmdletBinding()]
    param(
        [int] $MinimumActive = 5,
        [int] $MinimumTotalSpeedMBps = 30
    )

    $ps5 = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $profilePath = 'C:\Users\micha\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1'
    $logPath = Join-Path $env:TEMP 'afitgirl-minute-speed-monitor.log'
    if (-not (Test-Path -LiteralPath $ps5 -PathType Leaf)) { throw "Windows PowerShell 5 missing: $ps5" }

    $code = @"
`$ErrorActionPreference = 'Continue'
`$marker = 'afitgirl-minute-speed-monitor'
`$mutex = New-Object System.Threading.Mutex(`$false, 'Global\AfitgirlMinuteSpeedMonitor')
if (-not `$mutex.WaitOne(0)) { return }
try {
    . '$profilePath'
    Add-Content -LiteralPath '$logPath' -Value ((Get-Date -Format s) + ' monitor started; target-active=$MinimumActive target-speed-mbps=$MinimumTotalSpeedMBps') -Encoding UTF8
    while (`$true) {
        try {
            Invoke-FitLauncherDownloadRepair -OnceOnly | Out-Null
            `$s = Invoke-AfitgirlDownloadPolicy -MinimumActive $MinimumActive -MinimumTotalSpeedMBps $MinimumTotalSpeedMBps -Quiet
            Add-Content -LiteralPath '$logPath' -Value ((Get-Date -Format s) + (' active={0} waiting={1} stopped={2} speed={3}MB/s target={4}MB/s status={5}' -f `$s.Active,`$s.Waiting,`$s.Stopped,`$s.SpeedMBps,`$s.TargetMBps,`$s.Status)) -Encoding UTF8
        } catch {
            Add-Content -LiteralPath '$logPath' -Value ((Get-Date -Format s) + ' monitor warning: ' + `$_.Exception.Message) -Encoding UTF8
        }
        Start-Sleep -Seconds 60
    }
} finally {
    try { `$mutex.ReleaseMutex() } catch {}
    try { `$mutex.Dispose() } catch {}
}
"@
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($code))
    Start-Process -FilePath $ps5 -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-EncodedCommand',$encoded) -WindowStyle Hidden | Out-Null
    Write-Host ("[afitgirl] real-time minute monitor active: {0}" -f $logPath)
    return $logPath
}

function ConvertTo-AfitgirlCommandLineArgument {
    param([AllowNull()][string] $Value)
    if ($null -eq $Value) { return '""' }
    if ($Value -notmatch '[\s\"]') { return $Value }
    $escaped = $Value -replace '\\(?=\")','\\' -replace '"','\"'
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
        [int] $MetadataTimeoutSeconds = 8,
        [int] $MinimumActiveDownloads = 5,
        [int] $MinimumTotalSpeedMBps = 30
    )

    $ErrorActionPreference = 'Stop'
    if (-not $Games -or $Games.Count -eq 0) {
        Write-Host 'Usage: afitgirl "GAME 1" "GAME 2" "GAME 3" [-SavedOnly] [-Launch] [-VerifyOnly] [-NoScrape] [-Mode smart|all|first] [-QueueTimeoutSeconds 1800] [-MetadataTimeoutSeconds 8] [-MinimumActiveDownloads 5] [-MinimumTotalSpeedMBps 30]'
        Write-Host 'Default behavior queues to Fit Launcher Downloads, enforces at least 5 active slots where 5+ queueable games exist, removes local speed caps, starts a minute speed monitor, enforces auto-install, and returns to PowerShell on timeout instead of hanging.'
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

    Write-Host '[afitgirl] enforcing 5 live download slots + 4-install auto-install bridge before queue update'
    Invoke-FitLauncherDownloadRepair -OnceOnly
    Start-AfitgirlMinuteMonitor -MinimumActive $MinimumActiveDownloads -MinimumTotalSpeedMBps $MinimumTotalSpeedMBps | Out-Null
    Invoke-AfitgirlDownloadPolicy -MinimumActive $MinimumActiveDownloads -MinimumTotalSpeedMBps $MinimumTotalSpeedMBps | Out-Null

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
        Invoke-AfitgirlDownloadPolicy -MinimumActive $MinimumActiveDownloads -MinimumTotalSpeedMBps $MinimumTotalSpeedMBps | Out-Null
        Start-AfitgirlMinuteMonitor -MinimumActive $MinimumActiveDownloads -MinimumTotalSpeedMBps $MinimumTotalSpeedMBps | Out-Null
        if ($code -ne 0) { throw "fit_download_list.py failed with exit code $code" }
        Write-Host '[afitgirl] OK: queued/saved games are protected by 5-active-download policy, 4-install auto-install markers, real minute speed logging, unlimited aria2 settings, and the auto-install daemon.'
        $global:LASTEXITCODE = 0
    }
    finally {
        Pop-Location
    }
}

Set-Alias -Name Afirgirl -Value afitgirl -Scope Global

# Profile now defines the hardened afitgirl wrapper inline so it can enforce timeout-return, max-speed, and auto-install before any external helper overrides it.
# . 'F:\study\Windows\Applications\Gaming\Launchers\FitLauncher\Automation\fit-download-list-terminal\Afirgirl.ps1'
