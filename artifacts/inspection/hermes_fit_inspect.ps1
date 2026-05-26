$ErrorActionPreference='SilentlyContinue'
$paths=@('C:\Users\micha\AppData\Roaming\com.fit-launcher.app','C:\Users\micha\AppData\Roaming\com.fitlauncher.carrotrub','C:\Users\micha\AppData\Local\com.fitlauncher.carrotrub','C:\Users\micha\AppData\Roaming\hydralauncher')
foreach($p in $paths){
  Write-Host "=== $p ==="
  if(Test-Path $p){
    Get-ChildItem -Path $p -Force | Select-Object Mode,Length,LastWriteTime,Name,FullName | Format-Table -AutoSize
    Write-Host '--- data files ---'
    Get-ChildItem -Path $p -Recurse -Force -Include *.db,*.sqlite,*.json,*.log,*.config,*.ldb,*.sqlite-shm,*.sqlite-wal -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 80 FullName,Length,LastWriteTime | Format-List
  }
}
Write-Host '=== process ==='
Get-Process | Where-Object {$_.Path -like '*Fit Launcher*' -or $_.ProcessName -like '*Fit*' -or $_.ProcessName -like '*launcher*'} | Select-Object Id,ProcessName,Path,MainWindowTitle | Format-List
