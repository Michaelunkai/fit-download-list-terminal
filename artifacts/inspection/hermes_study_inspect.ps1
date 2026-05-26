$ErrorActionPreference='SilentlyContinue'
Write-Host '--- study dirs ---'
$base='F:\study'
if(Test-Path $base){
  Get-ChildItem -Path $base -Directory -Recurse -Depth 8 | Select-Object -First 300 FullName | ForEach-Object {$_.FullName}
} else { Write-Host 'NO_STUDY' }
Write-Host '--- fit launcher tree ---'
$fit='F:\backup\windowsapps\installed\Fit Launcher'
if(Test-Path $fit){
  Get-ChildItem -Path $fit -Force | Select-Object Mode,Length,LastWriteTime,FullName | Format-List
  Write-Host '--- likely data/config under app ---'
  Get-ChildItem -Path $fit -Recurse -Force -Include *.db,*.sqlite,*.json,*.xml,*.config,*.ini,*.log -ErrorAction SilentlyContinue | Select-Object -First 100 FullName,Length,LastWriteTime | Format-List
} else { Write-Host 'NO_FIT' }
Write-Host '--- appdata fit related ---'
$roots=@($env:APPDATA,$env:LOCALAPPDATA,'C:\ProgramData')
foreach($r in $roots){ if($r){ Get-ChildItem -Path $r -Directory -Force -ErrorAction SilentlyContinue | Where-Object {$_.Name -match 'fit|launcher|fitgirl'} | Select-Object FullName | Format-List } }
